import hashlib
import json
import re
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from deposco_evals import calibration
from deposco_evals.calibration import (
    RunInfo,
    agreement,
    judge_labels,
    load_labels,
    render_report,
    write_calibration,
)
from deposco_evals.cases import load_cases
from deposco_evals.judge import JudgeOutputError, JudgeVerdict
from deposco_evals.llm import LLMError

ROOT = Path(__file__).resolve().parent.parent
LABELS = load_labels(ROOT / "calibration" / "labels.json")
QUESTIONS = {case.id: case.question for case in load_cases()}


class FakeJudge:
    """Returns a scripted verdict per reply and records every call."""

    def __init__(self, verdicts_by_label_id=None):
        self.verdicts = verdicts_by_label_id or {}
        self.calls = []

    def __call__(self, snapshot, question, reply):
        self.calls.append((snapshot, question, reply))
        label = next(label for label in LABELS if label.response == reply)
        scripted = self.verdicts.get(label.id)
        if isinstance(scripted, Exception):
            raise scripted
        verdict = scripted or label.human_verdict
        return JudgeVerdict(verdict, f"judge says {verdict}", (f"quote for {label.id}",))


def test_each_label_is_judged_exactly_once_with_its_snapshot_question_and_reply():
    judge = FakeJudge()

    judge_labels(LABELS, judge, labels_root=ROOT)

    assert len(judge.calls) == 10
    for label, (snapshot, question, reply) in zip(LABELS, judge.calls):
        assert snapshot.source_name == Path(label.data_file).name
        assert snapshot.today == date.fromisoformat(Path(label.data_file).stem.removeprefix("orders_"))
        assert question == QUESTIONS[label.case_id]
        assert reply == label.response


def test_a_judge_that_always_agrees_scores_ten_of_ten_on_the_diagonal():
    result = agreement(judge_labels(LABELS, FakeJudge(), labels_root=ROOT))

    assert (result.exact, result.total) == (10, 10)
    assert result.matrix == {
        "PASS": {"PASS": 3, "FLAG": 0, "FAIL": 0},
        "FLAG": {"PASS": 0, "FLAG": 2, "FAIL": 0},
        "FAIL": {"PASS": 0, "FLAG": 0, "FAIL": 5},
    }
    assert result.per_class == {"PASS": (3, 3), "FLAG": (2, 2), "FAIL": (5, 5)}
    assert result.disagreements == []


def test_disagreements_land_off_the_diagonal_and_keep_both_sides_of_the_argument():
    judge = FakeJudge({"cal-01": "FLAG", "cal-10": "FAIL"})

    result = agreement(judge_labels(LABELS, judge, labels_root=ROOT))

    assert (result.exact, result.total) == (8, 10)
    assert result.matrix == {
        "PASS": {"PASS": 2, "FLAG": 1, "FAIL": 0},
        "FLAG": {"PASS": 0, "FLAG": 1, "FAIL": 1},
        "FAIL": {"PASS": 0, "FLAG": 0, "FAIL": 5},
    }
    assert result.per_class == {"PASS": (2, 3), "FLAG": (1, 2), "FAIL": (5, 5)}
    first = result.disagreements[0]
    assert [d.label.id for d in result.disagreements] == ["cal-01", "cal-10"]
    assert (first.label.human_verdict, first.judge_verdict) == ("PASS", "FLAG")
    assert first.label.human_rationale.startswith("The filter (status is open) is right")
    assert (first.judged.reason, first.judged.evidence) == ("judge says FLAG", ("quote for cal-01",))


def test_a_judge_error_is_recorded_once_and_counts_as_a_disagreement_outside_the_matrix():
    judge = FakeJudge({
        "cal-04": JudgeOutputError("invalid verdict 'MAYBE' (expected PASS, FLAG, or FAIL)"),
        "cal-09": LLMError("Gemini API timed out after 120s"),
    })

    result = agreement(judge_labels(LABELS, judge, labels_root=ROOT))

    assert len(judge.calls) == 10
    assert (result.exact, result.total) == (8, 10)
    assert result.matrix["FAIL"] == {"PASS": 0, "FLAG": 0, "FAIL": 4}
    assert result.matrix["FLAG"] == {"PASS": 0, "FLAG": 1, "FAIL": 0}
    assert result.per_class == {"PASS": (3, 3), "FLAG": (1, 2), "FAIL": (4, 5)}
    assert [(e.label.id, e.judge_verdict, e.error) for e in result.errors] == [
        ("cal-04", "ERROR", "invalid verdict 'MAYBE' (expected PASS, FLAG, or FAIL)"),
        ("cal-09", "ERROR", "Gemini API timed out after 120s"),
    ]
    assert [d.label.id for d in result.disagreements] == ["cal-04", "cal-09"]


def test_an_unexpected_judge_exception_is_recorded_without_losing_other_results():
    judge = FakeJudge({"cal-05": RuntimeError("boom")})

    predictions = judge_labels(LABELS, judge, labels_root=ROOT)

    assert len(judge.calls) == 10
    assert [(p.label.id, p.error) for p in predictions if p.error] == [("cal-05", "RuntimeError: boom")]


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"case_id": "P99"}, "cal-03: unknown case_id 'P99'"),
        ({"human_verdict": "pass"}, "cal-03: invalid human_verdict 'pass'"),
        ({"data_file": "data/orders_2026-11-99.csv"}, "cal-03: cannot load data/orders_2026-11-99.csv"),
    ],
)
def test_bad_labels_are_rejected_before_any_judge_call(change, problem):
    labels = [replace(label, **change) if label.id == "cal-03" else label for label in LABELS]
    judge = FakeJudge()

    with pytest.raises(ValueError, match=re.escape(problem)):
        judge_labels(labels, judge, labels_root=ROOT)

    assert judge.calls == []


