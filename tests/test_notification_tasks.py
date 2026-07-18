from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.db.notification_task_store import NotificationTaskStore, next_run_at


class NotificationTaskStoreTest(unittest.TestCase):
    def test_next_run_for_interval_and_weekly(self) -> None:
        base = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)
        interval = next_run_at({"kind": "minutes", "interval": 15}, base)
        self.assertEqual(interval, datetime(2026, 7, 16, 12, 15, tzinfo=timezone.utc))
        weekly = next_run_at(
            {"kind": "weekly", "weekday": 4, "hour": 9, "minute": 0, "interval": 1},
            base,
        )
        self.assertGreater(weekly, base)

    def test_create_claim_and_creator_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = NotificationTaskStore(Path(directory) / "tasks.sqlite")
            task = store.create(
                {"userid": "creator", "name": "管理员"},
                [{"userid": "u1", "name": "张三"}],
                {"kind": "minutes", "interval": 1, "hour": 9, "minute": 0, "weekday": 0},
            )
            self.assertEqual(len(store.list_for_user("creator")), 1)
            self.assertEqual(store.list_for_user("other"), [])
            due = datetime.fromisoformat(task["nextRunAt"])
            self.assertEqual(len(store.claim_due(due)), 1)
            self.assertEqual(store.claim_due(due), [])
            store.record_result(task["id"], success=False, error="发送失败")
            updated = store.get(task["id"], "creator")
            self.assertEqual(updated["lastStatus"], "failed")


if __name__ == "__main__":
    unittest.main()
