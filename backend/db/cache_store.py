from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.config import PROJECT_ROOT, optional_env


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_cache_db_path() -> Path:
    configured = optional_env("YONBIP_CACHE_DB")
    if configured:
        return Path(configured)
    return PROJECT_ROOT / "data" / "yongyou_cache.sqlite"


@dataclass(frozen=True)
class CachedContract:
    contract_id: str
    month_key: str
    list_ts: str
    payload: dict[str, Any]
    fetched_at: str


class ContractCacheStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_cache_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS contract_detail_cache (
                        contract_id TEXT PRIMARY KEY,
                        month_key TEXT NOT NULL,
                        list_ts TEXT NOT NULL DEFAULT '',
                        payload_json TEXT NOT NULL,
                        fetched_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_contract_detail_month
                    ON contract_detail_cache(month_key)
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sync_meta (
                        month_key TEXT PRIMARY KEY,
                        last_synced_at TEXT,
                        updated_at TEXT,
                        last_error TEXT NOT NULL DEFAULT ''
                    )
                    """
                )
                conn.commit()

    def get_list_ts_map(self, month_key: str | None = None) -> dict[str, str]:
        with self._lock:
            with self._connect() as conn:
                if month_key:
                    rows = conn.execute(
                        "SELECT contract_id, list_ts FROM contract_detail_cache WHERE month_key = ?",
                        (month_key,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT contract_id, list_ts FROM contract_detail_cache"
                    ).fetchall()
        return {str(row["contract_id"]): str(row["list_ts"] or "") for row in rows}

    def get_by_month(self, month_key: str) -> list[CachedContract]:
        return self._rows_to_contracts(
            self._fetch_rows("WHERE month_key = ?", (month_key,))
        )

    def get_all(self) -> list[CachedContract]:
        return self._rows_to_contracts(self._fetch_rows("", ()))

    def _fetch_rows(self, where_sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
        query = f"""
            SELECT contract_id, month_key, list_ts, payload_json, fetched_at
            FROM contract_detail_cache
            {where_sql}
            ORDER BY contract_id
        """
        with self._lock:
            with self._connect() as conn:
                return conn.execute(query, params).fetchall()

    def _rows_to_contracts(self, rows: list[sqlite3.Row]) -> list[CachedContract]:
        result: list[CachedContract] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            result.append(
                CachedContract(
                    contract_id=str(row["contract_id"]),
                    month_key=str(row["month_key"]),
                    list_ts=str(row["list_ts"] or ""),
                    payload=payload,
                    fetched_at=str(row["fetched_at"] or ""),
                )
            )
        return result

    def count_by_month(self, month_key: str) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM contract_detail_cache WHERE month_key = ?",
                    (month_key,),
                ).fetchone()
        return int(row["cnt"] if row else 0)

    def count_all(self) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) AS cnt FROM contract_detail_cache").fetchone()
        return int(row["cnt"] if row else 0)

    def upsert(
        self,
        contract_id: str,
        month_key: str,
        list_ts: str,
        payload: dict[str, Any],
        fetched_at: str | None = None,
    ) -> None:
        stamp = fetched_at or _utc_now_iso()
        payload_json = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO contract_detail_cache (
                        contract_id, month_key, list_ts, payload_json, fetched_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(contract_id) DO UPDATE SET
                        month_key = excluded.month_key,
                        list_ts = excluded.list_ts,
                        payload_json = excluded.payload_json,
                        fetched_at = excluded.fetched_at
                    """,
                    (contract_id, month_key, list_ts or "", payload_json, stamp),
                )
                conn.execute(
                    """
                    INSERT INTO sync_meta (month_key, last_synced_at, updated_at, last_error)
                    VALUES (?, ?, ?, '')
                    ON CONFLICT(month_key) DO UPDATE SET
                        updated_at = excluded.updated_at,
                        last_error = ''
                    """,
                    (month_key, stamp, stamp),
                )
                conn.commit()

    def mark_sync_finished(self, month_key: str, error: str = "") -> None:
        stamp = _utc_now_iso()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO sync_meta (month_key, last_synced_at, updated_at, last_error)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(month_key) DO UPDATE SET
                        last_synced_at = excluded.last_synced_at,
                        updated_at = excluded.updated_at,
                        last_error = excluded.last_error
                    """,
                    (month_key, stamp, stamp, error or ""),
                )
                conn.commit()

    def get_sync_meta(self, month_key: str) -> dict[str, str]:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT last_synced_at, updated_at, last_error
                    FROM sync_meta WHERE month_key = ?
                    """,
                    (month_key,),
                ).fetchone()
        if not row:
            return {"last_synced_at": "", "updated_at": "", "last_error": ""}
        return {
            "last_synced_at": str(row["last_synced_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "last_error": str(row["last_error"] or ""),
        }

    def latest_updated_at(self, month_key: str | None = None) -> str:
        if month_key:
            meta = self.get_sync_meta(month_key)
            if meta["updated_at"]:
                return meta["updated_at"]
        with self._lock:
            with self._connect() as conn:
                if month_key:
                    row = conn.execute(
                        """
                        SELECT MAX(fetched_at) AS latest
                        FROM contract_detail_cache
                        WHERE month_key = ?
                        """,
                        (month_key,),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT MAX(fetched_at) AS latest FROM contract_detail_cache"
                    ).fetchone()
        return str(row["latest"] or "") if row else ""


_STORE: Optional[ContractCacheStore] = None
_STORE_LOCK = threading.Lock()


def get_cache_store(db_path: Path | None = None) -> ContractCacheStore:
    global _STORE
    if db_path is not None:
        return ContractCacheStore(db_path)
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = ContractCacheStore()
        return _STORE
