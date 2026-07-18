from __future__ import annotations

import unittest
import warnings
from unittest.mock import patch

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

from backend.clients.yonyou import finance
from backend.clients.yonyou.pagination import PageResult


class YonyouFinanceClientTest(unittest.TestCase):
    @patch("backend.clients.yonyou.finance.fetch_pages")
    def test_list_collections_uses_bill_date_range(self, mock_fetch) -> None:
        mock_fetch.return_value = PageResult(
            records=[{"id": "1", "code": "REC001"}],
            record_count=1,
            page_count=1,
            fetched_pages=1,
            truncated=False,
        )

        result = finance.list_collections("2025-01-01 00:00:00", "2025-12-31 23:59:59")

        self.assertEqual(result.record_count, 1)
        self.assertEqual(result.records[0]["code"], "REC001")
        mock_fetch.assert_called_once()
        path, factory = mock_fetch.call_args[0]
        self.assertEqual(path, "/yonbip/EFI/collection/list")
        payload = factory(1, 200)
        self.assertEqual(
            payload,
            {
                "pageIndex": 1,
                "pageSize": 200,
                "open_billDate_begin": "2025-01-01 00:00:00",
                "open_billDate_end": "2025-12-31 23:59:59",
                "isSum": True,
            },
        )

    @patch("backend.clients.yonyou.finance.yonyou_get")
    def test_get_collection_by_id_uses_get_detail_path(self, mock_get) -> None:
        mock_get.return_value = {
            "code": "200",
            "data": {"id": "1513642038374957065", "code": "RECar220802000502"},
        }

        data = finance.get_collection_by_id("1513642038374957065")

        self.assertEqual(data["code"], "RECar220802000502")
        mock_get.assert_called_once_with(
            "/yonbip/EFI/collection/detail",
            {"id": "1513642038374957065"},
        )

    @patch("backend.clients.yonyou.finance.yonyou_get")
    def test_get_collection_by_id_raises_on_empty_id(self, mock_get) -> None:
        with self.assertRaises(ValueError):
            finance.get_collection_by_id("")
        mock_get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
