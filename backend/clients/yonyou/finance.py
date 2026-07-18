from __future__ import annotations

from typing import Any

from backend.clients.yonyou.client import success_code, yonyou_get
from backend.clients.yonyou.pagination import PageResult, fetch_pages


COLLECTION_LIST_PATH = "/yonbip/EFI/collection/list"
COLLECTION_DETAIL_PATH = "/yonbip/EFI/collection/detail"


def list_collections(start_time: str, end_time: str, *, is_sum: bool = True) -> PageResult:
    def payload(page_index: int, page_size: int) -> dict[str, Any]:
        return {
            "pageIndex": page_index,
            "pageSize": page_size,
            "open_billDate_begin": start_time,
            "open_billDate_end": end_time,
            "isSum": is_sum,
        }

    return fetch_pages(COLLECTION_LIST_PATH, payload)


def get_collection_by_id(collection_id: str | int) -> dict[str, Any]:
    if collection_id in (None, ""):
        raise ValueError("get_collection_by_id 需要 id")

    body = yonyou_get(COLLECTION_DETAIL_PATH, {"id": collection_id})
    if not success_code(body, "200"):
        raise RuntimeError(f"用友接口调用失败：{COLLECTION_DETAIL_PATH}，{body.get('message') or body}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"收款单详情返回为空：{collection_id}")
    return data
