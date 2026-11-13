# Spec: read-only results dashboard

Status: ready-for-agent

## Problem Statement

The eval results live in three JSON reports, three Markdown reports, and the calibration files. That's fine for audit but slow to present: a reviewer can't see at a glance how the snapshots compare, which cases failed where, or why a case failed. In particular, the difference between a wrong answer and unsupported reasoning is spread across several metrics.

## Solution

A local, read-only Streamlit page that reads the existing `reports/orders_*.json` files and `calibration/` results and shows:
- the overall PASS / FLAG / FAIL / ERROR counts
- a snapshot comparison
- metric pass rates and a category breakdown
- a case explorer
- an answer-versus-reasoning view
- calibration agreement, with its independence limitation

It computes nothing new about the assistant. Every number on the page is read from, or summed from, the saved reports.

## User Stories

1. As a reviewer, I want overall PASS, FLAG, FAIL, and ERROR counts across all snapshots, so that I see the headline result first.
2. As a reviewer, I want each snapshot side by side with its counts and pass rate, so that I can compare the three files.
3. As a reviewer, I want a case-by-snapshot verdict grid, so that I see which cases failed on which file.
4. As a reviewer, I want pass rates per metric and per category, so that I know where the assistant is weak.
5. As a reviewer, I want to filter cases by snapshot, case, and verdict, so that I can find specific results.
6. As a reviewer, I want each case's question, expected answer and evidence, response, metric verdicts and reasons, and the judge's reason and evidence, so that every verdict is explainable.
7. As a reviewer, I want each case's answer verdict and reasoning verdict side by side with a plain label for how they relate, so that a wrong answer with grounded reasoning (P1), a right answer with unsupported reasoning (P10), and a refusal-format failure (P12) are visible.
8. As a reviewer, I want calibration agreement with its limitation stated next to it, so that the judge's reliability isn't overstated.
9. As a presenter, I want one launch command and a page that works offline from the saved files, so that I can show it in the interview.
10. As a maintainer, I want the dashboard to never write files or call an API, so that it can't change the results.

## Implementation Decisions

- **Data module** (`deposco_evals.dashboard_data`): pure Python with only the standard library, and no Streamlit import.
  - `load_reports(directory)` reads `orders_*.json`, sorted by reference date. It rejects a missing directory, no reports, or a report missing required fields with a clear error.
  - `overall_totals`, `snapshot_rows`, `metric_rows`, `category_rows`, `verdict_grid`, and `case_records` aggregate the saved `summary` and `cases` fields. They count the stored values and never re-grade.
  - `relation(answer_verdict, reasoning_verdict)` returns a plain label for how the two verdicts relate. A refusal FAIL with Answer `NOT IN DATA` and a judge PASS is labelled as a refusal-format failure with compliant behaviour. The saved reasons predate the reason-wording correction.
  - `calibration_summary(directory)` reads `predictions.json` and the completed `human-review.md`. It returns the agreement counts and the human-versus-judge confusion matrix.
- **App** (`dashboard.py` at the repo root): a single Streamlit script using native components, which are `st.metric`, `st.tabs`, `st.dataframe` with `column_config`, filters, and expanders. Theming is in `.streamlit/config.toml`, with a little CSS only for the status badges.
- **Dependencies:** Streamlit is an optional extra, installed with `pip install -e '.[dashboard]'`. The harness keeps no runtime dependencies.
- **Launch:** `streamlit run dashboard.py`.

## Testing Decisions

- **Seam 1, the data module:** tested against the real committed reports, with literal expected numbers. Examples are 34 / 0 / 11 / 0 overall, 32 of 39 for `answer_correct`, the P1, P10, and P12 relations, and 10/10 calibration. It's also tested against small temporary report directories for the error paths.
- **Seam 2, the app:** a headless Streamlit `AppTest` smoke test checks that the page renders without exceptions and shows the headline counts. It's skipped when Streamlit isn't installed, so the core suite still runs with only pytest.
- **No LLM, network, or writes** in either seam.

## Out of Scope

- deployment, authentication, a database, an API, or any new Gemini calls
- editing or re-running evaluations
- decorative charts and frontend build tooling

## Further Notes

**Palette** (Deposco's media kit and deposco.com):
- Deposco Orange `#F48020`, the official swatch, used as an accent only and never as text on white
- site blue `#4797D8`
- navy `#24323D` for text
- surfaces `#F3F7F9`, `#E2ECF4`, and `#D9E4ED`
- Deposco Dark Gray `#444444`

Status colours always come with the status word, so meaning never relies on colour alone.

## Revision: two-screen evaluation console

The app has two screens, linked from a navy sidebar with native Streamlit navigation:

- **Evaluation dashboard:** the same saved-data views, restyled with:
  - a hero that shows the headline and the proportional verdict split
  - snapshot cards
  - tabs for the case grid, metrics and categories, answer versus reasoning, the case explorer, and calibration
- **Assistant playground:** pick a CSV from `data/` and a golden case, or type your own question, then run the existing assistant live.
  - `deposco_evals.playground` matches a typed question to a golden case, ignoring case and spacing.
  - It runs `assistant.ask` through the existing client, parses the `Answer:` line, and for golden cases grades the reply with the existing `answer_correct` and `refusal_correct`. The judge isn't called.
  - Live output is labelled "Live run, not saved" and is kept only in the session, shown beside the committed baseline verdict for the same case and snapshot.
  - With no key, the page says how to set one and disables the run.
  - API and snapshot errors show as an error message.

**Tests:**
- `ask_live` and `matching_case` are tested with a scripted LLM.
- The page tests cover both screens, using `AppTest` with the fake client patched in at `make_complete`: no key, a golden case, a custom question, and an API failure.

The evaluation engine, golden cases, rubric, metrics, and baseline reports are unchanged.
