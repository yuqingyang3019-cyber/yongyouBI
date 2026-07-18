from __future__ import annotations

import unittest
import warnings
from datetime import date
from unittest.mock import patch

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

from backend.services.overdue_service import (
    TRUE_OVERDUE_STATUS,
    build_contract_receivable_summary,
    build_receivable_charts,
    build_receivable_rows,
    classify_status,
)
from backend.services import receivable_sync_service
from backend.services.receivable_match_service import allocate_collections_to_invoices
from backend.services.receivable_sync_service import RECEIVABLE_SYNC_KEY, invoice_contract_ref
from backend.services.sync_service import rolling_12m_range
from tests.receivable_store_fake import InMemoryReceivableStore


class ReceivableRulesTest(unittest.TestCase):
    def test_classify_status(self) -> None:
        today = date(2026, 7, 10)
        self.assertEqual(classify_status(date(2026, 7, 1), today)[0], "overdue")
        self.assertEqual(classify_status(date(2026, 7, 15), today)[0], "upcoming")
        self.assertEqual(classify_status(date(2026, 8, 1), today)[0], "normal")

    def test_invoice_contract_ref_uses_sact_code(self) -> None:
        payload = {
            "saleInvoiceDetails": [
                {"sactCode": "SACT001", "firstupcode": "SACT001", "sactId": "99"}
            ]
        }
        self.assertEqual(invoice_contract_ref(payload), ("SACT001", "99"))

    def test_build_receivable_rows_splits_pending_and_unmatched(self) -> None:
        invoices = [
            {
                "id": "inv-overdue",
                "code": "INV-001",
                "agentName": "客户A",
                "auditor": "张三",
                "auditTime": "2025-01-01 10:00:00",
                "oriSum": 1000,
                "saleInvoiceDetails": [{"sactCode": "SACT001", "sactId": "c1"}],
            },
            {
                "id": "inv-pending",
                "code": "INV-002",
                "agentName": "客户B",
                "oriSum": 500,
                "saleInvoiceDetails": [{"sactCode": "SACT002", "sactId": "c2"}],
            },
            {
                "id": "inv-unmatched",
                "code": "INV-003",
                "agentName": "客户C",
                "auditTime": "2025-02-01 10:00:00",
                "oriSum": 300,
                "saleInvoiceDetails": [{"sactCode": "SACT-MISSING", "sactId": "missing"}],
            },
        ]
        contracts = {
            "SACT001": {
                "code": "SACT001",
                "receiveAgreement": [{"accountDay": 30, "receivePercent": 100}],
            }
        }

        rows, pending, unmatched, settled, summary = build_receivable_rows(
            invoices,
            contracts,
            today=date(2026, 7, 10),
            statuses={"overdue", "upcoming", "normal"},
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["invoiceCode"], "INV-001")
        self.assertEqual(rows[0]["dueDate"], "2025-01-31")
        self.assertEqual(rows[0]["trueStatus"], TRUE_OVERDUE_STATUS)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["invoiceCode"], "INV-002")
        self.assertEqual(len(unmatched), 1)
        self.assertEqual(unmatched[0]["invoiceCode"], "INV-003")
        self.assertEqual(len(settled), 0)
        self.assertEqual(summary["trueOverdue"]["count"], 1)
        self.assertEqual(summary["pendingAudit"]["count"], 1)
        self.assertEqual(summary["unmatched"]["count"], 1)

    def test_settled_invoice_not_true_overdue(self) -> None:
        invoices = [
            {
                "id": "inv1",
                "code": "INV-001",
                "agentName": "客户A",
                "auditTime": "2025-01-01 10:00:00",
                "oriSum": 1000,
                "saleInvoiceDetails": [
                    {"sactCode": "SACT001", "sactId": "c1", "orderNo": "ORD-1"}
                ],
            }
        ]
        contracts = {
            "SACT001": {
                "code": "SACT001",
                "receiveAgreement": [{"accountDay": 30, "receivePercent": 100}],
            }
        }
        collections = [
            {
                "id": "rec1",
                "code": "REC-001",
                "verifyState": 2,
                "bodyItem": [
                    {"orderNo": "ORD-1", "oriTaxIncludedAmount": 1000, "customerName": "客户A"}
                ],
            }
        ]
        allocations = allocate_collections_to_invoices(invoices, collections)
        rows, _pending, _unmatched, settled, summary = build_receivable_rows(
            invoices,
            contracts,
            allocations=allocations,
            today=date(2026, 7, 10),
            statuses={"overdue", "upcoming", "normal"},
        )

        self.assertEqual(len(rows), 0)
        self.assertEqual(len(settled), 1)
        self.assertEqual(settled[0]["collectionStatus"], "settled")
        self.assertEqual(summary["settled"]["count"], 1)
        self.assertEqual(summary["trueOverdue"]["count"], 0)
        self.assertEqual(summary["calendarOverdue"]["count"], 1)

    def test_partial_collection_stays_true_overdue(self) -> None:
        invoices = [
            {
                "id": "inv1",
                "code": "INV-001",
                "agentName": "客户A",
                "auditTime": "2025-01-01 10:00:00",
                "oriSum": 1000,
                "saleInvoiceDetails": [
                    {"sactCode": "SACT001", "sactId": "c1", "orderNo": "ORD-1"}
                ],
            }
        ]
        contracts = {
            "SACT001": {
                "code": "SACT001",
                "receiveAgreement": [{"accountDay": 30, "receivePercent": 100}],
            }
        }
        collections = [
            {
                "id": "rec1",
                "code": "REC-001",
                "bodyItem": [{"orderNo": "ORD-1", "oriTaxIncludedAmount": 400}],
            }
        ]
        allocations = allocate_collections_to_invoices(invoices, collections)
        rows, _pending, _unmatched, _settled, summary = build_receivable_rows(
            invoices,
            contracts,
            allocations=allocations,
            today=date(2026, 7, 10),
            statuses={"overdue", "upcoming", "normal"},
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["collectedAmount"], 400)
        self.assertEqual(rows[0]["outstanding"], 600)
        self.assertEqual(rows[0]["collectionStatus"], "partial")
        self.assertEqual(rows[0]["trueStatus"], TRUE_OVERDUE_STATUS)
        self.assertEqual(summary["trueOverdue"]["amount"], 600)

    def test_build_receivable_charts_from_rows(self) -> None:
        rows = [
            {
                "trueStatus": TRUE_OVERDUE_STATUS,
                "daysUntilDue": -3,
                "outstanding": 100,
                "customer": "客户A",
            }
        ]
        charts = build_receivable_charts(rows)
        self.assertEqual(charts["agingBuckets"][0]["count"], 1)
        self.assertEqual(charts["topCustomers"][0]["customer"], "客户A")

    def test_build_contract_receivable_summary(self) -> None:
        rows = [
            {
                "contractCode": "SACT001",
                "customer": "客户A",
                "taxAmount": 1000,
                "collectedAmount": 400,
                "outstanding": 600,
                "trueStatus": TRUE_OVERDUE_STATUS,
            },
            {
                "contractCode": "SACT001",
                "customer": "客户A",
                "taxAmount": 500,
                "collectedAmount": 500,
                "outstanding": 0,
                "trueStatus": "settled",
            },
        ]
        summary = build_contract_receivable_summary(rows)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["receivableAmount"], 1500)
        self.assertEqual(summary[0]["collectedAmount"], 900)
        self.assertEqual(summary[0]["outstanding"], 600)
        self.assertEqual(summary[0]["trueOverdueAmount"], 600)
        self.assertEqual(summary[0]["trueOverdueCount"], 1)

    def test_rolling_12m_range(self) -> None:
        start, end = rolling_12m_range(date(2026, 7, 10))
        self.assertEqual(start, "2025-08-01")
        self.assertEqual(end, "2026-07-11")


