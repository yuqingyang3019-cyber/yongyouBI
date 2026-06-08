from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from backend.clients.yonyou.purchase import PageResult, list_contracts, list_payment_applies, list_purchase_orders


@dataclass(frozen=True)
class DocumentConfig:
    key: str
    label: str
    fetcher: Callable[[str, str], PageResult]
    person_fields: tuple[str, ...]
    amount_fields: tuple[str, ...]
    id_fields: tuple[str, ...]


DOCUMENTS: dict[str, DocumentConfig] = {
    "contract": DocumentConfig(
        key="contract",
        label="采购合同",
        fetcher=lambda start, end: list_contracts(start[:10], _next_day(end[:10])),
        person_fields=("purPersonName",),
        amount_fields=("taxMoney", "money", "natTaxMoney", "natMoney"),
        id_fields=("id", "code"),
    ),
    "purchase_order": DocumentConfig(
        key="purchase_order",
        label="采购订单",
        fetcher=list_purchase_orders,
        person_fields=("operator_name", "operator"),
        amount_fields=("oriSum", "moneysum", "listOriSum", "natSum"),
        id_fields=("id", "code"),
    ),
    "payment_apply": DocumentConfig(
        key="payment_apply",
        label="付款申请单",
        fetcher=list_payment_applies,
        person_fields=("staff_name", "bodyItem_staff_name", "employee_name"),
        amount_fields=("oriAmount", "bodyItem_oriAmount", "oriOccupyAmount"),
        id_fields=("id", "code"),
    ),
}


def _next_day(day: str) -> str:
    year, month, date_part = (int(part) for part in day.split("-"))
    return date.fromordinal(date(year, month, date_part).toordinal() + 1).isoformat()


def default_month() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def month_range(month: str | None) -> tuple[str, str]:
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
        "recordCount": 0,
        "fetchedPages": 0,
        "truncated": False,
        "error": "",
    }


def execution_summary(month: str | None = None, doc_types: list[str] | None = None) -> dict[str, Any]:
    start_time, end_time = month_range(month)
    selected_keys = doc_types or list(DOCUMENTS.keys())
    selected_docs = [DOCUMENTS[key] for key in selected_keys if key in DOCUMENTS]

    by_person: dict[str, dict[str, Any]] = {}
    by_document_type: dict[str, dict[str, Any]] = {config.key: _empty_doc_summary(config) for config in selected_docs}
    matrix: dict[tuple[str, str], dict[str, Any]] = {}
    missing_person_count = 0
    total_count = 0
    total_amount = Decimal("0")

    for config in selected_docs:
        doc_summary = by_document_type[config.key]
        try:
            page = config.fetcher(start_time, end_time)
            doc_summary.update(
                {
                    "recordCount": page.record_count,
                    "fetchedPages": page.fetched_pages,
                    "truncated": page.truncated,
                }
            )
            seen: set[str] = set()
            for record in page.records:
                unique_id = f"{config.key}:{document_id(record, config)}"
                if unique_id in seen:
                    continue
                seen.add(unique_id)

                person = first_text(record, config.person_fields) or "未分配"
                if person == "未分配":
                    missing_person_count += 1
                amount = first_amount(record, config.amount_fields)

                total_count += 1
                total_amount += amount
                doc_summary["count"] += 1
                doc_summary["amount"] += float(amount)

                person_row = by_person.setdefault(person, {"person": person, "count": 0, "amount": 0.0})
                person_row["count"] += 1
                person_row["amount"] += float(amount)

                matrix_key = (person, config.key)
                matrix_row = matrix.setdefault(
                    matrix_key,
                    {"person": person, "type": config.key, "label": config.label, "count": 0, "amount": 0.0},
                )
                matrix_row["count"] += 1
                matrix_row["amount"] += float(amount)
        except Exception as exc:
            doc_summary["error"] = str(exc)

    return {
        "month": (month or default_month()).strip(),
        "range": {"start": start_time, "end": end_time},
        "totals": {
            "count": total_count,
            "amount": float(total_amount),
            "missingPersonCount": missing_person_count,
        },
        "byPerson": sorted(by_person.values(), key=lambda row: row["amount"], reverse=True),
        "byDocumentType": list(by_document_type.values()),
        "matrix": sorted(matrix.values(), key=lambda row: (row["person"], row["type"])),
        "availableDocumentTypes": [{"type": config.key, "label": config.label} for config in DOCUMENTS.values()],
    }
