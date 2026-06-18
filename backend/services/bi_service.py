from __future__ import annotations

import calendar
import copy
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from threading import Lock
from time import sleep, time
from typing import Any, Callable, Optional

from backend.clients.yonyou.purchase import (
    PageResult,
    list_arrival_orders,
    list_contracts,
    list_payment_applies,
    list_purchase_invoices,
    list_purchase_orders,
)


@dataclass(frozen=True)
class DocumentConfig:
    key: str
    label: str
    fetcher: Callable[[str, str], PageResult]
    person_fields: tuple[str, ...]
    amount_fields: tuple[str, ...]
    id_fields: tuple[str, ...]
    supplier_fields: tuple[str, ...] = ()
    org_fields: tuple[str, ...] = ()
    quantity_fields: tuple[str, ...] = ()
    status_fields: tuple[str, ...] = ()


DOCUMENTS: dict[str, DocumentConfig] = {
    "contract": DocumentConfig(
        key="contract",
        label="采购合同",
        fetcher=lambda start, end: list_contracts(start[:10], _next_day(end[:10])),
        person_fields=("purPersonName",),
        amount_fields=("taxMoney", "money", "natTaxMoney", "natMoney"),
        id_fields=("id", "code"),
        supplier_fields=("supplierSupName",),
        org_fields=("orgName", "orgCode"),
        quantity_fields=("totalnum", "totalMainNum", "totalPurchaseNum"),
        status_fields=("billstatus", "signStatus"),
    ),
    "purchase_order": DocumentConfig(
        key="purchase_order",
        label="采购订单",
        fetcher=list_purchase_orders,
        person_fields=("operator_name", "operator"),
        amount_fields=("oriSum", "moneysum", "listOriSum", "natSum"),
        id_fields=("id", "code"),
        supplier_fields=("vendor_name", "invoiceVendor_name"),
        org_fields=("org_name", "demandOrg_name", "inOrg_name"),
        quantity_fields=("totalQuantity", "qty", "priceQty"),
        status_fields=("status", "bizstatus", "receiveStatus"),
    ),
    "arrival_order": DocumentConfig(
        key="arrival_order",
        label="采购到货",
        fetcher=list_arrival_orders,
        person_fields=("creator",),
        amount_fields=("oriSum", "natSum", "oriMoney", "natMoney"),
        id_fields=("id", "code"),
        supplier_fields=("vendor_name", "invoiceSupplier_name"),
        org_fields=("org_name", "purchaseOrg_name"),
        quantity_fields=("qty", "acceptqty", "valuation_AcceptQty", "priceQty"),
        status_fields=("status",),
    ),
    "purchase_invoice": DocumentConfig(
        key="purchase_invoice",
        label="采购发票",
        fetcher=list_purchase_invoices,
        person_fields=("creator",),
        amount_fields=("listOriSum", "oriSum", "natSum", "listOriMoney", "natMoney"),
        id_fields=("id", "code"),
        supplier_fields=("vendor_name", "invoiceVendor_name"),
        org_fields=("org_name", "inInvoiceOrg_name", "inOrg_name", "demandOrg_name"),
        quantity_fields=("qty",),
        status_fields=("status", "creditStatus"),
    ),
    "payment_apply": DocumentConfig(
        key="payment_apply",
        label="付款申请单",
        fetcher=list_payment_applies,
        person_fields=("staff_name", "bodyItem_staff_name", "employee_name"),
        amount_fields=("oriAmount", "bodyItem_oriAmount", "oriOccupyAmount"),
        id_fields=("id", "code"),
        supplier_fields=("supplier_name", "partner_name", "funder_name"),
        org_fields=("financeOrg_name", "org_name"),
        quantity_fields=(),
        status_fields=("verifyState", "paidStatus"),
    ),
}

DOCUMENT_STAGE_ORDER = {
    "contract": 1,
    "purchase_order": 2,
    "arrival_order": 3,
    "purchase_invoice": 4,
    "payment_apply": 5,
}

_SUMMARY_CACHE: dict[str, dict[str, Any]] = {}
_SUMMARY_CACHE_LOCK = Lock()


def _next_day(day: str) -> str:
    year, month, date_part = (int(part) for part in day.split("-"))
    return date.fromordinal(date(year, month, date_part).toordinal() + 1).isoformat()


def default_month() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def month_range(month: Optional[str]) -> tuple[str, str]:
    value = (month or default_month()).strip()
    try:
        year_text, month_text = value.split("-", 1)
        year = int(year_text)
        month_num = int(month_text)
        last_day = calendar.monthrange(year, month_num)[1]
    except (ValueError, IndexError) as exc:
        raise ValueError("month 格式必须为 YYYY-MM") from exc

    start = f"{year:04d}-{month_num:02d}-01 00:00:00"
    end = f"{year:04d}-{month_num:02d}-{last_day:02d} 23:59:59"
    return start, end


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("name", "zh_CN", "value"):
            text = as_text(value.get(key))
            if text:
                return text
        return ""
    return str(value).strip()


