from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from backend.config import optional_env, require_env


@dataclass(frozen=True)
class CachedReceivableRecord:
    record_id: str
    month_key: str
    list_ts: str
    payload: dict[str, Any]
    fetched_at: str


_TABLES = {
    "invoice": ("sale_invoices", "invoice_id"),
    "contract": ("sale_contracts", "contract_id"),
    "collection": ("collections", "collection_id"),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _as_iso(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value or "")


class ReceivableCacheStore:
    """PostgreSQL repository kept under the existing name to preserve service contracts."""

    def __init__(self, database_url: str | None = None, *, apply_migrations: bool = True) -> None:
        self.database_url = database_url or require_env("RECEIVABLE_DATABASE_URL")
        self._pool = ConnectionPool(
            self.database_url,
            min_size=1,
            max_size=max(int(optional_env("RECEIVABLE_DB_POOL_SIZE", "8")), 1),
            kwargs={"row_factory": dict_row},
            open=True,
        )
        if apply_migrations:
            self.apply_migrations()

    def close(self) -> None:
        self._pool.close()

    def apply_migrations(self) -> None:
        migrations_dir = Path(__file__).with_name("migrations")
        with self._pool.connection() as conn:
            for migration in sorted(migrations_dir.glob("*.sql")):
                conn.execute(migration.read_text(encoding="utf-8"))

    def _list_ts_map(self, kind: str, month_key: str | None) -> dict[str, str]:
        table, id_column = _TABLES[kind]
        query = sql.SQL("SELECT {}, list_ts FROM receivable_raw.{}").format(
            sql.Identifier(id_column),
            sql.Identifier(table),
        )
        params: tuple[str, ...] = ()
        if month_key:
            query += sql.SQL(" WHERE month_key = %s")
            params = (month_key,)
        with self._pool.connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return {str(row[id_column]): str(row["list_ts"] or "") for row in rows}

    def _all(self, kind: str) -> list[CachedReceivableRecord]:
        table, id_column = _TABLES[kind]
        query = sql.SQL(
            "SELECT {}, month_key, list_ts, payload_json, fetched_at "
            "FROM receivable_raw.{} ORDER BY {}"
        ).format(
            sql.Identifier(id_column),
            sql.Identifier(table),
            sql.Identifier(id_column),
        )
        with self._pool.connection() as conn:
            rows = conn.execute(query).fetchall()
        return [
            CachedReceivableRecord(
                record_id=str(row[id_column]),
                month_key=str(row["month_key"]),
                list_ts=str(row["list_ts"] or ""),
                payload=dict(row["payload_json"]),
                fetched_at=_as_iso(row["fetched_at"]),
            )
            for row in rows
            if isinstance(row["payload_json"], dict)
        ]

    def _count(self, kind: str) -> int:
        table, _ = _TABLES[kind]
        query = sql.SQL("SELECT COUNT(*) AS cnt FROM receivable_raw.{}").format(sql.Identifier(table))
        with self._pool.connection() as conn:
            row = conn.execute(query).fetchone()
        return int(row["cnt"] if row else 0)

    def _latest(self, kind: str) -> str:
        table, _ = _TABLES[kind]
        query = sql.SQL("SELECT MAX(fetched_at) AS latest FROM receivable_raw.{}").format(
            sql.Identifier(table)
        )
        with self._pool.connection() as conn:
            row = conn.execute(query).fetchone()
        return _as_iso(row["latest"]) if row and row["latest"] else ""

    def _upsert(
        self,
        kind: str,
        record_id: str,
        month_key: str,
        list_ts: str,
        payload: dict[str, Any],
        fetched_at: str | datetime | None,
    ) -> None:
        table, id_column = _TABLES[kind]
        query = sql.SQL(
            """
            INSERT INTO receivable_raw.{} ({}, month_key, list_ts, payload_json, fetched_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT ({}) DO UPDATE SET
                month_key = EXCLUDED.month_key,
                list_ts = EXCLUDED.list_ts,
                payload_json = EXCLUDED.payload_json,
                fetched_at = EXCLUDED.fetched_at
            """
        ).format(
            sql.Identifier(table),
            sql.Identifier(id_column),
            sql.Identifier(id_column),
        )
        with self._pool.connection() as conn:
            conn.execute(
                query,
                (record_id, month_key, list_ts or "", Jsonb(payload), fetched_at or _utc_now()),
            )

    def get_sync_meta(self, month_key: str) -> dict[str, str]:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT last_synced_at, updated_at, last_error
                FROM receivable_raw.sync_meta WHERE month_key = %s
                """,
                (month_key,),
            ).fetchone()
        if not row:
            return {"last_synced_at": "", "updated_at": "", "last_error": ""}
        return {
            "last_synced_at": _as_iso(row["last_synced_at"]),
            "updated_at": _as_iso(row["updated_at"]),
            "last_error": str(row["last_error"] or ""),
        }

    def mark_sync_finished(self, month_key: str, error: str = "") -> None:
        stamp = _utc_now()
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO receivable_raw.sync_meta
                    (month_key, last_synced_at, updated_at, last_error)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (month_key) DO UPDATE SET
                    last_synced_at = EXCLUDED.last_synced_at,
                    updated_at = EXCLUDED.updated_at,
                    last_error = EXCLUDED.last_error
                """,
                (month_key, stamp, stamp, error or ""),
            )

    def latest_updated_at(self) -> str:
        latest = max(
            self.latest_sale_invoice_updated_at(),
            self.latest_collection_updated_at(),
            self._latest("contract"),
        )
        return latest

    def get_sale_invoice_list_ts_map(self, month_key: str | None = None) -> dict[str, str]:
        return self._list_ts_map("invoice", month_key)

    def get_all_sale_invoices(self) -> list[CachedReceivableRecord]:
        return self._all("invoice")

    def count_all_sale_invoices(self) -> int:
        return self._count("invoice")

    def latest_sale_invoice_updated_at(self) -> str:
        return self._latest("invoice")

    def upsert_sale_invoice(
        self,
        record_id: str,
        month_key: str,
        list_ts: str,
        payload: dict[str, Any],
        fetched_at: str | datetime | None = None,
    ) -> None:
        self._upsert("invoice", record_id, month_key, list_ts, payload, fetched_at)

    def get_sale_contract_list_ts_map(self, month_key: str | None = None) -> dict[str, str]:
        return self._list_ts_map("contract", month_key)

    def get_all_sale_contracts(self) -> list[CachedReceivableRecord]:
        return self._all("contract")

    def count_all_sale_contracts(self) -> int:
        return self._count("contract")

    def upsert_sale_contract(
        self,
        record_id: str,
        month_key: str,
        list_ts: str,
        payload: dict[str, Any],
        fetched_at: str | datetime | None = None,
    ) -> None:
        self._upsert("contract", record_id, month_key, list_ts, payload, fetched_at)

    def get_collection_list_ts_map(self, month_key: str | None = None) -> dict[str, str]:
        return self._list_ts_map("collection", month_key)

    def get_all_collections(self) -> list[CachedReceivableRecord]:
        return self._all("collection")

    def count_all_collections(self) -> int:
        return self._count("collection")

    def latest_collection_updated_at(self) -> str:
        return self._latest("collection")

    def upsert_collection(
        self,
        record_id: str,
        month_key: str,
        list_ts: str,
        payload: dict[str, Any],
        fetched_at: str | datetime | None = None,
    ) -> None:
        self._upsert("collection", record_id, month_key, list_ts, payload, fetched_at)

    def delete_collection(self, record_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "DELETE FROM receivable_raw.collections WHERE collection_id = %s",
                (record_id,),
            )

    def replace_receivable_facts(self, rows: list[dict[str, Any]]) -> None:
        values = [
            (
                row.get("invoiceId") or "",
                row.get("invoiceCode") or "",
                row.get("contractCode") or "",
                row.get("customer") or "",
                row.get("salesman") or "",
                Decimal(str(row.get("taxAmount") or 0)),
                Decimal(str(row.get("collectedAmount") or 0)),
                Decimal(str(row.get("outstanding") or 0)),
                row.get("collectionStatus") or "unpaid",
                row.get("matchQuality") or "unpaid",
                row.get("auditTime") or None,
                int(row.get("paymentTermDays") or 0),
                row.get("dueDate") or None,
                int(row.get("daysUntilDue") or 0),
                row.get("calendarStatus") or row.get("status") or "unmatched",
                row.get("trueStatus") or row.get("status") or "unmatched",
            )
            for row in rows
            if row.get("invoiceId")
        ]
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM receivable_analytics.invoice_facts")
            if values:
                with conn.cursor() as cursor:
                    cursor.executemany(
                        """
                        INSERT INTO receivable_analytics.invoice_facts (
                            invoice_id, invoice_code, contract_code, customer, salesman,
                            tax_amount, collected_amount, outstanding, collection_status,
                            match_quality, audit_time, payment_term_days, due_date,
                            days_until_due, calendar_status, true_status
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        """,
                        values,
                    )


_STORE: Optional[ReceivableCacheStore] = None
_STORE_LOCK = Lock()


def get_receivable_store(database_url: str | None = None) -> ReceivableCacheStore:
    global _STORE
    if database_url is not None:
        return ReceivableCacheStore(database_url)
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = ReceivableCacheStore()
        return _STORE
