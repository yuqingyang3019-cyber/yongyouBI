from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import PROJECT_ROOT, optional_env


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_contact_cache_db_path() -> Path:
    configured = optional_env("DINGTALK_CONTACT_CACHE_DB") or optional_env("PAYROLL_CONTACT_CACHE_DB")
    if configured:
        return Path(configured)
    return PROJECT_ROOT / "data" / "payroll_contact_cache.sqlite"


class ContactCacheStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_contact_cache_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
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
                    CREATE TABLE IF NOT EXISTS org_users (
                        userid TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL,
                        dept_ids_json TEXT NOT NULL DEFAULT '[]',
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS org_depts (
                        dept_id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL DEFAULT '',
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS contact_sync_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                conn.commit()

    def has_users(self) -> bool:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) AS cnt FROM org_users").fetchone()
        return bool(row and int(row["cnt"]) > 0)

    def get_dept_map(self) -> dict[int, str]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute("SELECT dept_id, name FROM org_depts").fetchall()
        return {int(row["dept_id"]): str(row["name"] or "") for row in rows}

    def get_users(self) -> list[dict[str, Any]]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT payload_json FROM org_users ORDER BY userid"
                ).fetchall()
        users: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(str(row["payload_json"]))
            if isinstance(payload, dict):
                users.append(payload)
        return users

    def get_meta(self) -> dict[str, str]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute("SELECT key, value FROM contact_sync_meta").fetchall()
        return {str(row["key"]): str(row["value"] or "") for row in rows}

    def _set_meta(self, conn: sqlite3.Connection, key: str, value: str) -> None:
        conn.execute(
            """
            INSERT INTO contact_sync_meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    def replace_all(self, depts: dict[int, str], users: list[dict[str, Any]]) -> tuple[int, int]:
        now = _utc_now_iso()
        users_by_id = self._index_users(users)
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM org_users")
                conn.execute("DELETE FROM org_depts")
                for dept_id, name in depts.items():
                    conn.execute(
                        "INSERT INTO org_depts (dept_id, name, updated_at) VALUES (?, ?, ?)",
                        (dept_id, name, now),
                    )
                for userid, payload in users_by_id.items():
                    conn.execute(
                        """
                        INSERT INTO org_users (userid, payload_json, dept_ids_json, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            userid,
                            json.dumps(payload, ensure_ascii=False),
                            json.dumps(payload.get("dept_ids") or [], ensure_ascii=False),
                            now,
                        ),
                    )
                self._set_meta(conn, "last_full_sync_at", now)
                self._set_meta(conn, "last_user_scan_at", now)
                self._set_meta(conn, "user_count", str(len(users_by_id)))
                self._set_meta(conn, "dept_count", str(len(depts)))
                conn.commit()
        return 0, 0

    def apply_user_scan(
        self,
        depts: dict[int, str],
        scanned_users: list[dict[str, Any]],
    ) -> tuple[int, int]:
        now = _utc_now_iso()
        scanned_by_id = self._index_users(scanned_users)
        with self._lock:
            with self._connect() as conn:
                previous_ids = {
                    str(row["userid"])
                    for row in conn.execute("SELECT userid FROM org_users").fetchall()
                }
                conn.execute("DELETE FROM org_users")
                conn.execute("DELETE FROM org_depts")
                for dept_id, name in depts.items():
                    conn.execute(
                        "INSERT INTO org_depts (dept_id, name, updated_at) VALUES (?, ?, ?)",
                        (dept_id, name, now),
                    )
                for userid, payload in scanned_by_id.items():
                    conn.execute(
                        """
                        INSERT INTO org_users (userid, payload_json, dept_ids_json, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            userid,
                            json.dumps(payload, ensure_ascii=False),
                            json.dumps(payload.get("dept_ids") or [], ensure_ascii=False),
                            now,
                        ),
                    )
                self._set_meta(conn, "last_user_scan_at", now)
                self._set_meta(conn, "user_count", str(len(scanned_by_id)))
                self._set_meta(conn, "dept_count", str(len(depts)))
                had_full_sync = conn.execute(
                    "SELECT value FROM contact_sync_meta WHERE key = 'last_full_sync_at'"
                ).fetchone()
                if not had_full_sync:
                    self._set_meta(conn, "last_full_sync_at", now)
                conn.commit()
        added = len(set(scanned_by_id) - previous_ids)
        removed = len(previous_ids - set(scanned_by_id))
        return added, removed

    def remove_departments(self, removed_dept_ids: set[int]) -> tuple[int, int]:
        if not removed_dept_ids:
            return 0, 0
        now = _utc_now_iso()
        removed = 0
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT userid, payload_json, dept_ids_json FROM org_users"
                ).fetchall()
                for row in rows:
                    dept_ids = json.loads(str(row["dept_ids_json"] or "[]"))
                    if not isinstance(dept_ids, list):
                        continue
                    remaining = [dept_id for dept_id in dept_ids if int(dept_id) not in removed_dept_ids]
                    if remaining:
                        payload = json.loads(str(row["payload_json"]))
                        if isinstance(payload, dict):
                            payload["dept_ids"] = remaining
                            conn.execute(
                                """
                                UPDATE org_users
                                SET payload_json = ?, dept_ids_json = ?, updated_at = ?
                                WHERE userid = ?
                                """,
                                (
                                    json.dumps(payload, ensure_ascii=False),
                                    json.dumps(remaining, ensure_ascii=False),
                                    now,
                                    str(row["userid"]),
                                ),
                            )
                        continue
                    conn.execute("DELETE FROM org_users WHERE userid = ?", (str(row["userid"]),))
                    removed += 1
                for dept_id in removed_dept_ids:
                    conn.execute("DELETE FROM org_depts WHERE dept_id = ?", (dept_id,))
                self._set_meta(conn, "last_user_scan_at", now)
                row = conn.execute("SELECT COUNT(*) AS cnt FROM org_users").fetchone()
                self._set_meta(conn, "user_count", str(int(row["cnt"]) if row else 0))
                conn.commit()
        return 0, removed

    def upsert_department_users(
        self,
        depts: dict[int, str],
        dept_users: dict[int, list[dict[str, Any]]],
    ) -> tuple[int, int]:
        now = _utc_now_iso()
        existing = {user["userid"]: user for user in self.get_users() if user.get("userid")}
        previous_ids = set(existing)
        merged = dict(existing)

        for dept_id, users in dept_users.items():
            dept_name = depts.get(dept_id, "")
            for user in users:
                userid = str(user.get("userid") or "")
                if not userid:
                    continue
                current = merged.get(userid)
                if current is None:
                    copied = dict(user)
                    dept_ids = [dept_id]
                    copied["dept_ids"] = dept_ids
                    if dept_name and not copied.get("dept_name"):
                        copied["dept_name"] = dept_name
                    merged[userid] = copied
                    continue
                dept_ids = list(current.get("dept_ids") or [])
                if dept_id not in dept_ids:
                    dept_ids.append(dept_id)
                current["dept_ids"] = dept_ids
                if dept_name:
                    current_name = str(current.get("dept_name") or "").strip()
                    current["dept_name"] = (
                        f"{current_name}、{dept_name}".strip("、") if current_name else dept_name
                    )
                for key in ("name", "title", "hired_date"):
                    if not current.get(key) and user.get(key):
                        current[key] = user[key]

        with self._lock:
            with self._connect() as conn:
                for dept_id, name in depts.items():
                    conn.execute(
                        """
                        INSERT INTO org_depts (dept_id, name, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(dept_id) DO UPDATE SET
                            name = excluded.name,
                            updated_at = excluded.updated_at
                        """,
                        (dept_id, name, now),
                    )
                conn.execute("DELETE FROM org_users")
                for userid, payload in merged.items():
                    conn.execute(
                        """
                        INSERT INTO org_users (userid, payload_json, dept_ids_json, updated_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            userid,
                            json.dumps(payload, ensure_ascii=False),
                            json.dumps(payload.get("dept_ids") or [], ensure_ascii=False),
                            now,
                        ),
                    )
                self._set_meta(conn, "last_user_scan_at", now)
                self._set_meta(conn, "user_count", str(len(merged)))
                self._set_meta(conn, "dept_count", str(len(depts)))
                conn.commit()

        added = len(set(merged) - previous_ids)
        removed = len(previous_ids - set(merged))
        return added, removed

    @staticmethod
    def _index_users(users: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for user in users:
            userid = str(user.get("userid") or "")
            if userid:
                indexed[userid] = user
        return indexed


_STORE: ContactCacheStore | None = None
_STORE_LOCK = threading.Lock()


def get_contact_cache_store(db_path: Path | None = None) -> ContactCacheStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None or (db_path is not None and _STORE.db_path != Path(db_path)):
            _STORE = ContactCacheStore(db_path)
        return _STORE
