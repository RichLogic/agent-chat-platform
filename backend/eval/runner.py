"""Eval runner — loads YAML cases, runs through chat service, collects results."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import yaml

from eval.judge import judge_result
from eval.report import generate_report


def load_cases(cases_dir: str) -> list[dict]:
    """Load all YAML test case files from a directory."""
    cases = []
    for path in sorted(Path(cases_dir).glob("*.yaml")):
        with open(path) as f:
            docs = yaml.safe_load(f)
            if isinstance(docs, list):
                for case in docs:
                    case.setdefault("source_file", path.name)
                    cases.append(case)
    return cases


async def run_case(case: dict) -> dict:
    """Run a single eval case and return the result dict.

    This is a lightweight simulation — it evaluates assertions against
    expected tool calls and response patterns without a live LLM.
    """
    result = {
        "id": case["id"],
        "category": case.get("category", "unknown"),
        "input": case["input"],
        "expected_tool": case.get("expected_tool"),
        "assertions": case.get("assertions", []),
        "simulated": True,
    }

    # In a full integration run, we would call handle_chat_stream here.
    # For now, we mark the case as needing live evaluation.
    result["needs_live_eval"] = True
    return result


async def run_all(cases_dir: str, output_dir: str) -> dict:
    """Run all cases and produce a report."""
    cases = load_cases(cases_dir)
    if not cases:
        print(f"No cases found in {cases_dir}", file=sys.stderr)
        return {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0}

    results = []
    for case in cases:
        result = await run_case(case)
        judgment = judge_result(case, result)
        results.append({**result, **judgment})

    summary = generate_report(results, output_dir)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run eval cases")
    parser.add_argument("--cases", default="eval/cases", help="Directory with YAML case files")
    parser.add_argument("--output", default="eval/reports", help="Output directory for reports")
    args = parser.parse_args()

    summary = asyncio.run(run_all(args.cases, args.output))
    print(f"\nTotal: {summary['total']}, Passed: {summary['passed']}, "
          f"Failed: {summary['failed']}, Pass Rate: {summary['pass_rate']:.1%}")

    sys.exit(0 if summary["pass_rate"] >= 0.8 else 1)


if __name__ == "__main__":
    main()
