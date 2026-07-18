from __future__ import annotations

import unittest
import warnings
from unittest.mock import patch

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

from backend.clients.yonyou import sales


class YonyouSalesClientTest(unittest.TestCase):
    @patch("backend.clients.yonyou.pagination.yonyou_post")
    def test_list_sale_contracts_posts_expected_payload(self, mock_post) -> None:
        mock_post.return_value = {
            "code": "200",
            "data": {
                "recordList": [{"id": "1", "code": "SACT001"}],
                "recordCount": 1,
                "pageCount": 1,
            },
        }

        result = sales.list_sale_contracts("2026-01-01 00:00:00", "2026-01-31 23:59:59")

        self.assertEqual(result.records[0]["code"], "SACT001")
        mock_post.assert_called_once()
        path, payload = mock_post.call_args.args
        self.assertEqual(path, "/sd/sact/list")
        self.assertEqual(payload["open_vouchdate_begin"], "2026-01-01 00:00:00")
        self.assertTrue(payload["isSum"])

    @patch("backend.clients.yonyou.sales.yonyou_get")
    def test_get_sale_contract_by_id_uses_get_detail_path(self, mock_get) -> None:
        mock_get.return_value = {"code": "200", "data": {"id": "9", "code": "SACT009"}}

        data = sales.get_sale_contract_by_id("9")

        self.assertEqual(data["code"], "SACT009")
        mock_get.assert_called_once_with("/yonbip/sd/sact/detail", {"id": "9"})

    @patch("backend.clients.yonyou.pagination.yonyou_post")
    def test_list_sale_invoices_posts_expected_payload(self, mock_post) -> None:
        mock_post.return_value = {
            "code": "200",
            "data": {
                "recordList": [{"id": "2", "code": "INV002"}],
                "recordCount": 1,
                "pageCount": 1,
            },
        }

        result = sales.list_sale_invoices("2026-02-01 00:00:00", "2026-02-28 23:59:59")

        self.assertEqual(result.records[0]["code"], "INV002")
        path, payload = mock_post.call_args.args
        self.assertEqual(path, "/yonbip/sd/vouchersaleinvoice/list")
        self.assertEqual(payload["pageIndex"], 1)

    @patch("backend.clients.yonyou.sales.yonyou_get")
    def test_get_sale_invoice_by_id_uses_get_detail_path(self, mock_get) -> None:
        mock_get.return_value = {"code": "200", "data": {"id": "7", "code": "INV007"}}

        data = sales.get_sale_invoice_by_id("7")

        self.assertEqual(data["code"], "INV007")
        mock_get.assert_called_once_with("/yonbip/sd/vouchersaleinvoice/detail", {"id": "7"})


if __name__ == "__main__":
    unittest.main()
