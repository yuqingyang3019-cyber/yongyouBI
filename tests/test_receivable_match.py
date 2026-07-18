from __future__ import annotations

import unittest

from backend.services.receivable_match_service import allocate_collections_to_invoices


class ReceivableMatchTest(unittest.TestCase):
    def test_order_no_exact_match(self) -> None:
        invoices = [
            {
                "id": "inv1",
                "code": "INV-001",
                "agentName": "客户A",
                "oriSum": 1000,
                "saleInvoiceDetails": [
                    {"sactCode": "SACT001", "orderNo": "ORD-100"}
                ],
            }
        ]
        collections = [
            {
                "id": "rec1",
                "code": "REC-001",
                "bodyItem": [{"orderNo": "ORD-100", "oriTaxIncludedAmount": 300}],
            }
        ]
        allocations = allocate_collections_to_invoices(invoices, collections)
        self.assertEqual(allocations["inv1"].collected_amount, 300)
        self.assertEqual(allocations["inv1"].match_quality, "partial_exact")
        self.assertEqual(allocations["inv1"].evidence[0].collection_code, "REC-001")
        self.assertEqual(allocations["inv1"].evidence[0].matched_field, "收款订单号 = 发票订单号")

    def test_contract_customer_fifo_fallback(self) -> None:
        invoices = [
            {
                "id": "inv1",
                "code": "INV-001",
                "agentName": "客户A",
                "auditTime": "2025-01-01 10:00:00",
                "oriSum": 1000,
                "saleInvoiceDetails": [{"sactCode": "SACT001"}],
            },
            {
                "id": "inv2",
                "code": "INV-002",
                "agentName": "客户A",
                "auditTime": "2025-02-01 10:00:00",
                "oriSum": 500,
                "saleInvoiceDetails": [{"sactCode": "SACT001"}],
            },
        ]
        collections = [
            {
                "id": "rec1",
                "code": "REC-001",
                "customerName": "客户A",
                "billDate": "2025-03-01",
                "bodyItem": [{"oriTaxIncludedAmount": 1200, "customerName": "客户A"}],
            }
        ]
        allocations = allocate_collections_to_invoices(invoices, collections)
        self.assertEqual(allocations["inv1"].collected_amount, 1000)
        self.assertEqual(allocations["inv2"].collected_amount, 200)
        self.assertEqual(allocations["inv1"].match_quality, "estimated")
        self.assertEqual(allocations["inv1"].evidence[0].rule, "客户内按时间分配")


    def test_contract_no_match(self) -> None:
        invoices = [
            {
                "id": "inv1",
                "code": "INV-001",
                "agentName": "客户A",
                "auditTime": "2025-01-01 10:00:00",
                "oriSum": 1000,
                "saleInvoiceDetails": [{"sactCode": "SACT001"}],
            }
        ]
        collections = [
            {
                "id": "rec1",
                "code": "REC-001",
                "contractNo": "SACT001",
                "bodyItem": [{"contractNo": "SACT001", "oriTaxIncludedAmount": 1000, "customerName": "客户A"}],
            }
        ]
        allocations = allocate_collections_to_invoices(invoices, collections)
        self.assertEqual(allocations["inv1"].collected_amount, 1000)
        self.assertEqual(allocations["inv1"].match_quality, "contract")


if __name__ == "__main__":
    unittest.main()
