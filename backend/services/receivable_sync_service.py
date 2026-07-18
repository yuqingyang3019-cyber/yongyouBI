from __future__ import annotations

import threading
from dataclasses import dataclass
from time import sleep
from typing import Any, Optional

from backend.clients.yonyou.sales import (
    get_sale_contract_by_id,
    get_sale_invoice_by_id,
    list_sale_invoices,
)
from backend.config import get_settings
from backend.db.receivable_store import ReceivableCacheStore, get_receivable_store
from backend.date_ranges import rolling_12m_range
from backend.value_utils import as_text


RECEIVABLE_SYNC_KEY = "receivable-rolling-12m"


@dataclass
class SyncState:
    month: str
    status: str = "idle"
    pending: int = 0
    done_count: int = 0
    total_listed: int = 0
    skipped: int = 0
    error: str = ""
    updated_at: str = ""
    last_synced_at: str = ""
    started: bool = False


_STATES: dict[str, SyncState] = {}
_THREADS: dict[str, threading.Thread] = {}
_LOCK = threading.Lock()


def _normalize_sync_key(_month: Optional[str] = None) -> str:
    return RECEIVABLE_SYNC_KEY


def _record_id(record: dict[str, Any]) -> str:
    return as_text(record.get("id")) or as_text(record.get("code"))


def _record_list_ts(record: dict[str, Any]) -> str:
    for key in ("pubts", "ts", "createTime", "auditTime", "vouchdate"):
        text = as_text(record.get(key))
        if text:
            return text
    return ""


def _needs_fetch(list_ts: str, cached_ts: str | None) -> bool:
    if cached_ts is None:
        return True
    if not list_ts:
        return False
    return list_ts != cached_ts


def _source_month_key(record: dict[str, Any], detail: dict[str, Any] | None = None) -> str:
    for source in (detail or {}, record):
        for key in ("vouchdate", "auditTime", "createTime"):
            text = as_text(source.get(key))
            if not text:
                continue
            if len(text) >= 7 and text[4] == "-":
                return text[:7]
    return RECEIVABLE_SYNC_KEY


def invoice_contract_ref(payload: dict[str, Any]) -> tuple[str, str]:
    lines = payload.get("saleInvoiceDetails") or payload.get("details") or []
    if not isinstance(lines, list):
        return "", ""
    for line in lines:
        if not isinstance(line, dict):
            continue
        code = as_text(line.get("sactCode") or line.get("firstupcode"))
        contract_id = as_text(line.get("sactId"))
        if code or contract_id:
            return code, contract_id
    return "", ""


def _snapshot_state(sync_key: str) -> SyncState | None:
    with _LOCK:
        state = _STATES.get(sync_key)
        if state is None:
            return None
        return SyncState(
            month=state.month,
            status=state.status,
            pending=state.pending,
            done_count=state.done_count,
            total_listed=state.total_listed,
            skipped=state.skipped,
            error=state.error,
            updated_at=state.updated_at,
            last_synced_at=state.last_synced_at,
            started=state.started,
        )


def get_receivable_sync_status(month: Optional[str] = None, store: ReceivableCacheStore | None = None) -> dict[str, Any]:
    sync_key = _normalize_sync_key(month)
    cache = store or get_receivable_store()
    meta = cache.get_sync_meta(sync_key)
    cached_count = cache.count_all_sale_invoices()
    latest = (
        meta.get("updated_at")
        or cache.latest_sale_invoice_updated_at()
        or cache.latest_updated_at()
    )
    state = _snapshot_state(sync_key)
    start, end = rolling_12m_range()

    base = {
        "month": sync_key,
        "scope": sync_key,
        "range": {"start": start, "end": end},
        "pending": 0,
        "doneCount": 0,
        "totalListed": 0,
        "skipped": 0,
        "error": meta.get("last_error") or "",
        "lastSyncedAt": meta.get("last_synced_at") or "",
        "updatedAt": latest,
        "cachedCount": cached_count,
    }

    if state is None:
        return {**base, "status": "idle"}

    return {
        **base,
        "status": state.status,
        "pending": state.pending,
        "doneCount": state.done_count,
        "totalListed": state.total_listed,
        "skipped": state.skipped,
        "error": state.error or meta.get("last_error") or "",
        "lastSyncedAt": state.last_synced_at or meta.get("last_synced_at") or "",
        "updatedAt": state.updated_at or latest,
    }


