# Deposco take-home: evals for an orders assistant on changing data

This repository contains three things:
- **A small AI assistant** that answers questions about one warehouse orders CSV. "Today" is the date in the file name.
- **A 15-case golden dataset** whose expected answers are computed in code from each file.
- **An eval harness** that grades every reply with deterministic metrics and a Gemini LLM judge, then writes a Markdown and a JSON report.

The design and the eight assignment decisions are in [`DESIGN.md`](DESIGN.md).

## Requirements

- Python 3.11 or newer. It was developed and tested with Python 3.14.
- No runtime dependencies. The LLM client uses only the standard library, and `pytest` is the only dev dependency.
- A Gemini API key for full runs. `--expected-only` and the tests need no key and no network.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

The install needs network access to PyPI, for pytest and the build backend.

## Run the tests

```bash
pytest -q
```

The suite runs offline. The LLM is replaced at the HTTP boundary by a fake transport, or by a scripted assistant and judge.

## Gemini configuration

The harness calls the Gemini API's OpenAI-compatible Chat Completions endpoint. Configuration comes only from environment variables:

| Variable | Required | Default |
|---|---|---|
| `GEMINI_API_KEY` | yes, for full runs | none |
| `LLM_BASE_URL` | no | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| `ASSISTANT_MODEL` | no | `gemini-3.5-flash-lite` |
| `JUDGE_MODEL` | no | `gemini-3.8-flash` |

The committed reports were produced with exactly these default model IDs. Never commit the key. `.env` is gitignored, and the CLI reads only the process environment. To load a local `.env` file:

```bash
set -a; source .env; set +a
```

## Run the evals (one command per data file)

```bash
python -m deposco_evals --data data/orders_2026-11-10.csv
```

The command runs all 15 cases (30 Gemini calls, about 2 minutes) and writes two reports of the same run:
- `reports/orders_2026-11-10.md`, a readable report
- `reports/orders_2026-11-10.json`, the same data in structured form

Both reports contain:
- the models, the reference date, and the evaluation definitions
- the PASS, FLAG, FAIL, and ERROR counts by metric, by category, and overall, with pass rates
- per case: the question, the expected answer and its evidence, the reply, every metric's verdict, score, threshold, and reason, the judge's reason and evidence, and the case verdict

Options:
- `--out <dir>` changes the report folder.
- `--expected-only` prints the expected answers only, with no API calls.

Exit codes:
- **0** means the run completed, whatever the pass rate.
- **2** means bad input, a missing key, reports that can't be written, or a run where every case ended in ERROR. In that last case the previous reports are kept.

Committed results:
- `reports/` holds the three baseline runs (a Markdown and a JSON report for each), plus `reports/failure-analysis.md`.
- `calibration/` holds the judge calibration labels, predictions, report, and analysis. Calibration is a separate, run-once command: `python -m deposco_evals.calibration`. It refuses to overwrite existing results.

## A fourth CSV

The file must use the same schema and be named `orders_YYYY-MM-DD.csv`; that date becomes "today". No code changes are needed.

```bash
python -m deposco_evals --data path/to/orders_2026-11-24.csv --expected-only   # inspect ground truth (seconds, no key)
python scripts/crosscheck_expected.py path/to/orders_2026-11-24.csv           # independent re-computation to compare
python -m deposco_evals --data path/to/orders_2026-11-24.csv                  # full run, reports in reports/
```

Copying the file into `data/` also makes `pytest` compare the ground truth with the independent cross-check for it automatically.

A file with an unsupported header, status, carrier, date, or unit value is rejected with exit code 2 and an error naming the line, rather than being graded wrongly.

## Results dashboard (optional)

The dashboard is a read-only Streamlit view of the saved `reports/orders_*.json` files and the `calibration/` results. It shows:
- the PASS, FLAG, FAIL, and ERROR counts
- the snapshot comparison
- metric and category pass rates
- a case explorer
- the answer-versus-reasoning split (P1, P10, P12)
- judge calibration agreement, with its limitations

It makes no API calls and writes no files.

```bash
pip install -e '.[dashboard]'      # adds Streamlit; the harness itself stays dependency-free
streamlit run dashboard.py         # from the repository root; opens http://localhost:8501
```

Run it from the repository root so the theme in `.streamlit/config.toml` applies. It shows whatever reports are in `reports/`, so a new `python -m deposco_evals` run appears after a page refresh. Its tests run with `pytest`; the app smoke test is skipped when Streamlit isn't installed.
