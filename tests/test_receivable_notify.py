from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from backend.services.overdue_service import build_receivable_charts
from backend.services.receivable_notify_service import (
    build_overdue_digest_markdown,
    build_overdue_risk_card_data,
    send_receivable_digest,
)


class ReceivableChartsTest(unittest.TestCase):
    def test_build_receivable_charts_buckets_and_top_customers(self) -> None:
        rows = [
            {"trueStatus": "true_overdue", "daysUntilDue": -5, "outstanding": 1000, "customer": "客户A"},
            {"trueStatus": "true_overdue", "daysUntilDue": -20, "outstanding": 2000, "customer": "客户A"},
            {"trueStatus": "true_overdue", "daysUntilDue": -120, "outstanding": 500, "customer": "客户B"},
            {"trueStatus": "upcoming", "daysUntilDue": 3, "outstanding": 800, "customer": "客户C"},
        ]
        charts = build_receivable_charts(rows)
        self.assertEqual(len(charts["agingBuckets"]), 4)
        self.assertEqual(charts["agingBuckets"][0]["count"], 1)
        self.assertEqual(charts["agingBuckets"][1]["count"], 1)
        self.assertEqual(charts["topCustomers"][0]["customer"], "客户A")
        self.assertEqual(charts["topCustomers"][0]["amount"], 3000)


class ReceivableNotifyTest(unittest.TestCase):
    def test_build_overdue_digest_markdown(self) -> None:
        rows = [
            {
                "trueStatus": "true_overdue",
                "status": "overdue",
                "customer": "客户A",
                "invoiceCode": "INV-001",
                "daysUntilDue": -45,
                "taxAmount": 520000,
                "outstanding": 520000,
            },
            {
                "trueStatus": "upcoming",
                "status": "upcoming",
                "customer": "客户B",
                "invoiceCode": "INV-002",
                "daysUntilDue": 3,
                "taxAmount": 120000,
            },
        ]
        summary = {
            "overdue": {"count": 1, "amount": 520000},
            "upcoming": {"count": 1, "amount": 120000},
        }
        title, text = build_overdue_digest_markdown(
            rows,
            summary,
            today=date(2026, 7, 15),
            top_n=5,
            include_upcoming=True,
        )
        self.assertIn("2026-07-15", title)
        self.assertIn("客户A", text)
        self.assertIn("INV-001", text)
        self.assertIn("即将逾期", text)

    def test_digest_rejects_more_than_twenty_recipients(self) -> None:
        with self.assertRaisesRegex(ValueError, "最多选择 20 人"):
            send_receivable_digest([f"u{index}" for index in range(21)], dry_run=True)

    def test_build_overdue_risk_card_data(self) -> None:
        self.assertEqual(
            build_overdue_risk_card_data({"overdue": {"count": 2, "amount": 1234.5}}),
            {"overdue_count": "2", "overdue_amount": "¥1,234.50"},
        )

    @patch("backend.services.receivable_notify_service.send_robot_markdown_to_users")
    @patch("backend.services.receivable_notify_service.DingTalkOpenApiClient")
    @patch("backend.services.receivable_notify_service.load_receivable_snapshot")
    def test_send_scheduled_digest_dry_run(
        self,
        snapshot_mock,
        _client_cls_mock,
        send_mock,
    ) -> None:
        snapshot_mock.return_value = (
            [{"trueStatus": "true_overdue", "status": "overdue", "customer": "客户A", "invoiceCode": "INV-1", "daysUntilDue": -10, "taxAmount": 100, "outstanding": 100}],
            {"overdue": {"count": 1, "amount": 100}, "upcoming": {"count": 0, "amount": 0}},
            {"agingBuckets": [], "topCustomers": []},
        )
        result = send_receivable_digest(["u1"], dry_run=True)
        self.assertTrue(result["dryRun"])
        self.assertIn("title", result)
        send_mock.assert_not_called()

    @patch("backend.services.receivable_notify_service.send_robot_markdown_to_users", return_value={"sent": 1, "total": 1})
    @patch("backend.services.receivable_notify_service.DingTalkOpenApiClient.from_env")
    @patch("backend.services.receivable_notify_service.load_receivable_snapshot")
    def test_send_scheduled_digest_sends_message(
        self,
        snapshot_mock,
        client_from_env_mock,
        send_mock,
    ) -> None:
        snapshot_mock.return_value = (
            [{"trueStatus": "true_overdue", "status": "overdue", "customer": "客户A", "invoiceCode": "INV-1", "daysUntilDue": -10, "taxAmount": 100, "outstanding": 100}],
            {"overdue": {"count": 1, "amount": 100}, "upcoming": {"count": 0, "amount": 0}},
            {"agingBuckets": [], "topCustomers": []},
        )
        client_from_env_mock.return_value = object()
        result = send_receivable_digest(["u1"])
        self.assertEqual(result["overdueCount"], 1)
        send_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
