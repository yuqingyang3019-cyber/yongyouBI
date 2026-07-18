from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Literal

from backend.clients.dingtalk.openapi_client import DingTalkOpenApiClient
from backend.config import optional_env
from backend.db.contact_cache_store import ContactCacheStore, get_contact_cache_store

ContactSyncMode = Literal["full", "incremental", "cache_hit"]

_ORG_USERS_CACHE: list[dict[str, Any]] | None = None
_CONTACT_SYNC_INFO: dict[str, Any] = {}

_DEFAULT_TTL_HOURS = 6.0
_REQUEST_SLEEP_SEC = 0.05


def clear_contact_cache() -> None:
    global _ORG_USERS_CACHE
    _ORG_USERS_CACHE = None


def get_contact_sync_info() -> dict[str, Any]:
    return dict(_CONTACT_SYNC_INFO)


def _contact_ttl_hours() -> float:
    raw = optional_env("DINGTALK_CONTACT_CACHE_TTL_HOURS") or optional_env("PAYROLL_CONTACT_CACHE_TTL_HOURS")
    if not raw:
        return _DEFAULT_TTL_HOURS
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return _DEFAULT_TTL_HOURS


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _cache_age_hours(meta: dict[str, str]) -> float | None:
    scanned_at = _parse_iso(meta.get("last_user_scan_at", ""))
    if scanned_at is None:
        return None
    now = datetime.now(timezone.utc)
    if scanned_at.tzinfo is None:
        scanned_at = scanned_at.replace(tzinfo=timezone.utc)
    return max((now - scanned_at.astimezone(timezone.utc)).total_seconds() / 3600.0, 0.0)


def fetch_all_departments(client: DingTalkOpenApiClient, root_dept_id: int = 1) -> dict[int, str]:
    payload = client.topapi_get(
        "department/list",
        {"fetch_child": "true", "id": str(root_dept_id)},
    )
    departments = payload.get("department")
    if not isinstance(departments, list):
        return {root_dept_id: "根部门"}
    names = {root_dept_id: "根部门"}
    for item in departments:
        if not isinstance(item, dict):
            continue
        dept_id = item.get("id")
        if dept_id is None:
            continue
        names[int(dept_id)] = str(item.get("name") or "")
    return names


def list_department_users(client: DingTalkOpenApiClient, dept_id: int) -> list[dict[str, Any]]:
    users: list[dict[str, Any]] = []
    cursor = 0
    while True:
        result = client.topapi_post(
            "topapi/v2/user/list",
            {"dept_id": dept_id, "cursor": cursor, "size": 100},
        )
        users.extend(result.get("list") or [])
        if not result.get("has_more"):
            break
        cursor = int(result.get("next_cursor") or 0)
        time.sleep(_REQUEST_SLEEP_SEC)
    return users


def _merge_users_for_depts(
    client: DingTalkOpenApiClient,
    depts: dict[int, str],
    dept_ids: set[int],
) -> list[dict[str, Any]]:
    users_by_id: dict[str, dict[str, Any]] = {}
    for dept_id in sorted(dept_ids):
        dept_name = depts.get(dept_id, "")
        for user in list_department_users(client, dept_id):
            userid = str(user.get("userid") or "")
            if not userid:
                continue
            existing = users_by_id.get(userid)
            if existing is None:
                copied = dict(user)
                copied["dept_ids"] = [dept_id]
                if dept_name and not copied.get("dept_name"):
                    copied["dept_name"] = dept_name
                users_by_id[userid] = copied
                continue
            dept_list = list(existing.get("dept_ids") or [])
            if dept_id not in dept_list:
                dept_list.append(dept_id)
            existing["dept_ids"] = dept_list
            if dept_name:
                current_name = str(existing.get("dept_name") or "").strip()
                existing["dept_name"] = (
                    f"{current_name}、{dept_name}".strip("、") if current_name else dept_name
                )
        time.sleep(_REQUEST_SLEEP_SEC)
    return list(users_by_id.values())


def sync_organization_users(
    client: DingTalkOpenApiClient,
    *,
    force_full: bool = False,
    store: ContactCacheStore | None = None,
    root_dept_id: int = 1,
) -> tuple[list[dict[str, Any]], ContactSyncMode, dict[str, Any]]:
    global _ORG_USERS_CACHE, _CONTACT_SYNC_INFO

    cache_store = store or get_contact_cache_store()
    depts = fetch_all_departments(client, root_dept_id=root_dept_id)
    meta = cache_store.get_meta()
    ttl_hours = _contact_ttl_hours()
    cache_age = _cache_age_hours(meta)

    added = 0
    removed = 0
    mode: ContactSyncMode = "full"

    if force_full or not cache_store.has_users():
        users = _merge_users_for_depts(client, depts, set(depts))
        added, removed = cache_store.replace_all(depts, users)
        mode = "full"
    else:
        cached_depts = cache_store.get_dept_map()
        current_ids = set(depts)
        cached_ids = set(cached_depts)
        new_dept_ids = current_ids - cached_ids
        removed_dept_ids = cached_ids - current_ids
        dept_structure_changed = bool(new_dept_ids or removed_dept_ids)
        cache_stale = cache_age is None or cache_age >= ttl_hours

        if not dept_structure_changed and not cache_stale:
            users = cache_store.get_users()
            mode = "cache_hit"
        elif cache_stale or force_full:
            users = _merge_users_for_depts(client, depts, current_ids)
            added, removed = cache_store.apply_user_scan(depts, users)
            mode = "full" if cache_stale else "incremental"
        else:
            if removed_dept_ids:
                _, removed = cache_store.remove_departments(removed_dept_ids)
            dept_users: dict[int, list[dict[str, Any]]] = {}
            for dept_id in sorted(new_dept_ids):
                dept_users[dept_id] = list_department_users(client, dept_id)
                time.sleep(_REQUEST_SLEEP_SEC)
            added, removed_delta = cache_store.upsert_department_users(depts, dept_users)
            removed += removed_delta
            users = cache_store.get_users()
            mode = "incremental"

    _ORG_USERS_CACHE = users
    refreshed_meta = cache_store.get_meta()
    _CONTACT_SYNC_INFO = {
        "mode": mode,
        "userCount": len(users),
        "deptCount": len(depts),
        "added": added,
        "removed": removed,
        "cacheAgeHours": round(cache_age, 2) if cache_age is not None else None,
        "ttlHours": ttl_hours,
        "lastUserScanAt": refreshed_meta.get("last_user_scan_at", ""),
        "lastFullSyncAt": refreshed_meta.get("last_full_sync_at", ""),
    }
    return users, mode, _CONTACT_SYNC_INFO


def list_organization_users(
    client: DingTalkOpenApiClient,
    root_dept_id: int = 1,
    *,
    force_full: bool = False,
) -> list[dict[str, Any]]:
    global _ORG_USERS_CACHE
    if _ORG_USERS_CACHE is not None:
        return _ORG_USERS_CACHE
    users, _, _ = sync_organization_users(client, force_full=force_full, root_dept_id=root_dept_id)
    return users


def resolve_userid_by_name(
    name: str,
    *,
    client: DingTalkOpenApiClient | None = None,
    users: list[dict[str, Any]] | None = None,
) -> str:
    target = str(name or "").strip()
    if not target:
        return ""
    pool = list(users or [])
    if not pool and client is not None:
        pool = list_organization_users(client)
    for user in pool:
        if str(user.get("name") or "").strip() == target:
            return str(user.get("userid") or "")
    return ""
