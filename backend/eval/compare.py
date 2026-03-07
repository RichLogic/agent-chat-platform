"""Baseline diff — compare two eval runs and gate CI on regressions.

Reads two ``report.json`` (or ``summary.json``) files, computes deltas for
pass_rate, latency, and per-category regressions, then exits non-zero when
any configured threshold is breached.

Usage::

    python -m eval.compare \\
        --baseline eval/artifacts-baseline/report.json \\
        --current  eval/artifacts/report.json \\
        --max-pass-rate-drop 0.05 \\
        --max-p90-increase-ms 500
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_summary(path: str) -> dict:
    """Load a summary dict from report.json or summary.json."""
    data = json.loads(Path(path).read_text())
    # report.json wraps summary under a key; summary.json is flat
    if "summary" in data:
        return data["summary"]
    return data


def compare(baseline: dict, current: dict) -> dict:
    """Compare two summary dicts and return a structured diff."""
    b_rate = baseline.get("pass_rate", 0)
    c_rate = current.get("pass_rate", 0)
    rate_delta = c_rate - b_rate

    b_lat = baseline.get("latency", {})
    c_lat = current.get("latency", {})

    def _lat_delta(key: str) -> float | None:
        b_val = b_lat.get(key)
        c_val = c_lat.get(key)
        if b_val is not None and c_val is not None:
            return round(c_val - b_val, 1)
        return None

    # Per-category regression
    b_cats = baseline.get("by_category", {})
    c_cats = current.get("by_category", {})
    cat_regressions: list[dict] = []
    for cat in sorted(set(b_cats) | set(c_cats)):
        b_cat = b_cats.get(cat, {"total": 0, "passed": 0})
        c_cat = c_cats.get(cat, {"total": 0, "passed": 0})
        b_cat_rate = b_cat["passed"] / b_cat["total"] if b_cat["total"] else 0
        c_cat_rate = c_cat["passed"] / c_cat["total"] if c_cat["total"] else 0
        delta = c_cat_rate - b_cat_rate
        if delta < 0:
            cat_regressions.append({
                "category": cat,
                "baseline_rate": b_cat_rate,
                "current_rate": c_cat_rate,
                "delta": round(delta, 4),
            })

    return {
        "pass_rate": {
            "baseline": b_rate,
            "current": c_rate,
            "delta": round(rate_delta, 4),
        },
        "latency": {
            "total_ms_p50_delta": _lat_delta("total_ms_p50"),
            "total_ms_p90_delta": _lat_delta("total_ms_p90"),
            "ttft_ms_p50_delta": _lat_delta("ttft_ms_p50"),
            "ttft_ms_p90_delta": _lat_delta("ttft_ms_p90"),
        },
        "category_regressions": cat_regressions,
        "totals": {
            "baseline": baseline.get("total", 0),
            "current": current.get("total", 0),
        },
    }


def check_thresholds(
    diff: dict,
    *,
    max_pass_rate_drop: float = 0.05,
    max_p90_increase_ms: float | None = None,
) -> list[str]:
    """Return a list of threshold-violation messages (empty = all OK)."""
    violations: list[str] = []

    rate_delta = diff["pass_rate"]["delta"]
    if rate_delta < -max_pass_rate_drop:
        violations.append(
            f"pass_rate dropped by {abs(rate_delta):.2%} "
            f"(threshold: {max_pass_rate_drop:.2%})"
        )

    if max_p90_increase_ms is not None:
        p90_delta = diff["latency"].get("total_ms_p90_delta")
        if p90_delta is not None and p90_delta > max_p90_increase_ms:
            violations.append(
                f"total_ms_p90 increased by {p90_delta:.0f} ms "
                f"(threshold: {max_p90_increase_ms:.0f} ms)"
            )

    return violations


def print_diff(diff: dict, violations: list[str]) -> None:
    """Pretty-print the comparison result."""
    pr = diff["pass_rate"]
    sign = "+" if pr["delta"] >= 0 else ""
    print(f"Pass Rate : {pr['baseline']:.1%} → {pr['current']:.1%}  ({sign}{pr['delta']:.2%})")

    lat = diff["latency"]
    for key in ("total_ms_p50_delta", "total_ms_p90_delta", "ttft_ms_p50_delta", "ttft_ms_p90_delta"):
        val = lat.get(key)
        if val is not None:
            label = key.replace("_delta", "").replace("_", " ")
            s = "+" if val >= 0 else ""
            print(f"  {label}: {s}{val:.0f} ms")

    regs = diff["category_regressions"]
    if regs:
        print(f"\nCategory regressions ({len(regs)}):")
        for r in regs:
            print(f"  {r['category']}: {r['baseline_rate']:.0%} → {r['current_rate']:.0%}")

    if violations:
        print(f"\nTHRESHOLD VIOLATIONS ({len(violations)}):")
        for v in violations:
            print(f"  - {v}")
    else:
        print("\nAll thresholds passed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two eval runs")
    parser.add_argument("--baseline", required=True, help="Path to baseline report.json or summary.json")
    parser.add_argument("--current", required=True, help="Path to current report.json or summary.json")
    parser.add_argument("--max-pass-rate-drop", type=float, default=0.05,
                        help="Max allowed pass-rate drop (default: 0.05 = 5%%)")
    parser.add_argument("--max-p90-increase-ms", type=float, default=None,
                        help="Max allowed P90 latency increase in ms")
    parser.add_argument("--output", default=None, help="Write diff JSON to this path")
    args = parser.parse_args()

    baseline = load_summary(args.baseline)
    current = load_summary(args.current)
    diff = compare(baseline, current)
    violations = check_thresholds(
        diff,
        max_pass_rate_drop=args.max_pass_rate_drop,
        max_p90_increase_ms=args.max_p90_increase_ms,
    )

    print_diff(diff, violations)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump({"diff": diff, "violations": violations}, f, indent=2)

    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