def _run_sync(sync_key: str, store: ReceivableCacheStore) -> None:
    settings = get_settings()
    with _LOCK:
        state = _STATES.setdefault(sync_key, SyncState(month=sync_key))
        state.status = "running"
        state.error = ""
        state.started = True

    try:
        start, end = rolling_12m_range()
        start_time = f"{start} 00:00:00"
        end_time = f"{end} 00:00:00"
        page = list_sale_invoices(start_time, end_time)

        listed: list[tuple[str, str, dict[str, Any]]] = []
        for record in page.records:
            invoice_id = _record_id(record)
            if not invoice_id:
                continue
            listed.append((invoice_id, _record_list_ts(record), record))

        cached_ts = store.get_sale_invoice_list_ts_map(None)
        todo: list[tuple[str, str, dict[str, Any]]] = []
        skipped = 0
        for invoice_id, list_ts, record in listed:
            if _needs_fetch(list_ts, cached_ts.get(invoice_id)):
                todo.append((invoice_id, list_ts, record))
            else:
                skipped += 1

        with _LOCK:
            state = _STATES[sync_key]
            state.total_listed = len(listed)
            state.pending = len(todo)
            state.done_count = 0
            state.skipped = skipped

        contract_ts = store.get_sale_contract_list_ts_map(None)

        for index, (invoice_id, list_ts, record) in enumerate(todo):
            detail = get_sale_invoice_by_id(invoice_id)
            source_month = _source_month_key(record, detail)
            store.upsert_sale_invoice(invoice_id, source_month, list_ts, detail)

            contract_code, contract_id = invoice_contract_ref(detail)
            if contract_id:
                contract_list_ts = as_text(detail.get("pubts")) or list_ts
                if _needs_fetch(contract_list_ts, contract_ts.get(contract_id)):
                    contract_detail = get_sale_contract_by_id(contract_id)
                    contract_month = _source_month_key({"code": contract_code}, contract_detail)
                    store.upsert_sale_contract(
                        contract_id,
                        contract_month,
                        contract_list_ts,
                        contract_detail,
                    )
                    contract_ts[contract_id] = contract_list_ts

            updated_at = store.latest_sale_invoice_updated_at() or store.get_sync_meta(sync_key).get("updated_at", "")
            with _LOCK:
                state = _STATES[sync_key]
                state.done_count += 1
                state.pending = max(len(todo) - state.done_count, 0)
                state.updated_at = updated_at
            if index < len(todo) - 1:
                sleep(max(settings.contract_detail_sync_interval, 0))

        store.mark_sync_finished(sync_key)
        from backend.services.overdue_service import contract_overdue

        contract_overdue(kick=False, store=store)
        meta = store.get_sync_meta(sync_key)
        updated_at = store.latest_sale_invoice_updated_at() or store.get_sync_meta(sync_key).get("updated_at", "")
        with _LOCK:
            state = _STATES[sync_key]
            state.status = "done"
            state.pending = 0
            state.last_synced_at = meta.get("last_synced_at") or ""
            state.updated_at = updated_at
    except Exception as exc:  # noqa: BLE001 - surface sync failure to status API
        message = str(exc)
        store.mark_sync_finished(sync_key, error=message)
        updated_at = store.latest_sale_invoice_updated_at() or store.get_sync_meta(sync_key).get("updated_at", "")
        with _LOCK:
            state = _STATES[sync_key]
            state.status = "error"
            state.error = message
            state.updated_at = updated_at
    finally:
        with _LOCK:
            _THREADS.pop(sync_key, None)


def kick_receivable_sync(
    month: Optional[str] = None,
    *,
    force: bool = False,
    store: ReceivableCacheStore | None = None,
) -> dict[str, Any]:
    sync_key = _normalize_sync_key(month)
    cache = store or get_receivable_store()

    with _LOCK:
        existing = _THREADS.get(sync_key)
        already_running = existing is not None and existing.is_alive()
        if not already_running:
            state = _STATES.setdefault(sync_key, SyncState(month=sync_key))
            if force:
                state.status = "idle"
                state.error = ""
            state.status = "running"
            thread = threading.Thread(
                target=_run_sync,
                args=(sync_key, cache),
                name=f"receivable-sync-{sync_key}",
                daemon=True,
            )
            _THREADS[sync_key] = thread
            thread.start()

    return get_receivable_sync_status(sync_key, cache)
