from __future__ import annotations

from typing import Any

from backend.db.receivable_store import get_receivable_store
from backend.services.receivable_notify_service import load_receivable_snapshot


_HELP_TEXT = (
    "我目前支持应收概览问题，例如：\n"
    "• 当前逾期金额是多少？\n"
    "• 7 天内到期有多少笔？\n"
    "• 当前未结应收情况\n"
    "更复杂的明细查询请打开应用中的「智能问数」。"
)


def _money(value: Any) -> str:
    return f"¥{float(value or 0):,.2f}"


def answer_receivable_question(question: str) -> str:
    normalized = question.strip()
    if not normalized or len(normalized) > 500:
        return "请 @我并发送不超过 500 个字符的应收问题。"

    if not any(word in normalized for word in ("应收", "逾期", "到期", "收款", "发票", "回款")):
        return _HELP_TEXT

    rows, summary, _ = load_receivable_snapshot()
    overdue = summary.get("overdue") or {}
    upcoming = summary.get("upcoming") or {}
    store = get_receivable_store()
    return "\n".join(
        [
            "应收账款概览",
            f"• 已逾期：{int(overdue.get('count') or 0)} 笔，{_money(overdue.get('amount'))}",
            f"• 7 天内到期：{int(upcoming.get('count') or 0)} 笔，{_money(upcoming.get('amount'))}",
            f"• 当前未结发票：{len(rows)} 笔",
            f"• 缓存收款：{store.count_all_collections()} 笔",
            "数据来自当前缓存；请在应用右上角手动同步后获取最新上游数据。",
        ]
    )
