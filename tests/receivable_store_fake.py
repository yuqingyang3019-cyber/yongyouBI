from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any


class InMemoryReceivableStore:
    def __init__(self) -> None:
        self.invoices: dict[str, SimpleNamespace] = {}
        self.contracts: dict[str, SimpleNamespace] = {}
        self.collections: dict[str, SimpleNamespace] = {}
        self.meta: dict[str, dict[str, str]] = {}
        self.facts: list[dict[str, Any]] = []

    @staticmethod
    def _stamp() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _upsert(
        self,
        bucket: dict[str, SimpleNamespace],
        record_id: str,
        month_key: str,
        list_ts: str,
        payload: dict[str, Any],
        fetched_at: str | None,
    ) -> None:
        bucket[record_id] = SimpleNamespace(
            record_id=record_id,
            month_key=month_key,
            list_ts=list_ts,
            payload=payload,
            fetched_at=fetched_at or self._stamp(),
        )

    def get_sync_meta(self, month_key: str) -> dict[str, str]:
        return self.meta.get(
            month_key,
            {"last_synced_at": "", "updated_at": "", "last_error": ""},
        )

    def mark_sync_finished(self, month_key: str, error: str = "") -> None:
        stamp = self._stamp()
        self.meta[month_key] = {
            "last_synced_at": stamp,
            "updated_at": stamp,
            "last_error": error,
        }

    def latest_updated_at(self) -> str:
        values = [item.fetched_at for bucket in self._buckets() for item in bucket.values()]
        return max(values, default="")

    def _buckets(self):
        return (self.invoices, self.contracts, self.collections)

    def upsert_sale_invoice(self, record_id, month_key, list_ts, payload, fetched_at=None):
        self._upsert(self.invoices, record_id, month_key, list_ts, payload, fetched_at)

    def upsert_sale_contract(self, record_id, month_key, list_ts, payload, fetched_at=None):
        self._upsert(self.contracts, record_id, month_key, list_ts, payload, fetched_at)

    def upsert_collection(self, record_id, month_key, list_ts, payload, fetched_at=None):
        self._upsert(self.collections, record_id, month_key, list_ts, payload, fetched_at)

    def delete_collection(self, record_id: str) -> None:
        self.collections.pop(record_id, None)

    def get_sale_invoice_list_ts_map(self, _month=None):
        return {key: item.list_ts for key, item in self.invoices.items()}

    def get_sale_contract_list_ts_map(self, _month=None):
        return {key: item.list_ts for key, item in self.contracts.items()}

    def get_collection_list_ts_map(self, _month=None):
        return {key: item.list_ts for key, item in self.collections.items()}

    def get_all_sale_invoices(self):
        return list(self.invoices.values())

    def get_all_sale_contracts(self):
        return list(self.contracts.values())

    def get_all_collections(self):
        return list(self.collections.values())

    def count_all_sale_invoices(self):
        return len(self.invoices)

    def count_all_sale_contracts(self):
        return len(self.contracts)

    def count_all_collections(self):
        return len(self.collections)

    def latest_sale_invoice_updated_at(self):
        return max((item.fetched_at for item in self.invoices.values()), default="")

    def latest_collection_updated_at(self):
        return max((item.fetched_at for item in self.collections.values()), default="")

    def replace_receivable_facts(self, rows):
        self.facts = list(rows)
