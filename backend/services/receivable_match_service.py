from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.value_utils import as_decimal, as_text
from backend.services.receivable_sync_service import invoice_contract_ref


@dataclass(frozen=True)
class CollectionLine:
    collection_id: str
    collection_code: str
    order_no: str
    invoice_code: str
    contract_code: str
    customer: str
    amount: float
    bill_date: str


@dataclass(frozen=True)
class InvoiceMatchTarget:
    invoice_id: str
    invoice_code: str
    contract_code: str
    customer: str
    tax_amount: float
    audit_time: str
    order_nos: tuple[str, ...]


@dataclass(frozen=True)
class InvoiceAllocation:
    collected_amount: float
    match_quality: str


def _money(value: Any) -> float:
    return float(as_decimal(value))


def _normalize_key(value: Any) -> str:
    return as_text(value).strip()


def _invoice_order_nos(payload: dict[str, Any]) -> tuple[str, ...]:
    lines = payload.get("saleInvoiceDetails") or payload.get("details") or []
    if not isinstance(lines, list):
        return ()
    result: list[str] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        order_no = _normalize_key(line.get("orderNo"))
        if order_no:
            result.append(order_no)
    return tuple(dict.fromkeys(result))


def extract_collection_lines(payload: dict[str, Any]) -> list[CollectionLine]:
    collection_id = _normalize_key(payload.get("id"))
    collection_code = _normalize_key(payload.get("code"))
    header_customer = _normalize_key(payload.get("customerName") or payload.get("bodyItemCustomerName"))
    header_order_no = _normalize_key(payload.get("orderNo") or payload.get("bodyItem_orderNo"))
    header_invoice_code = _normalize_key(payload.get("bodyItem_invoiceNo") or payload.get("invoiceNo"))
    header_contract_code = _normalize_key(payload.get("contractNo") or payload.get("bodyItem_contractNo"))
    bill_date = _normalize_key(payload.get("billDate") or payload.get("bodyItemPubts"))

    body_items = payload.get("bodyItem")
    if isinstance(body_items, list) and body_items:
        lines: list[CollectionLine] = []
        for item in body_items:
            if not isinstance(item, dict):
                continue
            amount = _money(item.get("oriTaxIncludedAmount"))
            if amount <= 0:
                continue
            lines.append(
                CollectionLine(
                    collection_id=collection_id,
                    collection_code=collection_code,
                    order_no=_normalize_key(item.get("orderNo")) or header_order_no,
                    invoice_code=_normalize_key(item.get("invoiceNo")) or header_invoice_code,
                    contract_code=_normalize_key(item.get("contractNo")) or header_contract_code,
                    customer=_normalize_key(item.get("customerName")) or header_customer,
                    amount=amount,
                    bill_date=bill_date,
                )
            )
        return lines

    amount = _money(
        payload.get("bodyItemOriTaxIncludedAmount")
        or payload.get("oriTaxIncludedAmount")
        or payload.get("bodyItemLocalTaxIncludedAmount")
    )
    if amount <= 0:
        return []
    return [
        CollectionLine(
            collection_id=collection_id,
            collection_code=collection_code,
            order_no=header_order_no or _normalize_key(payload.get("bodyItem_orderNo")),
            invoice_code=header_invoice_code,
            contract_code=header_contract_code,
            customer=header_customer or _normalize_key(payload.get("bodyItemCustomerName")),
            amount=amount,
            bill_date=bill_date,
        )
    ]


def build_invoice_targets(invoices: list[dict[str, Any]]) -> list[InvoiceMatchTarget]:
    targets: list[InvoiceMatchTarget] = []
    for payload in invoices:
        invoice_id = _normalize_key(payload.get("id"))
        if not invoice_id:
            continue
        invoice_code = _normalize_key(payload.get("code"))
        customer = _normalize_key(payload.get("agentName") or payload.get("agentId_name")) or "未填写"
        contract_code, _contract_id = invoice_contract_ref(payload)
        tax_amount = 0.0
        for key in ("oriSum", "natSum", "totalPriceTax"):
            tax_amount = _money(payload.get(key))
            if tax_amount:
                break
        targets.append(
            InvoiceMatchTarget(
                invoice_id=invoice_id,
                invoice_code=invoice_code,
                contract_code=contract_code,
                customer=customer,
                tax_amount=tax_amount,
                audit_time=_normalize_key(payload.get("auditTime")),
                order_nos=_invoice_order_nos(payload),
            )
        )
    return targets


