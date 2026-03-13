"""Unified regression runner for interview-oriented reliability checks."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from eval.compare import check_thresholds, compare, load_summary
from eval.live_runner import run_all_live
from eval.smoke_runner import run_smoke


def _load_results(artifacts_dir: str) -> list[dict]:
    report_path = Path(artifacts_dir) / "report.json"
    if not report_path.exists():
        return []
    with open(report_path) as f:
        payload = json.load(f)
    return payload.get("results", [])


def _print_case_table(results: list[dict]) -> None:
    print("\nCase Results:")
    for r in results:
        status = "PASS" if r.get("passed") else "FAIL"
        ms = r.get("total_ms", "-")
        reason = (r.get("fail_reason") or "").strip()
        trace = r.get("key_trace_signals") or {}
        print(f"  - {r.get('id')}: {status} | {ms} ms | reason={reason or '-'} | trace={trace}")


async def _run(args: argparse.Namespace) -> int:
    if args.mode == "live":
        summary = await run_all_live(
            args.cases,
            base_url=args.base_url,
            auth_token=args.token,
            case_file=args.case_file,
            artifacts_dir=args.artifacts,
            agent_mode=args.agent_mode,
            concurrency=args.concurrency,
        )
    else:
        summary = await run_smoke(
            cases_dir=args.cases,
            case_file=args.case_file,
            artifacts_dir=args.artifacts,
        )

    results = _load_results(args.artifacts)
    _print_case_table(results)

    out = {"summary": summary, "results": results}
    Path(args.artifacts).mkdir(parents=True, exist_ok=True)
    with open(Path(args.artifacts) / "regression_summary.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    if args.baseline:
        baseline = load_summary(args.baseline)
        current = load_summary(str(Path(args.artifacts) / "report.json"))
        diff = compare(baseline, current)
        violations = check_thresholds(
            diff,
            max_pass_rate_drop=args.max_pass_rate_drop,
            max_p90_increase_ms=args.max_p90_increase_ms,
        )
        with open(Path(args.artifacts) / "regression_diff.json", "w") as f:
            json.dump({"diff": diff, "violations": violations}, f, indent=2, ensure_ascii=False)
        print("\nBaseline Diff:")
        print(json.dumps(diff, indent=2, ensure_ascii=False))
        if violations:
            print("\nThreshold violations:")
            for v in violations:
                print(f"  - {v}")
            return 1

    return 0 if summary.get("pass_rate", 0) >= args.min_pass_rate else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Unified regression runner")
    parser.add_argument("--mode", choices=["smoke", "live"], default="smoke")
    parser.add_argument("--cases", default="eval/cases")
    parser.add_argument("--case-file", default="interview_reliability.yaml")
    parser.add_argument("--artifacts", default="eval/artifacts-interview")
    parser.add_argument("--min-pass-rate", type=float, default=0.8)

    parser.add_argument("--base-url", default="http://localhost:8301")
    parser.add_argument("--token", default="")
    parser.add_argument("--agent-mode", action="store_true")
    parser.add_argument("--concurrency", type=int, default=4)

    parser.add_argument("--baseline", default="")
    parser.add_argument("--max-pass-rate-drop", type=float, default=0.05)
    parser.add_argument("--max-p90-increase-ms", type=float, default=None)

    args = parser.parse_args()
    code = asyncio.run(_run(args))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
