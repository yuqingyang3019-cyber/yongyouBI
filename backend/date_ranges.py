from __future__ import annotations

from datetime import date


ROLLING_MONTHS = 12


def _next_day(day: str) -> str:
    year, month, date_part = (int(part) for part in day.split("-"))
    return date.fromordinal(date(year, month, date_part).toordinal() + 1).isoformat()


def rolling_12m_range(today: date | None = None) -> tuple[str, str]:
    today_value = today or date.today()
    year = today_value.year
    month = today_value.month - (ROLLING_MONTHS - 1)
    while month <= 0:
        month += 12
        year -= 1
    start = date(year, month, 1)
    return start.isoformat(), _next_day(today_value.isoformat())
