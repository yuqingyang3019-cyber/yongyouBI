from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from backend.clients.yonyou.client import success_code, yonyou_post
from backend.config import get_settings


CONTRACT_LIST_PATH = "/yonbip/cpu/contractOpenApi/queryList"
PURCHASE_ORDER_LIST_PATH = "/yonbip/scm/purchaseorder/list"
PAYMENT_APPLY_LIST_PATH = "/yonbip/EFI/paymentApply/list"


@dataclass
class PageResult:
    records: list[dict[str, Any]]
    record_count: int
    page_count: int
    fetched_pages: int
    truncated: bool


def _extract_page(body: dict[str, Any], path: str) -> tuple[list[dict[str, Any]], int, int]:
    if not success_code(body, "200"):
        raise RuntimeError(f"用友接口调用失败：{path}，{body.get('message') or body}")
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    record_list = data.get("recordList") if isinstance(data.get("recordList"), list) else []
    records = [item for item in record_list if isinstance(item, dict)]
    return records, int(data.get("recordCount") or len(records)), int(data.get("pageCount") or 1)


def _fetch_pages(path: str, payload_factory: Callable[[int, int], dict[str, Any]]) -> PageResult:
    settings = get_settings()
    all_records: list[dict[str, Any]] = []
    record_count = 0
    page_count = 1
    fetched_pages = 0

    for page_index in range(1, settings.request_max_pages + 1):
        body = yonyou_post(path, payload_factory(page_index, settings.request_page_size))
        records, record_count, page_count = _extract_page(body, path)
        all_records.extend(records)
        fetched_pages = page_index
        if page_index >= page_count or not records:
            break

    return PageResult(
        records=all_records,
        record_count=record_count,
        page_count=page_count,
        fetched_pages=fetched_pages,
        truncated=page_count > fetched_pages,
    )


def list_contracts(start_date: str, end_date: str) -> PageResult:
    def payload(page_index: int, page_size: int) -> dict[str, Any]:
        return {
            "pageIndex": page_index,
            "pageSize": page_size,
            "createTimeStart": start_date,
            "createTimeEnd": end_date,
            "orderBy": "createTime asc",
        }

    return _fetch_pages(CONTRACT_LIST_PATH, payload)


def list_purchase_orders(start_time: str, end_time: str) -> PageResult:
    def payload(page_index: int, page_size: int) -> dict[str, Any]:
        return {
            "pageIndex": page_index,
            "pageSize": page_size,
            "isSum": True,
            "simpleVOs": [
                {
                    "field": "vouchdate",
                    "op": "between",
                    "value1": start_time,
                    "value2": end_time,
                }
            ],
            "queryOrders": [{"field": "id", "order": "asc"}],
        }

    return _fetch_pages(PURCHASE_ORDER_LIST_PATH, payload)


def list_payment_applies(start_time: str, end_time: str) -> PageResult:
    def payload(page_index: int, page_size: int) -> dict[str, Any]:
        return {
            "pageIndex": str(page_index),
            "pageSize": str(page_size),
            "open_billDate_begin": start_time,
            "open_billDate_end": end_time,
            "isSum": True,
        }

    return _fetch_pages(PAYMENT_APPLY_LIST_PATH, payload)
