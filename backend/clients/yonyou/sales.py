from __future__ import annotations

from typing import Any

from backend.clients.yonyou.client import success_code, yonyou_get, yonyou_post
from backend.clients.yonyou.pagination import PageResult, fetch_pages


SALE_CONTRACT_LIST_PATH = "/sd/sact/list"
SALE_CONTRACT_DETAIL_PATH = "/yonbip/sd/sact/detail"
SALE_INVOICE_LIST_PATH = "/yonbip/sd/vouchersaleinvoice/list"
SALE_INVOICE_DETAIL_PATH = "/yonbip/sd/vouchersaleinvoice/detail"


def _get_by_id(path: str, record_id: str | int, *, label: str) -> dict[str, Any]:
    if record_id in (None, ""):
        raise ValueError(f"{label} 需要 id")

    body = yonyou_get(path, {"id": record_id})
    if not success_code(body, "200"):
        raise RuntimeError(f"用友接口调用失败：{path}，{body.get('message') or body}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"{label}返回为空：{record_id}")
    return data


def _list_by_vouchdate(path: str, start_time: str, end_time: str) -> PageResult:
    def payload(page_index: int, page_size: int) -> dict[str, Any]:
        return {
            "pageIndex": page_index,
            "pageSize": page_size,
            "isSum": True,
            "open_vouchdate_begin": start_time,
            "open_vouchdate_end": end_time,
            "queryOrders": [{"field": "id", "order": "asc"}],
        }

    return fetch_pages(path, payload)


def list_sale_contracts(start_time: str, end_time: str) -> PageResult:
    return _list_by_vouchdate(SALE_CONTRACT_LIST_PATH, start_time, end_time)


def get_sale_contract_by_id(contract_id: str | int) -> dict[str, Any]:
    return _get_by_id(SALE_CONTRACT_DETAIL_PATH, contract_id, label="销售合同详情")


def list_sale_invoices(start_time: str, end_time: str) -> PageResult:
    return _list_by_vouchdate(SALE_INVOICE_LIST_PATH, start_time, end_time)


def get_sale_invoice_by_id(invoice_id: str | int) -> dict[str, Any]:
    return _get_by_id(SALE_INVOICE_DETAIL_PATH, invoice_id, label="销售发票详情")
