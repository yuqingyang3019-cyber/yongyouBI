from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.db.receivable_store import ReceivableCacheStore
from backend.services.overdue_service import contract_overdue


TABLES = (
    ("sale_invoice_detail_cache", "sale_invoices", "invoice_id"),
    ("sale_contract_detail_cache", "sale_contracts", "contract_id"),
    ("collection_detail_cache", "collections", "collection_id"),
)


def _digest(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> None:
    source = Path(os.getenv("YONBIP_SQLITE_MIGRATION_SOURCE", ROOT / "data" / "yongyou_cache.sqlite"))
    database_url = (os.getenv("RECEIVABLE_DATABASE_URL") or "").strip()
    if not source.exists():
        raise RuntimeError(f"SQLite 源文件不存在：{source}")
    if not database_url:
        raise RuntimeError("缺少 RECEIVABLE_DATABASE_URL")

    backup = source.with_name(f"{source.name}.backup-{datetime.now():%Y%m%d%H%M%S}")
    shutil.copy2(source, backup)

    source_conn = sqlite3.connect(source)
    source_conn.row_factory = sqlite3.Row
    source_counts: dict[str, int] = {}
    samples: list[tuple[str, str, str]] = []

    store = ReceivableCacheStore(database_url)
    try:
        with psycopg.connect(database_url) as target:
            for source_table, target_table, id_column in TABLES:
                rows = source_conn.execute(
                    f"SELECT {id_column}, month_key, list_ts, payload_json, fetched_at FROM {source_table}"
                ).fetchall()
                source_counts[target_table] = len(rows)
                with target.cursor() as cursor:
                    cursor.executemany(
                        f"""
                        INSERT INTO receivable_raw.{target_table}
                            ({id_column}, month_key, list_ts, payload_json, fetched_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT ({id_column}) DO UPDATE SET
                            month_key = EXCLUDED.month_key,
                            list_ts = EXCLUDED.list_ts,
                            payload_json = EXCLUDED.payload_json,
                            fetched_at = EXCLUDED.fetched_at
                        """,
                        [
                            (
                                row[id_column],
                                row["month_key"],
                                row["list_ts"] or "",
                                Jsonb(json.loads(row["payload_json"])),
                                row["fetched_at"],
                            )
                            for row in rows
                        ],
                    )
                for row in rows[:3]:
                    samples.append(
                        (target_table, str(row[id_column]), _digest(json.loads(row["payload_json"])))
                    )

            meta_rows = source_conn.execute(
                "SELECT month_key, last_synced_at, updated_at, last_error FROM sync_meta"
            ).fetchall()
            with target.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO receivable_raw.sync_meta
                        (month_key, last_synced_at, updated_at, last_error)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (month_key) DO UPDATE SET
                        last_synced_at = EXCLUDED.last_synced_at,
                        updated_at = EXCLUDED.updated_at,
                        last_error = EXCLUDED.last_error
                    """,
                    [tuple(row) for row in meta_rows],
                )

        with psycopg.connect(database_url, row_factory=dict_row) as target:
            for target_table, expected in source_counts.items():
                actual = target.execute(
                    f"SELECT COUNT(*) AS count FROM receivable_raw.{target_table}"
                ).fetchone()["count"]
                if int(actual) != expected:
                    raise RuntimeError(f"{target_table} 数量不一致：SQLite={expected}, PostgreSQL={actual}")
            for target_table, record_id, expected_hash in samples:
                id_column = next(item[2] for item in TABLES if item[1] == target_table)
                payload = target.execute(
                    f"SELECT payload_json FROM receivable_raw.{target_table} WHERE {id_column} = %s",
                    (record_id,),
                ).fetchone()["payload_json"]
                if _digest(payload) != expected_hash:
                    raise RuntimeError(f"{target_table}/{record_id} payload 校验失败")

        result = contract_overdue(kick=False, store=store)
        print(
            "迁移完成："
            f"发票 {source_counts['sale_invoices']}，"
            f"合同 {source_counts['sale_contracts']}，"
            f"收款 {source_counts['collections']}，"
            f"事实 {result['meta']['rowCount'] + result['meta']['settledRowCount']}；"
            f"备份 {backup}"
        )
    finally:
        store.close()
        source_conn.close()


if __name__ == "__main__":
    main()
