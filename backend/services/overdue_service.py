from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from backend.db.receivable_store import ReceivableCacheStore, get_receivable_store
from backend.value_utils import as_decimal, as_text
from backend.services.collection_sync_service import (
    COLLECTION_SYNC_KEY,
    get_collection_sync_status,
    kick_collection_sync,
)
from backend.services.receivable_match_service import allocate_collections_to_invoices
from backend.services.receivable_sync_service import (
    RECEIVABLE_SYNC_KEY,
    get_receivable_sync_status,
    invoice_contract_ref,
    kick_receivable_sync,
)
from backend.date_ranges import rolling_12m_range


UPCOMING_DAYS = 7
DEFAULT_STATUSES = ("overdue", "upcoming", "normal")
TRUE_OVERDUE_STATUS = "true_overdue"
SETTLED_TOLERANCE = 0.01


def _parse_datetime(value: Any) -> datetime | None:
    text = as_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:19] if len(text) >= 19 else text[:10], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text[:19])
    except ValueError:
        return None


def _money(value: Any) -> float:
    return float(as_decimal(value))


def _payment_term_days(contract: dict[str, Any] | None) -> int:
    if not contract:
        return 0
    terms = contract.get("receiveAgreement") or []
    if not isinstance(terms, list):
        return 0

    best_percent = -1.0
    best_days = 0
    for term in terms:
        if not isinstance(term, dict):
            continue
        days = int(term.get("accountDay") or 0)
        if days <= 0:
            continue
        percent = float(term.get("receivePercent") or 0)
        if percent > best_percent:
            best_percent = percent
            best_days = days
        elif best_days == 0:
            best_days = days
    return best_days


def classify_status(due: date, today: date, upcoming_days: int = UPCOMING_DAYS) -> tuple[str, int]:
    days_until = (due - today).days
    if days_until < 0:
        return "overdue", days_until
    if days_until <= upcoming_days:
        return "upcoming", days_until
    return "normal", days_until


def _tax_amount(payload: dict[str, Any]) -> float:
    for key in ("oriSum", "natSum", "totalPriceTax"):
        amount = _money(payload.get(key))
        if amount:
            return amount
    return 0.0