class ReceivableSyncTest(unittest.TestCase):
    def test_sync_only_fetches_changed_invoices_and_contracts(self) -> None:
        with self.subTest("in-memory repository"):
            store = InMemoryReceivableStore()
            store.upsert_sale_invoice(
                "inv1",
                "2026-07",
                "same",
                {
                    "id": "inv1",
                    "code": "INV1",
                    "saleInvoiceDetails": [{"sactCode": "SACT1", "sactId": "c1"}],
                },
            )

            listed = type(
                "Page",
                (),
                {
                    "records": [
                        {"id": "inv1", "pubts": "same", "code": "INV1", "vouchdate": "2026-07-01"},
                        {"id": "inv2", "pubts": "new", "code": "INV2", "vouchdate": "2026-07-02"},
                    ]
                },
            )()

            with (
                patch.object(receivable_sync_service, "list_sale_invoices", return_value=listed),
                patch.object(
                    receivable_sync_service,
                    "get_sale_invoice_by_id",
                    return_value={
                        "id": "inv2",
                        "code": "INV2",
                        "saleInvoiceDetails": [{"sactCode": "SACT2", "sactId": "c2"}],
                    },
                ) as invoice_detail_mock,
                patch.object(
                    receivable_sync_service,
                    "get_sale_contract_by_id",
                    return_value={"id": "c2", "code": "SACT2", "receiveAgreement": []},
                ) as contract_detail_mock,
                patch.object(receivable_sync_service, "sleep"),
                patch.object(
                    receivable_sync_service,
                    "get_settings",
                    return_value=type("S", (), {"contract_detail_sync_interval": 0})(),
                ),
            ):
                receivable_sync_service._STATES.clear()
                receivable_sync_service._THREADS.clear()
                receivable_sync_service._run_sync(RECEIVABLE_SYNC_KEY, store)

            invoice_detail_mock.assert_called_once_with("inv2")
            contract_detail_mock.assert_called_once_with("c2")
            self.assertEqual(store.get_sale_invoice_list_ts_map()["inv2"], "new")
            self.assertIn("c2", store.get_sale_contract_list_ts_map())
            status = receivable_sync_service.get_receivable_sync_status(RECEIVABLE_SYNC_KEY, store)
            self.assertEqual(status["status"], "done")
            self.assertEqual(status["doneCount"], 1)
            self.assertEqual(status["skipped"], 1)
            self.assertEqual(status["cachedCount"], 2)


if __name__ == "__main__":
    unittest.main()
