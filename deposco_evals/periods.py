"""The assignment's date windows, always relative to a snapshot's `today`, never the clock."""

import calendar
from datetime import date, timedelta

Window = tuple[date, date]


def last_7_days(today: date) -> Window:
    return today - timedelta(days=6), today


def this_month(today: date) -> Window:
    last_day = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=1), today.replace(day=last_day)


def within(day: date | None, window: Window) -> bool:
    start, end = window
    return day is not None and start <= day <= end


def before_this_month(day: date, today: date) -> bool:
    first_of_month, _ = this_month(today)
    return day < first_of_month


def format_window(window: Window) -> str:
    start, end = window
    return f"{start.isoformat()} to {end.isoformat()}"