def _apply_fifo(
    lines: list[CollectionLine],
    targets: list[InvoiceMatchTarget],
    allocations: dict[str, float],
    qualities: dict[str, str],
    *,
    quality: str = "estimated",
) -> None:
    if not lines or not targets:
        return

    remaining = [line for line in lines if line.amount > 0]
    sorted_targets = sorted(targets, key=lambda item: item.audit_time or item.invoice_code)
    for line in remaining:
        amount_left = line.amount
        for target in sorted_targets:
            if amount_left <= 0:
                break
            outstanding = round(target.tax_amount - allocations[target.invoice_id], 2)
            if outstanding <= 0.01:
                continue
            applied = min(amount_left, outstanding)
            allocations[target.invoice_id] = round(allocations[target.invoice_id] + applied, 2)
            qualities[target.invoice_id] = quality
            amount_left = round(amount_left - applied, 2)


def allocate_collections_to_invoices(
    invoices: list[dict[str, Any]],
    collections: list[dict[str, Any]],
) -> dict[str, InvoiceAllocation]:
    targets = build_invoice_targets(invoices)
    if not targets:
        return {}

    allocations: dict[str, float] = {target.invoice_id: 0.0 for target in targets}
    qualities: dict[str, str] = {target.invoice_id: "unpaid" for target in targets}

    order_to_invoice: dict[str, str] = {}
    code_to_invoice: dict[str, str] = {}
    for target in targets:
        for order_no in target.order_nos:
            order_to_invoice.setdefault(order_no, target.invoice_id)
        if target.invoice_code:
            code_to_invoice[target.invoice_code] = target.invoice_id

    unmatched_lines: list[CollectionLine] = []
    for payload in collections:
        for line in extract_collection_lines(payload):
            matched_invoice_id = ""
            if line.order_no and line.order_no in order_to_invoice:
                matched_invoice_id = order_to_invoice[line.order_no]
                qualities[matched_invoice_id] = "exact"
            elif line.invoice_code and line.invoice_code in code_to_invoice:
                matched_invoice_id = code_to_invoice[line.invoice_code]
                qualities[matched_invoice_id] = "exact"
            elif line.order_no and line.order_no in code_to_invoice:
                matched_invoice_id = code_to_invoice[line.order_no]
                qualities[matched_invoice_id] = "exact"

            if matched_invoice_id:
                allocations[matched_invoice_id] = round(allocations[matched_invoice_id] + line.amount, 2)
            else:
                unmatched_lines.append(line)

    buckets: dict[tuple[str, str], list[InvoiceMatchTarget]] = {}
    contract_buckets: dict[str, list[InvoiceMatchTarget]] = {}
    for target in targets:
        if target.contract_code:
            buckets.setdefault((target.contract_code, target.customer), []).append(target)
            contract_buckets.setdefault(target.contract_code, []).append(target)

    contract_lines: list[CollectionLine] = []
    customer_lines: list[CollectionLine] = []
    for line in unmatched_lines:
        if line.amount <= 0:
            continue
        if line.contract_code and line.contract_code in contract_buckets:
            contract_lines.append(line)
        else:
            customer_lines.append(line)

    for line in contract_lines:
        _apply_fifo([line], contract_buckets.get(line.contract_code, []), allocations, qualities, quality="contract")

    for (contract_code, customer), bucket_targets in buckets.items():
        bucket_customer_lines = [
            line
            for line in customer_lines
            if line.amount > 0 and (not line.customer or line.customer == customer)
        ]
        _apply_fifo(bucket_customer_lines, bucket_targets, allocations, qualities)

    result: dict[str, InvoiceAllocation] = {}
    for target in targets:
        collected = round(allocations.get(target.invoice_id, 0.0), 2)
        quality = qualities.get(target.invoice_id, "unpaid")
        if collected <= 0:
            quality = "unpaid"
        elif collected + 0.01 < target.tax_amount and quality == "exact":
            quality = "partial_exact"
        result[target.invoice_id] = InvoiceAllocation(
            collected_amount=collected,
            match_quality=quality,
        )
    return result
