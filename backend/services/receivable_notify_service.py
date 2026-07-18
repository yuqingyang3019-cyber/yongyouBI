from __future__ import annotations

from datetime import date
from typing import Any

from backend.clients.dingtalk.message_api import send_robot_markdown_to_users
from backend.clients.dingtalk.openapi_client import DingTalkOpenApiClient
from backend.config import optional_env
from backend.db.receivable_store import ReceivableCacheStore, get_receivable_store
from backend.services.overdue_service import (
    TRUE_OVERDUE_STATUS,
    _contracts_by_code,
    build_receivable_charts,
    build_receivable_rows,
)
from backend.services.receivable_match_service import allocate_collections_to_invoices


def _include_upcoming() -> bool:
    return optional_env("RECEIVABLE_NOTIFY_INCLUDE_UPCOMING", "true").lower() in {"1", "true", "yes"}


def _top_n() -> int:
    try:
        return max(1, int(optional_env("RECEIVABLE_NOTIFY_TOP_N", "15")))
    except ValueError:
        return 15


def _format_money(amount: float) -> str:
    return f"¥{amount:,.2f}"


def build_overdue_digest_markdown(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    *,
    today: date | None = None,
    top_n: int | None = None,
    include_upcoming: bool | None = None,
) -> tuple[str, str]:
    today_value = today or date.today()
    limit = top_n if top_n is not None else _top_n()
    with_upcoming = _include_upcoming() if include_upcoming is None else include_upcoming

    overdue_rows = [row for row in rows if row.get("trueStatus") == TRUE_OVERDUE_STATUS]
    upcoming_rows = [row for row in rows if row.get("trueStatus") == "upcoming"] if with_upcoming else []
    overdue_rows.sort(key=lambda item: (int(item.get("daysUntilDue") or 0), -float(item.get("taxAmount") or 0)))

    title = f"应收逾期日报 {today_value.isoformat()}"
    overdue_summary = summary.get("overdue") or {}
    upcoming_summary = summary.get("upcoming") or {}
    lines = [
        f"### {title}",
        "",
        f"- 已逾期 **{overdue_summary.get('count', 0)}** 笔，合计 **{_format_money(float(overdue_summary.get('amount') or 0))}**",
    ]
    if with_upcoming:
        lines.append(
            f"- 7 天内到期 **{upcoming_summary.get('count', 0)}** 笔，合计 **{_format_money(float(upcoming_summary.get('amount') or 0))}**"
        )
    lines.append("")

    if overdue_rows:
        lines.append("**逾期 TOP**")
        for index, row in enumerate(overdue_rows[:limit], start=1):
            overdue_days = abs(int(row.get("daysUntilDue") or 0))
            lines.append(
                f"{index}. {row.get('customer')} · {row.get('invoiceCode')} · 逾期 {overdue_days} 天 · 未收 {_format_money(float(row.get('outstanding') or row.get('taxAmount') or 0))}"
            )
        lines.append("")
    else:
        lines.append("当前无逾期应收发票。")
        lines.append("")

    if with_upcoming and upcoming_rows:
        lines.append("**即将逾期（7天内）**")
        upcoming_rows.sort(key=lambda item: int(item.get("daysUntilDue") or 0))
        for index, row in enumerate(upcoming_rows[: min(5, limit)], start=1):
            lines.append(
                f"{index}. {row.get('customer')} · {row.get('invoiceCode')} · {int(row.get('daysUntilDue') or 0)} 天后到期 · {_format_money(float(row.get('taxAmount') or 0))}"
            )
        lines.append("")

    lines.append("请打开 YonBIP BI「应收逾期」查看明细。")
    return title, "\n".join(lines)


def load_receivable_snapshot(store: ReceivableCacheStore | None = None) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    cache = store or get_receivable_store()
    invoices = [item.payload for item in cache.get_all_sale_invoices()]
    contracts = [item.payload for item in cache.get_all_sale_contracts()]
    collections = [item.payload for item in cache.get_all_collections()]
    allocations = allocate_collections_to_invoices(invoices, collections)
    rows, pending, unmatched, settled, summary = build_receivable_rows(
        invoices,
        _contracts_by_code(contracts),
        allocations=allocations,
        statuses={"overdue", "upcoming", "normal"},
    )
    cache.replace_receivable_facts(rows + pending + unmatched + settled)
    charts = build_receivable_charts(rows)
    return rows, summary, charts


def send_receivable_digest(
    user_ids: list[str],
    *,
    store: ReceivableCacheStore | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    unique_user_ids = list(dict.fromkeys(item.strip() for item in user_ids if item.strip()))
    if not unique_user_ids:
        raise ValueError("接收人不能为空")
    if len(unique_user_ids) > 20:
        raise ValueError("单个任务最多选择 20 人")
    rows, summary, charts = load_receivable_snapshot(store)
    title, text = build_overdue_digest_markdown(rows, summary)
    if dry_run:
        return {
            "dryRun": True,
            "title": title,
            "text": text,
            "recipients": unique_user_ids,
            "overdueCount": (summary.get("overdue") or {}).get("count", 0),
            "charts": charts,
        }

    client = DingTalkOpenApiClient.from_env()
    if client is None:
        raise RuntimeError("未配置 DINGTALK_APP_KEY / DINGTALK_APP_SECRET")

    result = send_robot_markdown_to_users(
        client,
        user_ids=unique_user_ids,
        title=title,
        text=text,
    )
    return {
        "title": title,
        "sent": result["sent"],
        "recipients": unique_user_ids,
        "overdueCount": (summary.get("overdue") or {}).get("count", 0),
    }
