import json
from pathlib import Path

from deposco_evals.cases import load_cases
from deposco_evals.judge import VERDICTS

ROOT = Path(__file__).resolve().parent.parent
LABELS = json.loads((ROOT / "calibration" / "labels.json").read_text(encoding="utf-8"))


def test_there_are_ten_uniquely_identified_examples_covering_every_verdict():
    assert len(LABELS) == 10
    assert len({label["id"] for label in LABELS}) == 10
    assert {label["human_verdict"] for label in LABELS} == set(VERDICTS)


def test_every_example_points_at_a_real_case_and_data_file_with_a_rationale():
    case_ids = {case.id for case in load_cases()}

    for label in LABELS:
        assert set(label) == {"id", "case_id", "data_file", "source", "response", "human_verdict", "human_rationale"}
        assert label["case_id"] in case_ids, label["id"]
        assert (ROOT / label["data_file"]).is_file(), label["id"]
        assert label["response"].strip() and label["human_rationale"].strip(), label["id"]
