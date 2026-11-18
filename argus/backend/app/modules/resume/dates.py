"""Turn the model's copied date strings into real dates. Arithmetic lives here, in code."""

from __future__ import annotations

from datetime import date

_MONTH_NAMES = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_MONTHS = {m: i for i, m in enumerate(_MONTH_NAMES, 1)}


def parse_month_year(value: str | None, *, today: date | None = None) -> date | None:
    """'Jun 2025' -> 2025-06-01, '2025' -> 2025-01-01, 'Present' -> first of this month."""
    if not value:
        return None
    text = value.strip()
    if text.lower() == "present":
        today = today or date.today()
        return today.replace(day=1)
    parts = text.split()
    try:
        if len(parts) == 2 and parts[0][:3].lower() in _MONTHS:
            return date(int(parts[1]), _MONTHS[parts[0][:3].lower()], 1)
        if len(parts) == 1:
            return date(int(parts[0]), 1, 1)
    except ValueError:
        return None
    return None


def months_between(start: date | None, end: date | None) -> int | None:
    """Inclusive month count: Jun 2025 - Aug 2025 = 3."""
    if start is None or end is None or end < start:
        return None
    return (end.year - start.year) * 12 + (end.month - start.month) + 1
