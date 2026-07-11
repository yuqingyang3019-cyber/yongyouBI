from __future__ import annotations

import tempfile
import unittest
import warnings
from datetime import date
from pathlib import Path
from unittest.mock import patch

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

from backend.db.cache_store import ContractCacheStore
from backend.services.overdue_service import build_rows_from_payloads, classify_status, extract_attachments
from backend.services import sync_service
from backend.services.sync_service import ROLLING_SYNC_KEY, rolling_12m_range


class OverdueRulesTest(unittest.TestCase):
    def test_classify_status(self) -> None:
        today = date(2026, 7, 10)
        self.assertEqual(classify_status(date(2026, 7, 1), today)[0], "overdue")
        self.assertEqual(classify_status(date(2026, 7, 15), today)[0], "upcoming")
        self.assertEqual(classify_status(date(2026, 8, 1), today)[0], "normal")

    def test_build_rows_splits_paid_and_ranks_unpaid(self) -> None:
        payloads = [
            {
                "id": "1",
                "code": "CT-001",
                "supplierSupName": "供应商A",
                "purPersonName": "张三",
                "saleStampFileUrls": ["https://example.com/a.pdf"],
                "signedFileId": "file-1",
                "contractPayTermList": [
                    {
                        "payPeriod": 1,
                        "dueDate": "2026-07-01",
                        "payTaxMoney": 1000,
                        "practicalPaymentmny": 200,
                    },
                    {
                        "payPeriod": 2,
                        "dueDate": "2026-07-12",
                        "payTaxMoney": 500,
                        "practicalPaymentmny": 500,
                    },
                    {
                        "payPeriod": 3,
                        "dueDate": "",
                        "payTaxMoney": 300,
                        "practicalPaymentmny": 0,
                    },
                    {
                        "payPeriod": 4,
                        "dueDate": "2026-07-05",
                        "payTaxMoney": 2000,
                        "practicalPaymentmny": 0,
                    },
                ],
            }
        ]

        unpaid, paid, summary = build_rows_from_payloads(
            payloads,
            today=date(2026, 7, 10),
            statuses={"overdue", "upcoming", "normal"},
        )

        self.assertEqual(len(unpaid), 2)
        self.assertEqual(unpaid[0]["dueDate"], "2026-07-01")
        self.assertEqual(unpaid[0]["unpaidAmount"], 800.0)
        self.assertEqual(unpaid[1]["dueDate"], "2026-07-05")
        self.assertEqual(unpaid[1]["unpaidAmount"], 2000.0)
        self.assertEqual(len(paid), 1)
        self.assertEqual(paid[0]["status"], "paid")
        self.assertEqual(summary["overdue"]["count"], 2)
        self.assertEqual(summary["paid"]["count"], 1)
        self.assertEqual(len(unpaid[0]["attachments"]), 2)

    def test_extract_attachments_prefers_urls(self) -> None:
        attachments = extract_attachments(
            {
                "saleStampFileUrls": ["https://cdn.example.com/stamp.pdf"],
                "ectFilePath": "https://cdn.example.com/ect.pdf",
                "signedFileId": "abc",
            }
        )
        self.assertEqual(len(attachments), 3)
        self.assertTrue(any(item["url"].endswith("stamp.pdf") for item in attachments))

    def test_rolling_12m_range(self) -> None:
        start, end = rolling_12m_range(date(2026, 7, 10))
        self.assertEqual(start, "2025-08-01")
        self.assertEqual(end, "2026-07-11")


class CacheAndSyncTest(unittest.TestCase):
    def test_cache_store_get_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ContractCacheStore(Path(tmp) / "cache.sqlite")
            store.upsert("c1", "2026-06", "ts-1", {"id": "c1", "code": "A"})
            store.upsert("c2", "2026-07", "ts-2", {"id": "c2", "code": "B"})

            mapping = store.get_list_ts_map(None)
            self.assertEqual(mapping["c1"], "ts-1")
            self.assertEqual(store.count_all(), 2)
            self.assertEqual(len(store.get_all()), 2)

    def test_sync_only_fetches_changed_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ContractCacheStore(Path(tmp) / "cache.sqlite")
            store.upsert("c1", "2026-07", "same", {"id": "c1", "code": "OLD"})

            listed = type(
                "Page",
                (),
                {
                    "records": [
                        {"id": "c1", "ts": "same", "code": "CT1", "createTime": "2026-07-01"},
                        {"id": "c2", "ts": "new", "code": "CT2", "createTime": "2026-07-02"},
                    ]
                },
            )()

            with (
                patch.object(sync_service, "list_contracts", return_value=listed),
                patch.object(
                    sync_service,
                    "get_contract_by_id",
                    return_value={"id": "c2", "code": "CT2", "contractPayTermList": [], "createTime": "2026-07-02"},
                ) as detail_mock,
                patch.object(sync_service, "sleep"),
                patch.object(
                    sync_service,
                    "get_settings",
                    return_value=type("S", (), {"contract_detail_sync_interval": 0})(),
                ),
            ):
                sync_service._STATES.clear()
                sync_service._THREADS.clear()
                sync_service._run_sync(ROLLING_SYNC_KEY, store)

            detail_mock.assert_called_once_with("c2")
            self.assertEqual(store.get_list_ts_map(None)["c2"], "new")
            status = sync_service.get_sync_status(None, store)
            self.assertEqual(status["status"], "done")
            self.assertEqual(status["scope"], ROLLING_SYNC_KEY)
            self.assertEqual(status["doneCount"], 1)
            self.assertEqual(status["skipped"], 1)
            self.assertEqual(status["cachedCount"], 2)


if __name__ == "__main__":
    unittest.main()
