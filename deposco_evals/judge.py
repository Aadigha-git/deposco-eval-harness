"""LLM judge for response_quality: grades grounding and behaviour as PASS, FLAG, or FAIL."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from deposco_evals.llm import Complete
from deposco_evals.snapshot import Snapshot

RUBRIC = Path(__file__).with_name("judge_rubric.md")
VERDICTS = ("PASS", "FLAG", "FAIL")
VERDICT_FIELDS = {"verdict", "reason", "evidence"}
CODE_FENCE = re.compile(r"\A```(?:json)?\s*(?P<body>.*?)\s*```\Z", re.DOTALL | re.IGNORECASE)


class JudgeOutputError(ValueError):
    """The judge's reply is not a valid verdict; the case must not be graded from it."""

    raw_output: str | None = None


@dataclass(frozen=True)
class JudgeVerdict:
    verdict: str
    reason: str
    evidence: tuple[str, ...]


def judge_reply(snapshot: Snapshot, question: str, reply: str, complete: Complete, model: str) -> JudgeVerdict:
    judge_input = {
        "reference_date": snapshot.today.isoformat(),
        "data_file": snapshot.source_name,
        "question": question,
        "assistant_reply": reply,
        "orders_csv": snapshot.raw_csv,
    }
    rubric = RUBRIC.read_text(encoding="utf-8")
    text = complete(rubric, json.dumps(judge_input, ensure_ascii=False), model)
    try:
        return _parse_verdict(text)
    except JudgeOutputError as error:
        error.raw_output = text
        raise


def _parse_verdict(text: str) -> JudgeVerdict:
    text = text.strip()
    fenced = CODE_FENCE.fullmatch(text)
    if fenced:
        text = fenced.group("body")
    try:
        parsed = json.loads(text, object_pairs_hook=_reject_repeated_fields)
    except JudgeOutputError:
        raise
    except ValueError:
        parsed = None
    if not isinstance(parsed, dict):
        raise JudgeOutputError(f"judge output is not a single JSON object: {text[:80]!r}")

    if VERDICT_FIELDS - parsed.keys():
        missing = ", ".join(sorted(VERDICT_FIELDS - parsed.keys()))
        raise JudgeOutputError(f"judge output is missing field(s): {missing}")
    if parsed.keys() - VERDICT_FIELDS:
        unexpected = ", ".join(sorted(parsed.keys() - VERDICT_FIELDS))
        raise JudgeOutputError(f"judge output has unexpected field(s): {unexpected}")
    verdict, reason, evidence = parsed["verdict"], parsed["reason"], parsed["evidence"]
    if verdict not in VERDICTS:
        expected = f"{', '.join(VERDICTS[:-1])}, or {VERDICTS[-1]}"
        raise JudgeOutputError(f"invalid verdict {verdict!r} (expected {expected})")
    if not isinstance(reason, str) or not reason.strip():
        raise JudgeOutputError("judge reason must be a non-empty string")
    if not isinstance(evidence, list) or not all(isinstance(item, str) and item.strip() for item in evidence):
        raise JudgeOutputError("judge evidence must be a list of non-empty strings")
    if verdict != "FLAG" and not evidence:
        raise JudgeOutputError(f"a {verdict} verdict needs at least one evidence item")
    return JudgeVerdict(verdict, reason.strip(), tuple(evidence))


def _reject_repeated_fields(pairs: list[tuple[str, object]]) -> dict:
    keys = [key for key, _ in pairs]
    repeated = sorted({key for key in keys if keys.count(key) > 1})
    if repeated:
        raise JudgeOutputError(f"judge output repeats field(s): {', '.join(repeated)}")
    return dict(pairs)