def as_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def first_text(record: dict[str, Any], fields: tuple[str, ...]) -> str:
    for field in fields:
        text = as_text(record.get(field))
        if text:
            return text
    return ""


def first_amount(record: dict[str, Any], fields: tuple[str, ...]) -> Decimal:
    for field in fields:
        amount = as_decimal(record.get(field))
        if amount != 0:
            return amount
    return Decimal("0")


def first_decimal(record: dict[str, Any], fields: tuple[str, ...]) -> Decimal:
    for field in fields:
        amount = as_decimal(record.get(field))
        if amount != 0:
            return amount
    return Decimal("0")


def document_id(record: dict[str, Any], config: DocumentConfig) -> str:
    for field in config.id_fields:
        text = as_text(record.get(field))
        if text:
            return text
    return str(id(record))


def _empty_doc_summary(config: DocumentConfig) -> dict[str, Any]:
    return {
        "type": config.key,
        "label": config.label,
        "count": 0,
        "amount": 0.0,
        "quantity": 0.0,
        "recordCount": 0,
        "fetchedPages": 0,
        "truncated": False,
        "error": "",
    }


def _add_metric(bucket: dict[str, dict[str, Any]], key: str, label_field: str, amount: Decimal, quantity: Decimal) -> None:
    row = bucket.setdefault(key, {label_field: key, "count": 0, "amount": 0.0, "quantity": 0.0})
    row["count"] += 1
    row["amount"] += float(amount)
    row["quantity"] += float(quantity)


def _normalize_person_filters(persons: Optional[list[str]]) -> list[str]:
    if not persons:
        return []
    normalized = [item.strip() for item in persons if item and item.strip()]
    return list(dict.fromkeys(normalized))


def _person_match(person: str, filters: list[str], mode: str) -> bool:
    if not filters:
        return True
    if mode == "exact":
        return person in filters
    lowered = person.lower()
    return any(keyword.lower() in lowered for keyword in filters)


def _fetch_document_data(selected_docs: list[DocumentConfig], start_time: str, end_time: str) -> dict[str, Any]:
    if not selected_docs:
        return {}
    results: dict[str, Any] = {}
    for index, config in enumerate(selected_docs):
        if index > 0:
            sleep(0.35)
        try:
            results[config.key] = config.fetcher(start_time, end_time)
        except Exception as exc:
            results[config.key] = exc
    return results


def _safe_error_message(exc: Exception) -> str:
    message = str(exc)
    if "429" in message or "Too Many Requests" in message:
        return "接口请求过于频繁，请稍后点击刷新"
    return re.sub(r"access_token=[^&\\s]+", "access_token=***", message)


def _build_cache_key(
    month_value: str,
    selected_docs: list[DocumentConfig],
    person_filters: list[str],
    match_mode: str,
    top_n: int,
) -> str:
    doc_part = ",".join(config.key for config in selected_docs)
    person_part = ",".join(person_filters)
    return f"{month_value}|{doc_part}|{person_part}|{match_mode}|{top_n}"


