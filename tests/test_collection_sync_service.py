from __future__ import annotations

import unittest
import warnings
from unittest.mock import patch

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

from backend.services import collection_sync_service
from backend.services.collection_sync_service import COLLECTION_SYNC_KEY
from tests.receivable_store_fake import InMemoryReceivableStore


class CollectionSyncTest(unittest.TestCase):
    def test_sync_only_fetches_changed_collections(self) -> None:
        with self.subTest("in-memory repository"):
            store = InMemoryReceivableStore()
            store.upsert_collection(
                "rec1",
                "2026-07",
                "same",
                {
                    "id": "rec1",
                    "code": "REC1",
                    "verifyState": 2,
                    "billDate": "2026-07-01",
                    "bodyItem": [{"orderNo": "ORD1", "oriTaxIncludedAmount": 100}],
                },
            )

            listed = type(
                "Page",
                (),
                {
                    "records": [
                        {
                            "id": "rec1",
                            "code": "REC1",
                            "modifyTime": "same",
                            "verifyState": 2,
                            "bodyItem_orderNo": "ORD1",
                        },
                        {
                            "id": "rec2",
                            "code": "REC2",
                            "modifyTime": "new",
                            "verifyState": 2,
                            "bodyItem_orderNo": "ORD2",
                        },
                    ]
                },
            )()

            with (
                patch.object(collection_sync_service, "list_collections", return_value=listed) as list_mock,
                patch.object(
                    collection_sync_service,
                    "get_collection_by_id",
                    return_value={
                        "id": "rec2",
                        "code": "REC2",
                        "verifyState": 2,
                        "billDate": "2026-07-02",
                        "bodyItem": [{"orderNo": "ORD2", "oriTaxIncludedAmount": 200}],
                    },
                ) as detail_mock,
                patch.object(collection_sync_service, "sleep"),
                patch.object(
                    collection_sync_service,
                    "get_settings",
                    return_value=type("S", (), {"contract_detail_sync_interval": 0})(),
                ),
            ):
                collection_sync_service._STATES.clear()
                collection_sync_service._THREADS.clear()
                collection_sync_service._run_sync(COLLECTION_SYNC_KEY, store)

            list_mock.assert_called_once()
            self.assertFalse(list_mock.call_args.kwargs.get("is_sum", True))
            detail_mock.assert_called_once_with("rec2")
            self.assertEqual(store.get_collection_list_ts_map()["rec2"], "new")
            self.assertEqual(store.count_all_collections(), 2)
            status = collection_sync_service.get_collection_sync_status(COLLECTION_SYNC_KEY, store)
            self.assertEqual(status["status"], "done")
            self.assertEqual(status["doneCount"], 1)
            self.assertEqual(status["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
