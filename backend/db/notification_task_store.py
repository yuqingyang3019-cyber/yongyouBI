from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from backend.config import PROJECT_ROOT, optional_env

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def next_run_at(schedule: dict[str, Any], after: datetime | None = None) -> datetime:
    base = (after or _now()).astimezone(SHANGHAI)
    kind = str(schedule.get("kind") or "")
    interval = int(schedule.get("interval") or 1)
    if kind == "minutes":
        return (base + timedelta(minutes=max(1, interval))).astimezone(timezone.utc)
    if kind == "hours":
        return (base + timedelta(hours=max(1, interval))).astimezone(timezone.utc)
    hour = int(schedule.get("hour") or 0)
    minute = int(schedule.get("minute") or 0)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("发送时间无效")
    candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if kind == "daily":
        if candidate <= base:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc)
    if kind == "weekly":
        weekday = int(schedule.get("weekday") or 0)
        if not 0 <= weekday <= 6:
            raise ValueError("星期无效")
        candidate += timedelta(days=(weekday - candidate.weekday()) % 7)
        if candidate <= base:
            candidate += timedelta(days=7)
        return candidate.astimezone(timezone.utc)
    raise ValueError("不支持的发送频率")


def default_notification_db_path() -> Path:
    configured = optional_env("RECEIVABLE_NOTIFICATION_DB")
    return Path(configured) if configured else PROJECT_ROOT / "data" / "receivable_notifications.sqlite"


class NotificationTaskStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else default_notification_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_tasks (
                    id TEXT PRIMARY KEY,
                    creator_userid TEXT NOT NULL,
                    creator_name TEXT NOT NULL,
                    recipients_json TEXT NOT NULL,
                    schedule_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    next_run_at TEXT NOT NULL,
                    last_run_at TEXT NOT NULL DEFAULT '',
                    last_status TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    @staticmethod
    def _task(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "creatorUserid": row["creator_userid"],
            "creatorName": row["creator_name"],
            "recipients": json.loads(row["recipients_json"]),
            "schedule": json.loads(row["schedule_json"]),
            "enabled": bool(row["enabled"]),
            "nextRunAt": row["next_run_at"],
            "lastRunAt": row["last_run_at"],
            "lastStatus": row["last_status"],
            "lastError": row["last_error"],
            "createdAt": row["created_at"],
        }

    def create(
        self,
        creator: dict[str, Any],
        recipients: list[dict[str, str]],
        schedule: dict[str, Any],
    ) -> dict[str, Any]:
        now = _now()
        task_id = uuid.uuid4().hex
        next_at = next_run_at(schedule, now)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO notification_tasks
                (id, creator_userid, creator_name, recipients_json, schedule_json,
                 enabled, next_run_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    task_id,
                    creator["userid"],
                    creator.get("name") or creator["userid"],
                    json.dumps(recipients, ensure_ascii=False),
                    json.dumps(schedule, ensure_ascii=False),
                    _iso(next_at),
                    _iso(now),
                    _iso(now),
                ),
            )
            conn.commit()
        return self.get(task_id, str(creator["userid"]))

    def get(self, task_id: str, creator_userid: str | None = None) -> dict[str, Any]:
        query = "SELECT * FROM notification_tasks WHERE id = ?"
        params: list[Any] = [task_id]
        if creator_userid is not None:
            query += " AND creator_userid = ?"
            params.append(creator_userid)
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        if row is None:
            raise KeyError(task_id)
        return self._task(row)

    def list_for_user(self, creator_userid: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM notification_tasks WHERE creator_userid = ? ORDER BY created_at DESC",
                (creator_userid,),
            ).fetchall()
        return [self._task(row) for row in rows]

    def set_enabled(self, task_id: str, creator_userid: str, enabled: bool) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            result = conn.execute(
                """
                UPDATE notification_tasks
                SET enabled = ?, next_run_at = ?, updated_at = ?
                WHERE id = ? AND creator_userid = ?
                """,
                (
                    int(enabled),
                    _iso(next_run_at(self.get(task_id, creator_userid)["schedule"])) if enabled else "",
                    _iso(_now()),
                    task_id,
                    creator_userid,
                ),
            )
            conn.commit()
        if result.rowcount != 1:
            raise KeyError(task_id)
        return self.get(task_id, creator_userid)

    def delete(self, task_id: str, creator_userid: str) -> None:
        with self._lock, self._connect() as conn:
            result = conn.execute(
                "DELETE FROM notification_tasks WHERE id = ? AND creator_userid = ?",
                (task_id, creator_userid),
            )
            conn.commit()
        if result.rowcount != 1:
            raise KeyError(task_id)

    def claim_due(self, now: datetime | None = None) -> list[dict[str, Any]]:
        current = now or _now()
        claimed: list[dict[str, Any]] = []
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT * FROM notification_tasks WHERE enabled = 1 AND next_run_at <= ? ORDER BY next_run_at",
                (_iso(current),),
            ).fetchall()
            for row in rows:
                schedule = json.loads(row["schedule_json"])
                following = next_run_at(schedule, current)
                updated = conn.execute(
                    """
                    UPDATE notification_tasks
                    SET next_run_at = ?, last_run_at = ?, last_status = 'running',
                        last_error = '', updated_at = ?
                    WHERE id = ? AND enabled = 1 AND next_run_at = ?
                    """,
                    (_iso(following), _iso(current), _iso(current), row["id"], row["next_run_at"]),
                )
                if updated.rowcount == 1:
                    claimed.append(self._task(row))
            conn.commit()
        return claimed

    def record_result(self, task_id: str, *, success: bool, error: str = "") -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE notification_tasks
                SET last_run_at = ?, last_status = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    _iso(_now()),
                    "success" if success else "failed",
                    error[:500],
                    _iso(_now()),
                    task_id,
                ),
            )
            conn.commit()


_STORE: NotificationTaskStore | None = None
_STORE_LOCK = threading.Lock()


def get_notification_task_store() -> NotificationTaskStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = NotificationTaskStore()
        return _STORE
