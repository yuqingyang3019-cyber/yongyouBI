from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


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
