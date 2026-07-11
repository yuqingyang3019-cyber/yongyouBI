from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date
from time import sleep
from typing import Any, Optional

from backend.clients.yonyou.purchase import get_contract_by_id, list_contracts
from backend.config import get_settings
from backend.db.cache_store import ContractCacheStore, get_cache_store
from backend.services.bi_service import as_text


ROLLING_SYNC_KEY = "rolling-12m"
ROLLING_MONTHS = 12


def _next_day(day: str) -> str:
    year, month, date_part = (int(part) for part in day.split("-"))
    return date.fromordinal(date(year, month, date_part).toordinal() + 1).isoformat()


def rolling_12m_range(today: date | None = None) -> tuple[str, str]:
    today_value = today or date.today()
    year = today_value.year
    month = today_value.month - (ROLLING_MONTHS - 1)
    while month <= 0:
        month += 12
        year -= 1
    start = date(year, month, 1)
    end_exclusive = _next_day(today_value.isoformat())
    return start.isoformat(), end_exclusive


def _source_month_key(record: dict[str, Any], detail: dict[str, Any] | None = None) -> str:
    for source in (detail or {}, record):
        for key in ("createTime", "subscribedate", "actualvalidate"):
            text = as_text(source.get(key))
            if not text:
                continue
            if text.isdigit() and len(text) >= 10:
                try:
                    millis = int(text)
                    if millis > 10_000_000_000:
                        millis //= 1000
                    return date.fromtimestamp(millis).strftime("%Y-%m")
                except (ValueError, OSError, OverflowError):
                    continue
            if len(text) >= 7 and text[4] == "-":
                return text[:7]
    return ROLLING_SYNC_KEY


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
    # 月份参数已废弃，统一使用滚动 12 个月任务键
    return ROLLING_SYNC_KEY


def _record_id(record: dict[str, Any]) -> str:
    return as_text(record.get("id")) or as_text(record.get("code"))


def _record_list_ts(record: dict[str, Any]) -> str:
    for key in ("ts", "pubts", "modifiedtime", "createTime"):
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


def get_sync_status(month: Optional[str] = None, store: ContractCacheStore | None = None) -> dict[str, Any]:
    sync_key = _normalize_sync_key(month)
    cache = store or get_cache_store()
    meta = cache.get_sync_meta(sync_key)
    cached_count = cache.count_all()
    latest = meta.get("updated_at") or cache.latest_updated_at(sync_key) or cache.latest_updated_at()
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


def _run_sync(sync_key: str, store: ContractCacheStore) -> None:
    settings = get_settings()
    with _LOCK:
        state = _STATES.setdefault(sync_key, SyncState(month=sync_key))
        state.status = "running"
        state.error = ""
        state.started = True

    try:
        start, end = rolling_12m_range()
        page = list_contracts(start, end)
        listed: list[tuple[str, str, dict[str, Any]]] = []
        for record in page.records:
            contract_id = _record_id(record)
            if not contract_id:
                continue
            listed.append((contract_id, _record_list_ts(record), record))

        cached_ts = store.get_list_ts_map(None)
        todo: list[tuple[str, str, dict[str, Any]]] = []
        skipped = 0
        for contract_id, list_ts, record in listed:
            if _needs_fetch(list_ts, cached_ts.get(contract_id)):
                todo.append((contract_id, list_ts, record))
            else:
                skipped += 1

        with _LOCK:
            state = _STATES[sync_key]
            state.total_listed = len(listed)
            state.pending = len(todo)
            state.done_count = 0
            state.skipped = skipped

        for index, (contract_id, list_ts, record) in enumerate(todo):
            detail = get_contract_by_id(contract_id)
            source_month = _source_month_key(record, detail)
            store.upsert(contract_id, source_month, list_ts, detail)
            updated_at = store.latest_updated_at()
            with _LOCK:
                state = _STATES[sync_key]
                state.done_count += 1
                state.pending = max(len(todo) - state.done_count, 0)
                state.updated_at = updated_at
            if index < len(todo) - 1:
                sleep(max(settings.contract_detail_sync_interval, 0))

        store.mark_sync_finished(sync_key)
        meta = store.get_sync_meta(sync_key)
        updated_at = store.latest_updated_at(sync_key) or store.latest_updated_at()
        with _LOCK:
            state = _STATES[sync_key]
            state.status = "done"
            state.pending = 0
            state.last_synced_at = meta.get("last_synced_at") or ""
            state.updated_at = updated_at
    except Exception as exc:  # noqa: BLE001 - surface sync failure to status API
        message = str(exc)
        store.mark_sync_finished(sync_key, error=message)
        updated_at = store.latest_updated_at(sync_key) or store.latest_updated_at()
        with _LOCK:
            state = _STATES[sync_key]
            state.status = "error"
            state.error = message
            state.updated_at = updated_at
    finally:
        with _LOCK:
            _THREADS.pop(sync_key, None)


def kick_sync(
    month: Optional[str] = None,
    *,
    force: bool = False,
    store: ContractCacheStore | None = None,
) -> dict[str, Any]:
    sync_key = _normalize_sync_key(month)
    cache = store or get_cache_store()

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
                name=f"contract-sync-{sync_key}",
                daemon=True,
            )
            _THREADS[sync_key] = thread
            thread.start()

    return get_sync_status(sync_key, cache)
