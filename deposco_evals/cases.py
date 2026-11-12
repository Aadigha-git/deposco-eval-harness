"""The golden dataset: case IDs, categories, questions, and refusal behaviour, never computed answers."""

import json
from dataclasses import dataclass
from pathlib import Path

GOLDEN_CASES = Path(__file__).with_name("golden_cases.json")


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    question: str
    expected_behavior: str | None = None


def load_cases(path: Path = GOLDEN_CASES) -> list[Case]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    return [Case(**entry) for entry in entries]
