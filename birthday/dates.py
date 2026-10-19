"""Date parsing and leap-day celebration helpers (stdlib only)."""

import re
from datetime import date
from typing import Dict, Optional


_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{4}))?$")


def parse_birthday(value: str, today: Optional[date] = None) -> Dict[str, Optional[int]]:
    """Parse MM/DD or MM/DD/YYYY and reject invalid/future birthdates."""
    today = today or date.today()
    match = _DATE_RE.fullmatch(value.strip())
    if not match:
        raise ValueError("Use MM/DD/YYYY (e.g. 01/01/2000) or MM/DD.")

    month, day = int(match.group(1)), int(match.group(2))
    year = int(match.group(3)) if match.group(3) else None
    try:
        birth_date = date(year if year is not None else 2000, month, day)
    except ValueError:
        raise ValueError("That isn't a valid calendar date.") from None

    if year is not None:
        if year < 1900:
            raise ValueError("Please use a birth year of 1900 or later.")
        if birth_date > today:
            raise ValueError("A birthday can't be in the future.")

    return {"month": month, "day": day, "year": year}


def observed_date(year: int, month: int, day: int) -> date:
    """Observe Feb 29 on Feb 28 in non-leap years."""
    if month == 2 and day == 29:
        try:
            return date(year, 2, 29)
        except ValueError:
            return date(year, 2, 28)
    return date(year, month, day)


def next_birthday(today: date, month: int, day: int) -> date:
    this_year = observed_date(today.year, month, day)
    return this_year if this_year >= today else observed_date(today.year + 1, month, day)


def display_day(month: int, day: int) -> str:
    return f"{month:02d}/{day:02d}"


def age_on(occurrence: date, birth_year: Optional[int]) -> Optional[int]:
    return occurrence.year - birth_year if birth_year is not None else None
