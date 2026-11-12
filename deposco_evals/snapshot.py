"""Load one orders CSV into a snapshot whose `today` comes from the file name."""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

FILENAME_PATTERN = re.compile(r"orders_(\d{4}-\d{2}-\d{2})\.csv")
COLUMNS = ["order_id", "customer", "status", "carrier", "order_date", "ship_date", "units"]
STATUSES = ("open", "shipped", "cancelled")
CARRIERS = ("UPS", "FedEx", "USPS")
MIN_UNITS, MAX_UNITS = 1, 50
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
INTEGER_PATTERN = re.compile(r"[0-9]+")


class SnapshotError(ValueError):
    """The data file is unsupported; the message names the file and the problem."""


@dataclass(frozen=True)
class Order:
    order_id: int
    customer: str
    status: str
    carrier: str
    order_date: date
    ship_date: date | None
    units: int


@dataclass(frozen=True)
class Snapshot:
    source_name: str
    today: date
    orders: tuple[Order, ...]
    raw_csv: str


def load_snapshot(path: str | Path) -> Snapshot:
    path = Path(path)
    today = _today_from_name(path.name)
    with path.open(encoding="utf-8-sig", newline="") as file:
        raw_csv = file.read()
    reader = csv.reader(io.StringIO(raw_csv))
    header = next(reader, [])
    if header != COLUMNS:
        raise SnapshotError(
            f"{path.name}: line 1: unsupported header {','.join(header)!r} "
            f"(expected {','.join(COLUMNS)!r})"
        )
    orders: list[Order] = []
    seen_ids: set[int] = set()
    for fields in reader:
        try:
            order = _parse_order(fields)
            if order.order_id in seen_ids:
                raise ValueError(f"duplicate order_id {order.order_id}")
        except ValueError as problem:
            raise SnapshotError(f"{path.name}: line {reader.line_num}: {problem}") from None
        seen_ids.add(order.order_id)
        orders.append(order)
    return Snapshot(source_name=path.name, today=today, orders=tuple(orders), raw_csv=raw_csv)


def _parse_order(fields: list[str]) -> Order:
    if len(fields) != len(COLUMNS):
        raise ValueError(f"expected {len(COLUMNS)} fields, got {len(fields)}")
    order_id, customer, status, carrier, order_date, ship_date, units = fields

    if not INTEGER_PATTERN.fullmatch(order_id):
        raise ValueError(f"order_id must be an integer, got {order_id!r}")
    if not customer:
        raise ValueError("customer must not be empty")
    if status not in STATUSES:
        raise ValueError(f"unsupported status {status!r} (expected one of: {', '.join(STATUSES)})")
    if carrier not in CARRIERS:
        raise ValueError(f"unsupported carrier {carrier!r} (expected one of: {', '.join(CARRIERS)})")
    parsed_order_date = _parse_date("order_date", order_date)
    parsed_ship_date = _parse_date("ship_date", ship_date) if ship_date else None
    if status == "shipped" and parsed_ship_date is None:
        raise ValueError("shipped order must have a ship_date")
    if status != "shipped" and parsed_ship_date is not None:
        raise ValueError(f"{status} order must not have a ship_date, got {ship_date!r}")
    if not (INTEGER_PATTERN.fullmatch(units) and MIN_UNITS <= int(units) <= MAX_UNITS):
        raise ValueError(f"units must be an integer from {MIN_UNITS} to {MAX_UNITS}, got {units!r}")

    return Order(
        order_id=int(order_id),
        customer=customer,
        status=status,
        carrier=carrier,
        order_date=parsed_order_date,
        ship_date=parsed_ship_date,
        units=int(units),
    )


def _parse_date(column: str, value: str) -> date:
    if DATE_PATTERN.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError(f"{column} must be a YYYY-MM-DD date, got {value!r}")


def _today_from_name(name: str) -> date:
    match = FILENAME_PATTERN.fullmatch(name)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            pass
    raise SnapshotError(f"{name}: file name must be orders_YYYY-MM-DD.csv with a real date")
