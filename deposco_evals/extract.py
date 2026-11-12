"""Read the value of a response's final `Answer:` line; never infer it from the explanation."""

import re

ANSWER_LINE = re.compile(
    r"^[ \t>*_`#-]*(?:final[ \t]+)?answer[*_`]*[ \t]*:(?P<value>.*)$", re.IGNORECASE | re.MULTILINE
)
WRAPPING = " \t*_`\"'"
NOT_IN_DATA = "NOT IN DATA"
REFUSED = "REFUSED"
ZERO_WORDS = ("zero", "none")


def parse_answer(response: str) -> str | None:
    """The unwrapped value of the last `Answer:` line, or None when there is no such line."""
    values = ANSWER_LINE.findall(response)
    return _unwrap(values[-1]) if values else None


def is_marker(value: str, marker: str) -> bool:
    return normalize_name(value) == normalize_name(marker)


def read_number(value: str) -> int | None:
    if re.fullmatch(r"[0-9]+", value):
        return int(value)
    return 0 if value.casefold() in ZERO_WORDS else None


def read_items(value: str) -> list[str]:
    """Comma-separated items, allowing a final "and" (A, B, and C); "A and B" stays one item."""
    items = []
    for piece in value.split(","):
        piece = piece.strip(WRAPPING)
        if piece.casefold().startswith("and "):
            piece = piece[4:].strip(WRAPPING)
        if piece:
            items.append(piece)
    return items


def normalize_name(name: str) -> str:
    return " ".join(name.split()).casefold()


def read_order_id(item: str) -> int | None:
    item = item.removeprefix("#")
    return int(item) if re.fullmatch(r"[0-9]+", item) else None


def _unwrap(value: str) -> str:
    value = value.strip().strip(WRAPPING).strip()
    if value.endswith(".") and not value.endswith(".."):
        value = value[:-1].strip().strip(WRAPPING).strip()
    return value
