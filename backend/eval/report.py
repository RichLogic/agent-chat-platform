"""Eval report generation — Markdown + JSON output."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def generate_report(results: list[dict], output_dir: str) -> dict:
    """Generate a report from eval results. Returns summary dict."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    failed = total - passed
    pass_rate = passed / total if total > 0 else 0

    # Category breakdown
    by_category: dict[str, dict] = defaultdict(lambda: {"total": 0, "passed": 0})
    for r in results:
        cat = r.get("category", "unknown")
        by_category[cat]["total"] += 1
        if r.get("passed"):
            by_category[cat]["passed"] += 1

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "by_category": dict(by_category),
    }

    # Write JSON report
    json_path = output_path / "report.json"
    with open(json_path, "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2, ensure_ascii=False)

    # Write Markdown report
    md_path = output_path / "report.md"
    with open(md_path, "w") as f:
        f.write(f"# Eval Report\n\n")
        f.write(f"**Date**: {summary['timestamp']}\n\n")
        f.write(f"## Summary\n\n")
        f.write(f"| Metric | Value |\n|---|---|\n")
        f.write(f"| Total | {total} |\n")
        f.write(f"| Passed | {passed} |\n")
        f.write(f"| Failed | {failed} |\n")
        f.write(f"| Pass Rate | {pass_rate:.1%} |\n\n")

        f.write(f"## By Category\n\n")
        f.write(f"| Category | Total | Passed | Rate |\n|---|---|---|---|\n")
        for cat, stats in sorted(by_category.items()):
            cat_rate = stats["passed"] / stats["total"] if stats["total"] > 0 else 0
            f.write(f"| {cat} | {stats['total']} | {stats['passed']} | {cat_rate:.0%} |\n")

        f.write(f"\n## Failures\n\n")
        for r in results:
            if not r.get("passed"):
                f.write(f"### {r['id']}\n")
                f.write(f"- **Input**: {r.get('input', 'N/A')}\n")
                f.write(f"- **Failures**: {', '.join(r.get('failures', []))}\n\n")

    return summary