def _contracts_by_code(contracts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for payload in contracts:
        code = as_text(payload.get("code"))
        if code:
            mapping[code] = payload
    return mapping


def _collection_status(tax_amount: float, collected_amount: float) -> str:
    outstanding = round(max(tax_amount - collected_amount, 0.0), 2)
    if outstanding <= SETTLED_TOLERANCE:
        return "settled"
    if collected_amount > SETTLED_TOLERANCE:
        return "partial"
    return "unpaid"


def _true_status(calendar_status: str, collection_status: str) -> str:
    if collection_status == "settled":
        return "settled"
    if calendar_status == "overdue":
        return TRUE_OVERDUE_STATUS
    return calendar_status


def _status_allowed(true_status: str, allowed: set[str]) -> bool:
    if true_status == TRUE_OVERDUE_STATUS:
        return "overdue" in allowed
    return true_status in allowed


def _summary_bucket(summary: dict[str, Any], key: str, amount: float) -> None:
    summary[key]["count"] += 1
    summary[key]["amount"] = round(summary[key]["amount"] + amount, 2)


def build_receivable_rows(
    invoices: list[dict[str, Any]],
    contracts_by_code: dict[str, dict[str, Any]],
    *,
    allocations: dict[str, Any] | None = None,
    today: date | None = None,
    statuses: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    today_value = today or date.today()
    allowed = statuses or set(DEFAULT_STATUSES)
    receivable_rows: list[dict[str, Any]] = []
    pending_audit_rows: list[dict[str, Any]] = []
    unmatched_rows: list[dict[str, Any]] = []
    settled_rows: list[dict[str, Any]] = []
    summary = {
        "overdue": {"count": 0, "amount": 0.0},
        "calendarOverdue": {"count": 0, "amount": 0.0},
        "trueOverdue": {"count": 0, "amount": 0.0},
        "upcoming": {"count": 0, "amount": 0.0},
        "normal": {"count": 0, "amount": 0.0},
        "settled": {"count": 0, "amount": 0.0},
        "unmatched": {"count": 0, "amount": 0.0},
        "pendingAudit": {"count": 0, "amount": 0.0},
    }

    for payload in invoices:
        invoice_id = as_text(payload.get("id"))
        invoice_code = as_text(payload.get("code"))
        customer = as_text(payload.get("agentName") or payload.get("agentId_name")) or "未填写"
        salesman = as_text(payload.get("auditor") or payload.get("salesmanId_name")) or "未分配"
        tax_amount = _tax_amount(payload)
        audit_dt = _parse_datetime(payload.get("auditTime"))
        contract_code, _contract_id = invoice_contract_ref(payload)
        contract = contracts_by_code.get(contract_code) if contract_code else None
        payment_term_days = _payment_term_days(contract)
        allocation = allocations.get(invoice_id) if allocations else None
        collected_amount = round(float(getattr(allocation, "collected_amount", 0.0) or 0.0), 2)
        match_quality = str(getattr(allocation, "match_quality", "unpaid") or "unpaid")
        outstanding = round(max(tax_amount - collected_amount, 0.0), 2)
        collection_status = _collection_status(tax_amount, collected_amount)

        base_row = {
            "invoiceId": invoice_id,
            "invoiceCode": invoice_code,
            "contractCode": contract_code,
            "customer": customer,
            "salesman": salesman,
            "taxAmount": tax_amount,
            "collectedAmount": collected_amount,
            "outstanding": outstanding,
            "collectionStatus": collection_status,
            "matchQuality": match_quality,
            "auditTime": audit_dt.isoformat(sep=" ", timespec="seconds") if audit_dt else "",
            "paymentTermDays": payment_term_days,
            "dueDate": "",
            "daysUntilDue": 0,
            "status": "pending_audit",
            "calendarStatus": "pending_audit",
            "trueStatus": "pending_audit",
        }

        if audit_dt is None:
            _summary_bucket(summary, "pendingAudit", tax_amount)
            pending_audit_rows.append({**base_row, "status": "pending_audit"})
            continue

        if payment_term_days <= 0 or contract is None:
            _summary_bucket(summary, "unmatched", tax_amount)
            unmatched_rows.append({**base_row, "status": "unmatched", "trueStatus": "unmatched"})
            continue

        due = audit_dt.date() + timedelta(days=payment_term_days)
        calendar_status, days_until = classify_status(due, today_value)
        true_status = _true_status(calendar_status, collection_status)
        row = {
            **base_row,
            "dueDate": due.isoformat(),
            "daysUntilDue": days_until,
            "status": calendar_status,
            "calendarStatus": calendar_status,
            "trueStatus": true_status,
        }

        if calendar_status == "overdue":
            _summary_bucket(summary, "calendarOverdue", tax_amount)
        if true_status == TRUE_OVERDUE_STATUS:
            _summary_bucket(summary, "trueOverdue", outstanding)
            _summary_bucket(summary, "overdue", outstanding)
        elif true_status == "upcoming":
            _summary_bucket(summary, "upcoming", outstanding)
        elif true_status == "normal":
            _summary_bucket(summary, "normal", outstanding)
        elif true_status == "settled":
            _summary_bucket(summary, "settled", tax_amount)

        if true_status == "settled":
            settled_rows.append(row)
            continue

        if _status_allowed(true_status, allowed):
            receivable_rows.append(row)

    receivable_rows.sort(
        key=lambda item: (item["daysUntilDue"], -float(item["outstanding"]), item["invoiceCode"])
    )
    pending_audit_rows.sort(key=lambda item: item["invoiceCode"], reverse=True)
    unmatched_rows.sort(key=lambda item: item["invoiceCode"], reverse=True)
    settled_rows.sort(key=lambda item: item["dueDate"], reverse=True)
    return receivable_rows, pending_audit_rows, unmatched_rows, settled_rows, summary


def build_receivable_charts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    overdue_rows = [row for row in rows if row.get("trueStatus") == TRUE_OVERDUE_STATUS]
    bucket_defs = [
        ("1-7天", 1, 7),
        ("8-30天", 8, 30),
        ("31-90天", 31, 90),
        ("90天以上", 91, 10_000),
    ]
    aging_buckets: list[dict[str, Any]] = []
    for label, low, high in bucket_defs:
        matched = [
            row
            for row in overdue_rows
            if low <= -int(row.get("daysUntilDue") or 0) <= high
        ]
        aging_buckets.append(
            {
                "label": label,
                "count": len(matched),
                "amount": round(sum(float(row.get("outstanding") or 0) for row in matched), 2),
            }
        )

    customer_totals: dict[str, dict[str, Any]] = {}
    for row in overdue_rows:
        customer = str(row.get("customer") or "未填写")
        bucket = customer_totals.setdefault(customer, {"customer": customer, "amount": 0.0, "count": 0})
        bucket["amount"] = round(bucket["amount"] + float(row.get("outstanding") or 0), 2)
        bucket["count"] += 1
    top_customers = sorted(customer_totals.values(), key=lambda item: item["amount"], reverse=True)[:10]

    return {"agingBuckets": aging_buckets, "topCustomers": top_customers}


def build_contract_receivable_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        contract_code = str(row.get("contractCode") or "").strip()
        if not contract_code:
            continue
        bucket = grouped.setdefault(
            contract_code,
            {
                "contractCode": contract_code,
                "customer": str(row.get("customer") or "未填写"),
                "receivableAmount": 0.0,
                "collectedAmount": 0.0,
                "outstanding": 0.0,
                "trueOverdueAmount": 0.0,
                "invoiceCount": 0,
                "trueOverdueCount": 0,
            },
        )
        tax_amount = float(row.get("taxAmount") or 0)
        collected_amount = float(row.get("collectedAmount") or 0)
        outstanding = float(row.get("outstanding") or 0)
        bucket["receivableAmount"] = round(bucket["receivableAmount"] + tax_amount, 2)
        bucket["collectedAmount"] = round(bucket["collectedAmount"] + collected_amount, 2)
        bucket["outstanding"] = round(bucket["outstanding"] + outstanding, 2)
        bucket["invoiceCount"] += 1
        if row.get("trueStatus") == TRUE_OVERDUE_STATUS:
            bucket["trueOverdueAmount"] = round(bucket["trueOverdueAmount"] + outstanding, 2)
            bucket["trueOverdueCount"] += 1

    result = sorted(
        grouped.values(),
        key=lambda item: (item["trueOverdueAmount"], item["outstanding"]),
        reverse=True,
    )
    return result


def contract_overdue(
    month: Optional[str] = None,
    statuses: Optional[list[str]] = None,
    *,
    kick: bool = True,
    store: ReceivableCacheStore | None = None,
) -> dict[str, Any]:
    del month
    start, end = rolling_12m_range()
    cache = store or get_receivable_store()

    if kick:
        kick_receivable_sync(store=cache)
        kick_collection_sync(store=cache)

    status_set = {item.strip() for item in (statuses or list(DEFAULT_STATUSES)) if item.strip()}
    if not status_set:
        status_set = set(DEFAULT_STATUSES)

    invoices = [item.payload for item in cache.get_all_sale_invoices()]
    contracts = [item.payload for item in cache.get_all_sale_contracts()]
    collections = [item.payload for item in cache.get_all_collections()]
    allocations = allocate_collections_to_invoices(invoices, collections)

    all_rows, pending_audit_rows, unmatched_rows, settled_rows, summary = build_receivable_rows(
        invoices,
        _contracts_by_code(contracts),
        allocations=allocations,
        statuses=set(DEFAULT_STATUSES),
    )
    all_fact_rows = all_rows + settled_rows + pending_audit_rows + unmatched_rows
    cache.replace_receivable_facts(all_fact_rows)
    rows = [row for row in all_rows if _status_allowed(str(row.get("trueStatus") or ""), status_set)]
    contract_summary = build_contract_receivable_summary(all_fact_rows)
    charts = build_receivable_charts(rows)
    receivable_sync = get_receivable_sync_status(RECEIVABLE_SYNC_KEY, cache)
    collection_sync = get_collection_sync_status(COLLECTION_SYNC_KEY, cache)
    updated_at = max(
        receivable_sync.get("updatedAt") or "",
        collection_sync.get("updatedAt") or "",
    )

    return {
        "scope": RECEIVABLE_SYNC_KEY,
        "range": {"start": start, "end": end},
        "query": {"statuses": sorted(status_set)},
        "summary": summary,
        "charts": charts,
        "rows": rows,
        "pendingAuditRows": pending_audit_rows,
        "unmatchedRows": unmatched_rows,
        "settledRows": settled_rows,
        "contractSummary": contract_summary,
        "meta": {
            "cachedInvoiceCount": cache.count_all_sale_invoices(),
            "cachedContractCount": cache.count_all_sale_contracts(),
            "cachedCollectionCount": cache.count_all_collections(),
            "rowCount": len(rows),
            "pendingAuditRowCount": len(pending_audit_rows),
            "unmatchedRowCount": len(unmatched_rows),
            "settledRowCount": len(settled_rows),
            "updatedAt": updated_at,
            "sync": receivable_sync,
            "collectionSync": collection_sync,
            "emptyCache": len(invoices) == 0,
        },
    }