def execution_summary(
    month: Optional[str] = None,
    doc_types: Optional[list[str]] = None,
    persons: Optional[list[str]] = None,
    person_match_mode: str = "contains",
    top_n: int = 10,
    refresh: bool = False,
) -> dict[str, Any]:
    month_value = (month or default_month()).strip()
    start_time, end_time = month_range(month_value)
    selected_keys = doc_types or list(DOCUMENTS.keys())
    selected_docs = [DOCUMENTS[key] for key in selected_keys if key in DOCUMENTS]
    person_filters = _normalize_person_filters(persons)
    match_mode = "exact" if person_match_mode == "exact" else "contains"
    safe_top_n = max(top_n, 1)
    cache_key = _build_cache_key(month_value, selected_docs, person_filters, match_mode, safe_top_n)

    if not refresh:
        with _SUMMARY_CACHE_LOCK:
            cached = _SUMMARY_CACHE.get(cache_key)
        if cached:
            result = copy.deepcopy(cached)
            result["meta"] = {
                "fromCache": True,
                "generatedAt": cached.get("meta", {}).get("generatedAt", ""),
                "cacheKey": cache_key,
            }
            return result

    by_person: dict[str, dict[str, Any]] = {}
    by_supplier: dict[str, dict[str, Any]] = {}
    by_org: dict[str, dict[str, Any]] = {}
    by_status: dict[str, dict[str, Any]] = {}
    by_document_type: dict[str, dict[str, Any]] = {config.key: _empty_doc_summary(config) for config in selected_docs}
    matrix: dict[tuple[str, str], dict[str, Any]] = {}
    missing_person_count = 0
    missing_supplier_count = 0
    total_count = 0
    total_amount = Decimal("0")
    total_quantity = Decimal("0")
    fetch_results = _fetch_document_data(selected_docs, start_time, end_time)

    for config in selected_docs:
        doc_summary = by_document_type[config.key]
        fetch_result = fetch_results.get(config.key)
        if isinstance(fetch_result, Exception):
            doc_summary["error"] = _safe_error_message(fetch_result)
            continue
        if not hasattr(fetch_result, "records"):
            doc_summary["error"] = "未知返回结果"
            continue
        try:
            page = fetch_result
            doc_summary.update(
                {
                    "recordCount": int(getattr(page, "record_count", 0)),
                    "fetchedPages": int(getattr(page, "fetched_pages", 0)),
                    "truncated": bool(getattr(page, "truncated", False)),
                }
            )
            seen: set[str] = set()
            for record in list(getattr(page, "records", [])):
                unique_id = f"{config.key}:{document_id(record, config)}"
                if unique_id in seen:
                    continue
                seen.add(unique_id)

                person = first_text(record, config.person_fields) or "未分配"
                if not _person_match(person, person_filters, match_mode):
                    continue
                if person == "未分配":
                    missing_person_count += 1
                amount = first_amount(record, config.amount_fields)
                quantity = first_decimal(record, config.quantity_fields)
                supplier = first_text(record, config.supplier_fields) or "未分配供应商"
                org = first_text(record, config.org_fields) or "未分配组织"
                status = first_text(record, config.status_fields) or "未标记状态"
                if supplier == "未分配供应商":
                    missing_supplier_count += 1

                total_count += 1
                total_amount += amount
                total_quantity += quantity
                doc_summary["count"] += 1
                doc_summary["amount"] += float(amount)
                doc_summary["quantity"] += float(quantity)

                person_row = by_person.setdefault(person, {"person": person, "count": 0, "amount": 0.0})
                person_row["count"] += 1
                person_row["amount"] += float(amount)
                person_row["quantity"] = float(as_decimal(person_row.get("quantity")) + quantity)

                _add_metric(by_supplier, supplier, "supplier", amount, quantity)
                _add_metric(by_org, org, "org", amount, quantity)
                _add_metric(by_status, f"{config.label}:{status}", "status", amount, quantity)

                matrix_key = (person, config.key)
                matrix_row = matrix.setdefault(
                    matrix_key,
                    {"person": person, "type": config.key, "label": config.label, "count": 0, "amount": 0.0},
                )
                matrix_row["count"] += 1
                matrix_row["amount"] += float(amount)
                matrix_row["quantity"] = float(as_decimal(matrix_row.get("quantity")) + quantity)
        except Exception as exc:
            doc_summary["error"] = str(exc)

    by_person_rows = sorted(by_person.values(), key=lambda row: row["amount"], reverse=True)
    by_supplier_rows = sorted(by_supplier.values(), key=lambda row: row["amount"], reverse=True)
    by_org_rows = sorted(by_org.values(), key=lambda row: row["amount"], reverse=True)
    by_status_rows = sorted(by_status.values(), key=lambda row: row["amount"], reverse=True)
    lifecycle = sorted(
        (
            {
                "type": row["type"],
                "label": row["label"],
                "count": row["count"],
                "amount": row["amount"],
                "quantity": row["quantity"],
                "stageOrder": DOCUMENT_STAGE_ORDER.get(row["type"], 99),
            }
            for row in by_document_type.values()
        ),
        key=lambda row: row["stageOrder"],
    )
    order_amount = next((as_decimal(row["amount"]) for row in lifecycle if row["type"] == "purchase_order"), Decimal("0"))

    def coverage(type_key: str) -> float:
        if order_amount == 0:
            return 0.0
        current = next((as_decimal(row["amount"]) for row in lifecycle if row["type"] == type_key), Decimal("0"))
        return float((current / order_amount) * Decimal("100"))

    result = {
        "month": month_value,
        "range": {"start": start_time, "end": end_time},
        "query": {
            "persons": person_filters,
            "personMatchMode": match_mode,
            "topN": safe_top_n,
            "docTypes": [config.key for config in selected_docs],
        },
        "totals": {
            "count": total_count,
            "amount": float(total_amount),
            "quantity": float(total_quantity),
            "missingPersonCount": missing_person_count,
            "missingSupplierCount": missing_supplier_count,
        },
        "byPerson": by_person_rows,
        "byPersonTopN": by_person_rows[:safe_top_n],
        "bySupplier": by_supplier_rows,
        "bySupplierTopN": by_supplier_rows[:safe_top_n],
        "byOrg": by_org_rows,
        "byOrgTopN": by_org_rows[:safe_top_n],
        "byStatus": by_status_rows,
        "byDocumentType": list(by_document_type.values()),
        "lifecycle": lifecycle,
        "coverage": {
            "arrivalVsOrderAmount": coverage("arrival_order"),
            "invoiceVsOrderAmount": coverage("purchase_invoice"),
            "paymentApplyVsOrderAmount": coverage("payment_apply"),
        },
        "matrix": sorted(matrix.values(), key=lambda row: (row["person"], row["type"])),
        "availableDocumentTypes": [{"type": config.key, "label": config.label} for config in DOCUMENTS.values()],
        "availablePeople": [row["person"] for row in by_person_rows],
        "meta": {
            "fromCache": False,
            "generatedAt": int(time()),
            "cacheKey": cache_key,
        },
    }
    with _SUMMARY_CACHE_LOCK:
        _SUMMARY_CACHE[cache_key] = copy.deepcopy(result)
    return result
