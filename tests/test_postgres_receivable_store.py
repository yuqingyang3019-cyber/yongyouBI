from __future__ import annotations

import os
import unittest

from backend.db.receivable_store import ReceivableCacheStore


@unittest.skipUnless(os.getenv("RECEIVABLE_TEST_DATABASE_URL"), "未配置 PostgreSQL 集成测试库")
class PostgresReceivableStoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = ReceivableCacheStore(os.environ["RECEIVABLE_TEST_DATABASE_URL"])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.store.close()

    def setUp(self) -> None:
        with self.store._pool.connection() as conn:
            conn.execute(
                """
                TRUNCATE receivable_raw.sale_invoices,
                         receivable_raw.sale_contracts,
                         receivable_raw.collections,
                         receivable_raw.sync_meta,
                         receivable_analytics.invoice_facts
                """
            )

    def test_upsert_and_fact_replacement(self) -> None:
        self.store.upsert_sale_invoice(
            "inv-1",
            "2026-07",
            "v1",
            {"id": "inv-1", "code": "INV-1", "agentName": "测试客户"},
        )
        self.store.upsert_sale_invoice(
            "inv-1",
            "2026-07",
            "v2",
            {"id": "inv-1", "code": "INV-1", "agentName": "更新客户"},
        )
        self.assertEqual(self.store.count_all_sale_invoices(), 1)
        self.assertEqual(self.store.get_sale_invoice_list_ts_map()["inv-1"], "v2")
        self.assertEqual(self.store.get_all_sale_invoices()[0].payload["agentName"], "更新客户")

        self.store.replace_receivable_facts(
            [
                {
                    "invoiceId": "inv-1",
                    "invoiceCode": "INV-1",
                    "contractCode": "C-1",
                    "customer": "更新客户",
                    "salesman": "张三",
                    "taxAmount": 1000,
                    "collectedAmount": 400,
                    "outstanding": 600,
                    "collectionStatus": "partial",
                    "matchQuality": "partial_exact",
                    "auditTime": "2026-06-01 00:00:00",
                    "paymentTermDays": 30,
                    "dueDate": "2026-07-01",
                    "daysUntilDue": -15,
                    "calendarStatus": "overdue",
                    "trueStatus": "true_overdue",
                }
            ]
        )
        with self.store._pool.connection() as conn:
            fact = conn.execute(
                "SELECT outstanding, true_status FROM receivable_analytics.invoice_facts"
            ).fetchone()
        self.assertEqual(float(fact["outstanding"]), 600)
        self.assertEqual(fact["true_status"], "true_overdue")


if __name__ == "__main__":
    unittest.main()
