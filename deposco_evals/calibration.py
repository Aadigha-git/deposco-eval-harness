"""Compare judge verdicts with the committed human calibration labels; verdicts stay categorical."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from deposco_evals.cases import load_cases
from deposco_evals.judge import RUBRIC, VERDICTS, JudgeOutputError, JudgeVerdict, judge_reply
from deposco_evals.llm import LLMError, config_from_env, make_complete
from deposco_evals.report import _no_html, _one_line
from deposco_evals.snapshot import Snapshot, SnapshotError, load_snapshot

Judge = Callable[[Snapshot, str, str], JudgeVerdict]
"""judge(snapshot, question, reply) -> verdict"""

JUDGE_ERROR = "ERROR"


@dataclass(frozen=True)
class Label:
    id: str
    case_id: str
    data_file: str
    source: str
    response: str
    human_verdict: str
    human_rationale: str


@dataclass(frozen=True)
class Prediction:
    label: Label
    judged: JudgeVerdict | None
    error: str | None = None
    raw_output: str | None = None

    @property
    def judge_verdict(self) -> str:
        return self.judged.verdict if self.judged else JUDGE_ERROR

    @property
    def agrees(self) -> bool:
        return self.judge_verdict == self.label.human_verdict


@dataclass(frozen=True)
class Agreement:
    exact: int
    pass_vs_not_pass: int
    total: int
    matrix: dict[str, dict[str, int]]
    per_class: dict[str, tuple[int, int]]
    """human verdict -> (examples the judge matched, examples with that human verdict)"""
    disagreements: list[Prediction]
    errors: list[Prediction]


@dataclass(frozen=True)
class RunInfo:
    judge_model: str
    run_at: str
    rubric_sha256: str
    labels_sha256: str


def load_labels(path: Path) -> list[Label]:
    return [Label(**entry) for entry in json.loads(Path(path).read_text(encoding="utf-8"))]


def judge_labels(labels: list[Label], judge: Judge, labels_root: Path) -> list[Prediction]:
    """Judges each label exactly once; a failed call is recorded, never retried."""
    inputs = _validated_inputs(labels, Path(labels_root))
    predictions = []
    for label, (snapshot, question) in zip(labels, inputs):
        try:
            predictions.append(Prediction(label, judge(snapshot, question, label.response)))
        except JudgeOutputError as error:
            predictions.append(Prediction(label, None, str(error), error.raw_output))
        except LLMError as error:
            predictions.append(Prediction(label, None, str(error)))
        except Exception as error:  # one paid, unrepeatable run: keep every other result
            predictions.append(Prediction(label, None, f"{type(error).__name__}: {error}"))
    return predictions


def agreement(predictions: list[Prediction]) -> Agreement:
    matrix = {human: {judged: 0 for judged in VERDICTS} for human in VERDICTS}
    for prediction in predictions:
        if prediction.judged:
            matrix[prediction.label.human_verdict][prediction.judge_verdict] += 1
    per_class = {
        human: (matrix[human][human], sum(1 for p in predictions if p.label.human_verdict == human))
        for human in VERDICTS
    }
    return Agreement(
        exact=sum(p.agrees for p in predictions),
        pass_vs_not_pass=sum(
            1 for p in predictions if p.judged and (p.judge_verdict == "PASS") == (p.label.human_verdict == "PASS")
        ),
        total=len(predictions),
        matrix=matrix,
        per_class=per_class,
        disagreements=[p for p in predictions if not p.agrees],
        errors=[p for p in predictions if not p.judged],
    )


def render_report(predictions: list[Prediction], run: RunInfo) -> str:
    result = agreement(predictions)
    lines = [
        "# Judge calibration report",
        "",
        f"- Judge model: {run.judge_model}",
        f"- Run at: {run.run_at} (one judge call per example, no retries)",
        f"- Rubric: `deposco_evals/judge_rubric.md` (sha256 `{run.rubric_sha256[:12]}`)",
        f"- Labels: `calibration/labels.json` (sha256 `{run.labels_sha256[:12]}`)",
        "- Verdicts are categorical: FLAG is its own class, never partial credit.",
        "",
        "## Agreement",
        "",
        f"Exact: the judge's verdict equals the human verdict on **{result.exact} of {result.total}** "
        f"examples ({_percent(result.exact, result.total)}).",
        "",
        f"PASS versus not-PASS: **{result.pass_vs_not_pass} of {result.total}** examples "
        f"({_percent(result.pass_vs_not_pass, result.total)}), with FLAG and FAIL both counted as not-PASS.",
        "",
        "## Confusion matrix",
        "",
        "Rows are the human verdict, columns the judge verdict.",
        "",
        "| human \\ judge | " + " | ".join(VERDICTS) + " |",
        "|---|" + "---|" * len(VERDICTS),
    ]
    lines += [
        f"| **{human}** | " + " | ".join(str(result.matrix[human][judged]) for judged in VERDICTS) + " |"
        for human in VERDICTS
    ]
    lines += [
        "",
        f"Judge errors (outside the matrix): {len(result.errors)}",
        "",
        "## Per-class agreement",
        "",
        "Of the examples a human labelled with each verdict, how many the judge matched. Judge errors count as misses.",
        "",
        "| Human verdict | Judge agreed | Agreement |",
        "|---|---|---|",
    ]
    lines += [
        f"| {human} | {matched} of {total} | {_percent(matched, total)} |"
        for human, (matched, total) in result.per_class.items()
    ]
    lines += ["", "## Disagreements", ""]
    if not result.disagreements:
        lines.append("None.")
    for prediction in result.disagreements:
        lines += _disagreement_section(prediction)
    return "\n".join(lines) + "\n"


def write_calibration(predictions: list[Prediction], run: RunInfo, out_dir: Path) -> None:
    predictions_path, report_path = _output_paths(Path(out_dir))
    for path in (predictions_path, report_path):
        if path.exists():
            raise FileExistsError(f"{path} already exists; calibration results are written once, never overwritten")
    payload = {**asdict(run), "predictions": [_prediction_record(p) for p in predictions]}
    predictions_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    report_text = render_report(predictions, run)
    with predictions_path.open("x", encoding="utf-8") as file:
        file.write(predictions_text)
    with report_path.open("x", encoding="utf-8") as file:
        file.write(report_text)


def main(
    labels_path: Path = Path("calibration/labels.json"),
    out_dir: Path = Path("calibration"),
    repo_root: Path = Path("."),
) -> None:
    for path in _output_paths(out_dir):
        if path.exists():
            raise SystemExit(f"{path} already exists; calibration runs once and is never re-run")
    config = config_from_env()
    complete = make_complete(config)

    def judge(snapshot: Snapshot, question: str, reply: str) -> JudgeVerdict:
        return judge_reply(snapshot, question, reply, complete, config.judge_model)

    predictions = judge_labels(load_labels(labels_path), judge, labels_root=repo_root)
    run = RunInfo(
        judge_model=config.judge_model,
        run_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        rubric_sha256=_sha256(RUBRIC),
        labels_sha256=_sha256(labels_path),
    )
    write_calibration(predictions, run, out_dir)
    result = agreement(predictions)
    print(f"exact agreement {result.exact}/{result.total}; wrote {', '.join(map(str, _output_paths(out_dir)))}")


def _validated_inputs(labels: list[Label], labels_root: Path) -> list[tuple[Snapshot, str]]:
    questions = {case.id: case.question for case in load_cases()}
    inputs = []
    for label in labels:
        if label.case_id not in questions:
            raise ValueError(f"{label.id}: unknown case_id {label.case_id!r}")
        if label.human_verdict not in VERDICTS:
            raise ValueError(f"{label.id}: invalid human_verdict {label.human_verdict!r}")
        try:
            snapshot = load_snapshot(labels_root / label.data_file)
        except (OSError, SnapshotError) as error:
            raise ValueError(f"{label.id}: cannot load {label.data_file}: {error}") from None
        inputs.append((snapshot, questions[label.case_id]))
    return inputs


def _output_paths(out_dir: Path) -> tuple[Path, Path]:
    return out_dir / "predictions.json", out_dir / "report.md"


def _disagreement_section(prediction: Prediction) -> list[str]:
    label = prediction.label
    lines = [
        f"### {label.id}: {label.case_id} on {Path(label.data_file).name} "
        f"(human {label.human_verdict}, judge {prediction.judge_verdict})",
        "",
        f"Source: {label.source}",
        "",
        *(f"> {_no_html(line)}" if line else ">" for line in label.response.splitlines()),
        "",
        f"**Human rationale:** {_one_line(label.human_rationale)}",
        "",
    ]
    if prediction.judged:
        lines += [f"**Judge reason:** {_one_line(prediction.judged.reason)}", "", "**Judge evidence:**", ""]
        lines += [f"- {_one_line(item)}" for item in prediction.judged.evidence] or ["- (none)"]
    else:
        lines.append(f"**Judge error:** {_one_line(prediction.error)}")
    return lines + [""]


def _prediction_record(prediction: Prediction) -> dict:
    label, judged = prediction.label, prediction.judged
    return {
        "id": label.id,
        "case_id": label.case_id,
        "data_file": label.data_file,
        "human_verdict": label.human_verdict,
        "judge_verdict": prediction.judge_verdict,
        "judge_reason": judged.reason if judged else None,
        "judge_evidence": list(judged.evidence) if judged else [],
        "error": prediction.error,
        "judge_raw_output": prediction.raw_output,
        "agrees": prediction.agrees,
    }


def _percent(part: int, whole: int) -> str:
    return f"{round(100 * part / whole)}%" if whole else "n/a"


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
