"""python -m deposco_evals --data <csv> [--out DIR] [--expected-only]"""

import argparse
import os
import sys
from pathlib import Path

from deposco_evals.cases import load_cases
from deposco_evals.llm import LLMError, config_from_env, make_complete
from deposco_evals.report import percent, render_expected, render_json, render_markdown
from deposco_evals.run import CASE_VERDICTS, pass_rate, run_evals, summarize
from deposco_evals.snapshot import load_snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m deposco_evals", description="Run the orders-assistant evals on one data file.")
    parser.add_argument("--data", required=True, type=Path, help="orders CSV named orders_YYYY-MM-DD.csv")
    parser.add_argument("--out", default=Path("reports"), type=Path, help="report directory (default: reports)")
    parser.add_argument("--expected-only", action="store_true", help="print expected answers; no LLM calls, no API key")
    args = parser.parse_args(argv)

    try:
        snapshot = load_snapshot(args.data)
        cases = load_cases()
        if args.expected_only:
            print(render_expected(snapshot, cases))
            return 0
        config = config_from_env()
        run = run_evals(snapshot, cases, make_complete(config), config.assistant_model, config.judge_model)
    except (ValueError, OSError, LLMError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    errors = [result for result in run.cases if result.verdict == "ERROR"]
    if len(errors) == len(run.cases):
        print(f"error: every case ended in ERROR, so no reports were written; first error: {errors[0].error}",
              file=sys.stderr)
        return 2

    paths = {args.out / f"{args.data.stem}.md": render_markdown(run), args.out / f"{args.data.stem}.json": render_json(run)}
    try:
        _write_together(paths)
    except OSError as error:
        print(f"error: cannot write reports to {args.out}: {error}", file=sys.stderr)
        return 2

    overall = summarize(run).overall
    counts = ", ".join(f"{verdict} {overall[verdict]}" for verdict in CASE_VERDICTS)
    print(f"{run.data_file} (today {run.reference_date}): {overall['total']} cases: {counts}; "
          f"pass rate {percent(pass_rate(overall))}")
    print(f"wrote {' and '.join(map(str, paths))}")
    if errors:
        print(f"warning: {len(errors)} case(s) ended in ERROR and were not graded; see the report", file=sys.stderr)
    return 0


def _write_together(paths: dict[Path, str]) -> None:
    """Writes every report to a temporary file first, so a failure never leaves a mismatched pair."""
    next(iter(paths)).parent.mkdir(parents=True, exist_ok=True)
    temporary = {path: path.with_name(path.name + ".tmp") for path in paths}
    try:
        for path, text in paths.items():
            temporary[path].write_text(text, encoding="utf-8")
        for path in paths:
            os.replace(temporary[path], path)
    finally:
        for path in temporary.values():
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
