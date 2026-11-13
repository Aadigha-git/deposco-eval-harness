# Deposco take-home: evals for an orders assistant on changing data

This repository contains three things:
- **A small AI assistant** that answers questions about one warehouse orders CSV. "Today" is the date in the file name.
- **A 15-case golden dataset** whose expected answers are computed in code from each file, so it works on any new snapshot.
- **An eval harness** that grades every reply with deterministic metrics and a Gemini LLM judge, then writes a Markdown and a JSON report.

**Baseline result:** 34 of 45 cases passed over the three snapshots (87%, 67%, and 73%). The failures are real assistant errors, such as off-by-one counts and dropped rows. They're explained in [`reports/failure-analysis.md`](reports/failure-analysis.md).

**Where to look:**
- [`DESIGN.md`](DESIGN.md) (also as a 4-page [`DESIGN.pdf`](DESIGN.pdf)): the architecture, the eight assignment decisions, the metrics, the judge rubric and calibration, the findings, and the limitations
- [`reports/`](reports/): one Markdown and one JSON report per snapshot
- [`calibration/report.md`](calibration/report.md): the judge's agreement with hand labels

## Install and run the tests

You need Python 3.11 or newer; it was developed with 3.14. The harness uses only the standard library, and pytest is the only dev dependency.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

The tests need no API key and no network: the LLM is replaced by a fake transport or a scripted assistant and judge.

## Run the evals

A full run needs a Gemini API key in the environment. Never commit it; `.env` is gitignored.

```bash
set -a; source .env; set +a                                    # loads GEMINI_API_KEY
python -m deposco_evals --data data/orders_2026-11-10.csv      # 15 cases, about 2 minutes
python -m deposco_evals --data data/orders_2026-11-10.csv --expected-only   # expected answers only, no key
```

Reports go to `reports/` (change it with `--out <dir>`). The exit code is 0 for a completed run, whatever the pass rate, and 2 for bad input, a missing key, or a run where every case errored.

The models default to the ones used for the committed reports. Override them with environment variables:

| Variable | Default |
|---|---|
| `ASSISTANT_MODEL` | `gemini-3.5-flash-lite` |
| `JUDGE_MODEL` | `gemini-3.8-flash` |
| `LLM_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` |

## Evaluation console (optional)

There's a Streamlit app with two screens:
- the **evaluation dashboard**, which shows the saved results and makes no API calls
- the **assistant playground**, which asks the live assistant one question and grades it if it's a golden case

```bash
pip install -e '.[dashboard]'
streamlit run dashboard.py     # from the repository root; opens http://127.0.0.1:8501
```