def test_pass_versus_not_pass_agreement_treats_flag_and_fail_alike():
    judge = FakeJudge({"cal-01": "FLAG", "cal-10": "FAIL"})

    result = agreement(judge_labels(LABELS, judge, labels_root=ROOT))

    assert result.pass_vs_not_pass == 9


RUN = RunInfo(
    judge_model="gemini-3.8-flash",
    run_at="2026-11-12T18:30:00+00:00",
    rubric_sha256="a" * 64,
    labels_sha256="b" * 64,
)


def test_report_shows_agreement_matrix_per_class_and_every_disagreement_in_full():
    judge = FakeJudge({"cal-01": "FLAG", "cal-04": JudgeOutputError("judge output is not a single JSON object: 'x'")})

    report = render_report(judge_labels(LABELS, judge, labels_root=ROOT), RUN)

    for expected in (
        "Judge model: gemini-3.8-flash",
        "**8 of 10** examples (80%)",
        "PASS versus not-PASS: **8 of 10** examples (80%)",
        "| **PASS** | 2 | 1 | 0 |",
        "| **FLAG** | 0 | 2 | 0 |",
        "| **FAIL** | 0 | 0 | 4 |",
        "Judge errors (outside the matrix): 1",
        "| PASS | 2 of 3 | 67% |",
        "| FLAG | 2 of 2 | 100% |",
        "| FAIL | 4 of 5 | 80% |",
        "### cal-01: P1 on orders_2026-11-10.csv (human PASS, judge FLAG)",
        "**Human rationale:** The filter (status is open) is right",
        "**Judge reason:** judge says FLAG",
        "- quote for cal-01",
        "### cal-04: P8 on orders_2026-11-10.csv (human FAIL, judge ERROR)",
        "**Judge error:** judge output is not a single JSON object: 'x'",
        "> Answer: 7",
    ):
        assert expected in report, expected
    assert "average" not in report.casefold()


def test_model_text_cannot_inject_markdown_structure_into_the_report():
    class InjectingJudge(FakeJudge):
        def __call__(self, snapshot, question, reply):
            verdict = super().__call__(snapshot, question, reply)
            return JudgeVerdict("FLAG", "fine\n## Injected heading", ("ev\n# Injected title",))

    report = render_report(judge_labels(LABELS, InjectingJudge(), labels_root=ROOT), RUN)

    assert "**Judge reason:** fine ## Injected heading" in report
    assert not any(line.startswith(("## Injected", "# Injected")) for line in report.splitlines())


def test_malformed_judge_output_is_kept_in_full_in_the_predictions(tmp_path):
    raw = "Sure! Verdict: PASS because " + "x" * 200
    error = JudgeOutputError("judge output is not a single JSON object: 'Sure!...'")
    error.raw_output = raw

    write_calibration(judge_labels(LABELS, FakeJudge({"cal-02": error}), labels_root=ROOT), RUN, tmp_path)

    saved = json.loads((tmp_path / "predictions.json").read_text(encoding="utf-8"))["predictions"][1]
    assert (saved["judge_verdict"], saved["judge_raw_output"]) == ("ERROR", raw)


def test_a_failing_report_writes_nothing(tmp_path):
    broken = [replace(p, label=replace(p.label, human_verdict="pass"))
              for p in judge_labels(LABELS, FakeJudge(), labels_root=ROOT)]

    with pytest.raises(KeyError):
        write_calibration(broken, RUN, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_main_judges_once_records_provenance_and_refuses_a_second_run(tmp_path, monkeypatch):
    judge = FakeJudge({"cal-10": "FAIL"})
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(calibration, "judge_reply", lambda snapshot, question, reply, complete, model: judge(snapshot, question, reply))
    labels_path = ROOT / "calibration" / "labels.json"

    calibration.main(labels_path=labels_path, out_dir=tmp_path, repo_root=ROOT)

    saved = json.loads((tmp_path / "predictions.json").read_text(encoding="utf-8"))
    assert len(judge.calls) == 10
    assert saved["judge_model"] == "gemini-3.8-flash"
    assert saved["labels_sha256"] == hashlib.sha256(labels_path.read_bytes()).hexdigest()
    assert saved["rubric_sha256"] == hashlib.sha256((ROOT / "deposco_evals" / "judge_rubric.md").read_bytes()).hexdigest()

    with pytest.raises(SystemExit, match="already exists"):
        calibration.main(labels_path=labels_path, out_dir=tmp_path, repo_root=ROOT)
    assert len(judge.calls) == 10


def test_predictions_and_report_are_saved_once_and_never_overwritten(tmp_path):
    predictions = judge_labels(LABELS, FakeJudge({"cal-10": "FAIL"}), labels_root=ROOT)

    write_calibration(predictions, RUN, tmp_path)

    saved = json.loads((tmp_path / "predictions.json").read_text(encoding="utf-8"))
    assert saved["judge_model"] == "gemini-3.8-flash"
    assert saved["labels_sha256"] == "b" * 64
    assert saved["predictions"][9] == {
        "id": "cal-10",
        "case_id": "P10",
        "data_file": "data/orders_2026-11-17.csv",
        "human_verdict": "FLAG",
        "judge_verdict": "FAIL",
        "judge_reason": "judge says FAIL",
        "judge_evidence": ["quote for cal-10"],
        "error": None,
        "judge_raw_output": None,
        "agrees": False,
    }
    assert "**9 of 10** examples (90%)" in (tmp_path / "report.md").read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_calibration(judge_labels(LABELS, FakeJudge(), labels_root=ROOT), RUN, tmp_path)
    assert json.loads((tmp_path / "predictions.json").read_text(encoding="utf-8")) == saved
