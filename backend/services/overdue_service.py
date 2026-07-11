from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from backend.db.cache_store import ContractCacheStore, get_cache_store
from backend.services.bi_service import as_decimal, as_text
from backend.services.sync_service import (
    ROLLING_SYNC_KEY,
    get_sync_status,
    kick_sync,
    rolling_12m_range,
)


UPCOMING_DAYS = 7
DEFAULT_STATUSES = ("overdue", "upcoming", "normal")

ATTACHMENT_FIELDS: tuple[tuple[str, str], ...] = (
    ("signedFileId", "已签合同"),
    ("eContractFileId", "电子合同"),
    ("eContractWordFileId", "电子合同Word"),
    ("stockStampFileId", "采购盖章附件"),
    ("saleStampFileId", "供应方盖章附件"),
    ("saleFileId", "供应方附件"),
    ("internalFileId", "内控附件"),
    ("externalFileId", "外部附件"),
    ("nonStandardFileId", "非制式合同"),
)


def _parse_due_date(value: Any) -> date | None:
    text = as_text(value)
    if not text:
        return None
    if text.isdigit() and len(text) >= 10:
        try:
            millis = int(text)
            if millis > 10_000_000_000:
                millis //= 1000
            return datetime.fromtimestamp(millis).date()
        except (ValueError, OSError, OverflowError):
            return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19] if len(text) >= 19 else text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _money(value: Any) -> float:
    return float(as_decimal(value))


def extract_attachments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    seen: set[str] = set()

    urls = payload.get("saleStampFileUrls")
    if isinstance(urls, list):
        for url in urls:
            text = as_text(url)
            if text.startswith("http://") or text.startswith("https://"):
                key = f"url:{text}"
                if key in seen:
                    continue
                seen.add(key)
                attachments.append(
                    {
                        "type": "saleStampFileUrls",
                        "label": "供应商盖章附件",
                        "url": text,
                        "fileId": "",
                    }
                )
    elif as_text(urls).startswith("http"):
        text = as_text(urls)
        attachments.append(
            {
                "type": "saleStampFileUrls",
                "label": "供应商盖章附件",
                "url": text,
                "fileId": "",
            }
        )

    for field, label in (("ectFilePath", "电子合同文件"), ("ectOldFilePath", "旧电子合同文件")):
        path = as_text(payload.get(field))
        if path.startswith("http://") or path.startswith("https://"):
            key = f"url:{path}"
            if key in seen:
                continue
            seen.add(key)
            attachments.append({"type": field, "label": label, "url": path, "fileId": ""})

    for field, label in ATTACHMENT_FIELDS:
        file_id = as_text(payload.get(field))
        if not file_id:
            continue
        key = f"id:{file_id}"
        if key in seen:
            continue
        seen.add(key)
        attachments.append({"type": field, "label": label, "url": "", "fileId": file_id})

    return attachments


