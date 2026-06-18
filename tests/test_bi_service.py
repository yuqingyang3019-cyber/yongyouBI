from __future__ import annotations

import unittest
import warnings
from types import SimpleNamespace
from unittest.mock import patch

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

from backend.services import bi_service
from backend.services.bi_service import DocumentConfig, execution_summary, month_range


def page(records: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        records=records,
        record_count=len(records),
        page_count=1,
        fetched_pages=1,
        truncated=False,
    )


class BiServiceTest(unittest.TestCase):
    def test_month_range_uses_full_calendar_month(self) -> None:
        start, end = month_range("2026-02")

        self.assertEqual(start, "2026-02-01 00:00:00")
        self.assertEqual(end, "2026-02-28 23:59:59")

    def test_execution_summary_deduplicates_documents_and_groups_by_person(self) -> None:
        configs = {
            "contract": DocumentConfig(
                key="contract",
                label="采购合同",
                fetcher=lambda start, end: page(
                    [
                        {"id": "c1", "purPersonName": "张三", "taxMoney": "100.50"},
                        {"id": "c1", "purPersonName": "张三", "taxMoney": "100.50"},
                        {"id": "c2", "purPersonName": "李四", "taxMoney": "200"},
                    ]
                ),
                person_fields=("purPersonName",),
                amount_fields=("taxMoney",),
                id_fields=("id",),
            ),
            "payment_apply": DocumentConfig(
                key="payment_apply",
                label="付款申请单",
                fetcher=lambda start, end: page(
                    [
                        {"id": "p1", "staff_name": "张三", "oriAmount": "300"},
                        {"id": "p2", "staff_name": "", "oriAmount": "50"},
                    ]
                ),
                person_fields=("staff_name",),
                amount_fields=("oriAmount",),
                id_fields=("id",),
            ),
        }

        with patch.object(bi_service, "DOCUMENTS", configs):
            summary = execution_summary(month="2026-06")

        self.assertEqual(summary["totals"]["count"], 4)
        self.assertEqual(summary["totals"]["amount"], 650.5)
        self.assertEqual(summary["totals"]["missingPersonCount"], 1)
        self.assertEqual(summary["byDocumentType"][0]["count"], 2)
        self.assertEqual(summary["byDocumentType"][0]["amount"], 300.5)
        self.assertEqual(summary["byDocumentType"][1]["count"], 2)

        people = {item["person"]: item for item in summary["byPerson"]}
        self.assertEqual(people["张三"]["count"], 2)
        self.assertEqual(people["张三"]["amount"], 400.5)
        self.assertEqual(people["李四"]["amount"], 200.0)
        self.assertEqual(people["未分配"]["amount"], 50.0)

    def test_execution_summary_keeps_other_documents_when_one_fetcher_fails(self) -> None:
        def raise_error(start: str, end: str) -> SimpleNamespace:
            raise RuntimeError("接口超时")

        configs = {
            "ok": DocumentConfig(
                key="ok",
                label="正常单据",
                fetcher=lambda start, end: page([{"id": "ok1", "owner": "王五", "amount": 80}]),
                person_fields=("owner",),
                amount_fields=("amount",),
                id_fields=("id",),
            ),
            "failed": DocumentConfig(
                key="failed",
                label="失败单据",
                fetcher=raise_error,
                person_fields=("owner",),
                amount_fields=("amount",),
                id_fields=("id",),
            ),
        }

        with patch.object(bi_service, "DOCUMENTS", configs):
            summary = execution_summary(month="2026-06")

        self.assertEqual(summary["totals"]["count"], 1)
        self.assertEqual(summary["totals"]["amount"], 80.0)
        failed = next(item for item in summary["byDocumentType"] if item["type"] == "failed")
        self.assertEqual(failed["error"], "接口超时")

    def test_execution_summary_supports_person_filters(self) -> None:
        configs = {
            "purchase_order": DocumentConfig(
                key="purchase_order",
                label="采购订单",
                fetcher=lambda start, end: page(
                    [
                        {"id": "o1", "operator_name": "张三", "oriSum": "100"},
                        {"id": "o2", "operator_name": "李四", "oriSum": "200"},
                        {"id": "o3", "operator_name": "王五", "oriSum": "300"},
                    ]
                ),
                person_fields=("operator_name",),
                amount_fields=("oriSum",),
                id_fields=("id",),
            )
        }

        with patch.object(bi_service, "DOCUMENTS", configs):
            summary = execution_summary(month="2026-06", persons=["张"], person_match_mode="contains", top_n=1)

        self.assertEqual(summary["totals"]["count"], 1)
        self.assertEqual(summary["totals"]["amount"], 100.0)
        self.assertEqual(summary["query"]["persons"], ["张"])
        self.assertEqual(len(summary["byPersonTopN"]), 1)
        self.assertEqual(summary["byPersonTopN"][0]["person"], "张三")

    def test_execution_summary_uses_cache_and_refresh(self) -> None:
        call_count = {"value": 0}

        def fetcher(start: str, end: str) -> SimpleNamespace:
            call_count["value"] += 1
            return page([{"id": f"r{call_count['value']}", "owner": "张三", "amount": 10}])

        configs = {
            "test_doc": DocumentConfig(
                key="test_doc",
                label="测试单据",
                fetcher=fetcher,
                person_fields=("owner",),
                amount_fields=("amount",),
                id_fields=("id",),
            )
        }

        with patch.object(bi_service, "DOCUMENTS", configs), patch.object(bi_service, "_SUMMARY_CACHE", {}):
            first = execution_summary(month="2026-06")
            second = execution_summary(month="2026-06")
            refreshed = execution_summary(month="2026-06", refresh=True)

        self.assertEqual(call_count["value"], 2)
        self.assertFalse(first["meta"]["fromCache"])
        self.assertTrue(second["meta"]["fromCache"])
        self.assertFalse(refreshed["meta"]["fromCache"])


if __name__ == "__main__":
    unittest.main()
