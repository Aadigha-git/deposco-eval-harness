"""Independent cross-check of the expected answers for one orders CSV.

Shares no code with `deposco_evals` and deliberately uses different techniques
(raw csv rows, ISO-string month prefixes, day ordinals for the 7-day window), so
a bug in the ground-truth rules is unlikely to be repeated here.

Usage: python scripts/crosscheck_expected.py data/orders_2026-11-10.csv
Prints one JSON object: case ID -> expected value (refusal cases are null).
"""

import csv
import json
import re
import sys
from collections import Counter
from datetime import date


def day_number(iso: str) -> int:
    year, month, day = (int(part) for part in iso.split("-"))
    return date(year, month, day).toordinal()


def tied_top(counter: Counter) -> list:
    if not counter:
        return []
    best = max(counter.values())
    return sorted(key for key, count in counter.items() if count == best)


def crosscheck(path: str) -> dict:
    today = re.search(r"orders_(\d{4}-\d{2}-\d{2})\.csv$", path).group(1)
    month = today[:7]
    today_number = day_number(today)
    with open(path, newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))

    def in_last_7_days(iso: str) -> bool:
        return bool(iso) and today_number - 6 <= day_number(iso) <= today_number

    def in_this_month(iso: str) -> bool:
        return iso[:7] == month

    shipped = [row for row in rows if row["status"] == "shipped"]
    open_rows = [row for row in rows if row["status"] == "open"]
    cancelled = [row for row in rows if row["status"] == "cancelled"]

    return {
        "P1": len(open_rows),
        "P2": sum(1 for row in cancelled if in_this_month(row["order_date"])),
        "P3": sum(1 for row in shipped if row["ship_date"] == today),
        "P4": sum(
            int(row["units"])
            for row in shipped
            if row["carrier"] == "UPS" and in_last_7_days(row["ship_date"])
        ),
        "P5": sum(int(row["units"]) for row in open_rows),
        "P6": tied_top(Counter(row["customer"] for row in open_rows)),
        "P7": sum(1 for row in shipped if row["carrier"] == "DHL"),
        "P8": None,
        "P9": sum(
            int(row["units"])
            for row in rows
            if row["status"] != "cancelled" and in_last_7_days(row["order_date"])
        ),
        "P10": tied_top(Counter(row["carrier"] for row in shipped if in_this_month(row["ship_date"]))),
        "P11": sum(1 for row in rows if row["status"] == "returned"),
        "P12": None,
        "C1": sorted(int(row["order_id"]) for row in open_rows),
        "C2": tied_top(Counter(row["customer"] for row in cancelled)),
        "C3": sum(
            1
            for row in shipped
            if row["order_date"][:7] < month and in_this_month(row["ship_date"])
        ),
    }


if __name__ == "__main__":
    print(json.dumps(crosscheck(sys.argv[1]), indent=2))