def _iter_pay_terms(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    terms: list[tuple[str, dict[str, Any]]] = []
    for source, key in (
        ("contractPayTermList", "payTerm"),
        ("contractPrepayList", "prepay"),
    ):
        items = payload.get(source)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                terms.append((key, item))
    return terms


def classify_status(due: date, today: date, upcoming_days: int = UPCOMING_DAYS) -> tuple[str, int]:
    days_until = (due - today).days
    if days_until < 0:
        return "overdue", days_until
    if days_until <= upcoming_days:
        return "upcoming", days_until
    return "normal", days_until


def _row_from_term(
    *,
    payload: dict[str, Any],
    source: str,
    term: dict[str, Any],
    due: date,
    pay_tax: float,
    paid: float,
    unpaid: float,
    status: str,
    days_until: int,
    attachments: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "contractId": as_text(payload.get("id")),
        "contractCode": as_text(payload.get("code")),
        "supplier": as_text(payload.get("supplierSupName") or payload.get("supEnterpriseName")) or "未填写",
        "person": as_text(payload.get("purPersonName")) or "未分配",
        "payPeriod": term.get("payPeriod"),
        "payPointName": as_text(term.get("payPointName")),
        "source": source,
        "payTaxMoney": pay_tax,
        "paidAmount": paid,
        "unpaidAmount": unpaid,
        "dueDate": due.isoformat(),
        "daysUntilDue": days_until,
        "status": status,
        "attachments": attachments,
    }


def build_rows_from_payloads(
    contracts: list[dict[str, Any]],
    *,
    today: date | None = None,
    statuses: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    today_value = today or date.today()
    allowed = statuses or set(DEFAULT_STATUSES)
    unpaid_rows: list[dict[str, Any]] = []
    paid_rows: list[dict[str, Any]] = []
    summary = {
        "overdue": {"count": 0, "amount": 0.0},
        "upcoming": {"count": 0, "amount": 0.0},
        "normal": {"count": 0, "amount": 0.0},
        "paid": {"count": 0, "amount": 0.0},
    }

    for payload in contracts:
        attachments = extract_attachments(payload)
        for source, term in _iter_pay_terms(payload):
            due = _parse_due_date(term.get("dueDate"))
            if due is None:
                continue
            pay_tax = _money(term.get("payTaxMoney"))
            paid = _money(term.get("practicalPaymentmny"))
            unpaid = round(pay_tax - paid, 2)

            if unpaid <= 0:
                status, days_until = classify_status(due, today_value)
                summary["paid"]["count"] += 1
                summary["paid"]["amount"] = round(summary["paid"]["amount"] + pay_tax, 2)
                paid_rows.append(
                    _row_from_term(
                        payload=payload,
                        source=source,
                        term=term,
                        due=due,
                        pay_tax=pay_tax,
                        paid=paid,
                        unpaid=0.0,
                        status="paid",
                        days_until=days_until,
                        attachments=attachments,
                    )
                )
                continue

            status, days_until = classify_status(due, today_value)
            summary[status]["count"] += 1
            summary[status]["amount"] = round(summary[status]["amount"] + unpaid, 2)
            if status not in allowed:
                continue

            unpaid_rows.append(
                _row_from_term(
                    payload=payload,
                    source=source,
                    term=term,
                    due=due,
                    pay_tax=pay_tax,
                    paid=paid,
                    unpaid=unpaid,
                    status=status,
                    days_until=days_until,
                    attachments=attachments,
                )
            )

    unpaid_rows.sort(
        key=lambda item: (item["daysUntilDue"], -float(item["unpaidAmount"]), item["contractCode"], str(item.get("payPeriod") or ""))
    )
    paid_rows.sort(key=lambda item: item["dueDate"], reverse=True)
    return unpaid_rows, paid_rows, summary


def contract_overdue(
    month: Optional[str] = None,
    statuses: Optional[list[str]] = None,
    *,
    kick: bool = True,
    store: ContractCacheStore | None = None,
) -> dict[str, Any]:
    del month  # 月份筛选已废弃
    start, end = rolling_12m_range()
    cache = store or get_cache_store()

    if kick:
        kick_sync(ROLLING_SYNC_KEY, store=cache)

    status_set = {item.strip() for item in (statuses or list(DEFAULT_STATUSES)) if item.strip()}
    if not status_set:
        status_set = set(DEFAULT_STATUSES)

    cached = cache.get_all()
    payloads = [item.payload for item in cached]
    rows, paid_rows, summary = build_rows_from_payloads(payloads, statuses=status_set)
    sync = get_sync_status(ROLLING_SYNC_KEY, cache)

    return {
        "scope": ROLLING_SYNC_KEY,
        "range": {"start": start, "end": end},
        "query": {"statuses": sorted(status_set)},
        "summary": summary,
        "rows": rows,
        "paidRows": paid_rows,
        "meta": {
            "cachedContractCount": len(cached),
            "rowCount": len(rows),
            "paidRowCount": len(paid_rows),
            "updatedAt": sync.get("updatedAt") or "",
            "sync": sync,
            "emptyCache": len(cached) == 0,
        },
    }
