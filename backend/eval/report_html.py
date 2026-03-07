"""HTML report generator — aggregates eval results into a single report.html."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def generate_html_report(results: list[dict], output_dir: str) -> dict:
    """Generate report.html + report.json from scored results. Returns summary dict."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    failed = total - passed
    pass_rate = passed / total if total else 0

    # Category breakdown
    by_cat: dict[str, dict] = defaultdict(lambda: {"total": 0, "passed": 0})
    for r in results:
        cat = r.get("category", "unknown")
        by_cat[cat]["total"] += 1
        if r.get("passed"):
            by_cat[cat]["passed"] += 1

    # Latency stats
    times = [r["total_ms"] for r in results if r.get("total_ms") is not None]
    ttfts = [r["ttft_ms"] for r in results if r.get("ttft_ms") is not None]
    latency = {
        "total_ms_p50": _percentile(times, 50),
        "total_ms_p90": _percentile(times, 90),
        "total_ms_max": max(times) if times else None,
        "ttft_ms_p50": _percentile(ttfts, 50),
        "ttft_ms_p90": _percentile(ttfts, 90),
    }

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "by_category": dict(by_cat),
        "latency": latency,
    }

    # Write JSON
    with open(out / "report.json", "w") as f:
        json.dump({"summary": summary, "results": results}, f, indent=2, ensure_ascii=False,
                  default=str)

    # Write HTML
    html = _render_html(summary, results, dict(by_cat))
    with open(out / "report.html", "w") as f:
        f.write(html)

    return summary


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _percentile(data: list[float], pct: int) -> float | None:
    if not data:
        return None
    s = sorted(data)
    idx = int(len(s) * pct / 100)
    idx = min(idx, len(s) - 1)
    return round(s[idx], 1)


def _render_html(summary: dict, results: list[dict], by_cat: dict) -> str:
    ts = summary["timestamp"]
    total = summary["total"]
    passed = summary["passed"]
    failed = summary["failed"]
    rate = summary["pass_rate"]
    lat = summary["latency"]

    # Category rows
    cat_rows = ""
    for cat in sorted(by_cat):
        s = by_cat[cat]
        cr = s["passed"] / s["total"] if s["total"] else 0
        color = "#16a34a" if cr == 1 else "#dc2626" if cr == 0 else "#ca8a04"
        cat_rows += (
            f'<tr><td>{_esc(cat)}</td><td>{s["total"]}</td>'
            f'<td>{s["passed"]}</td>'
            f'<td style="color:{color};font-weight:600">{cr:.0%}</td></tr>\n'
        )

    # Failure rows
    fail_rows = ""
    for r in results:
        if r.get("passed"):
            continue
        reasons = r.get("reasons") or r.get("failures") or []
        reasons_html = "<br>".join(_esc(x) for x in reasons)
        events_link = f'{_esc(r["id"])}/events.jsonl'
        fail_rows += (
            f'<tr><td><a href="{events_link}">{_esc(r["id"])}</a></td>'
            f'<td>{_esc(r.get("category", ""))}</td>'
            f'<td>{_esc(r.get("input", ""))}</td>'
            f'<td>{reasons_html}</td>'
            f'<td>{r.get("total_ms", "—")}</td></tr>\n'
        )

    # All results rows
    all_rows = ""
    for r in results:
        status = "PASS" if r.get("passed") else "FAIL"
        cls = "pass" if r.get("passed") else "fail"
        events_link = f'{_esc(r["id"])}/events.jsonl'
        all_rows += (
            f'<tr class="{cls}"><td><a href="{events_link}">{_esc(r["id"])}</a></td>'
            f'<td>{_esc(r.get("category", ""))}</td>'
            f'<td>{status}</td>'
            f'<td>{r.get("total_ms", "—")}</td>'
            f'<td>{r.get("ttft_ms", "—")}</td></tr>\n'
        )

    def _fmt(v: float | None) -> str:
        return f"{v:.0f}" if v is not None else "—"

    bar_pct = int(rate * 100)
    bar_color = "#16a34a" if rate >= 0.8 else "#ca8a04" if rate >= 0.5 else "#dc2626"

    return f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Eval Report — {ts[:10]}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:#f8fafc; color:#1e293b; padding:2rem; }}
  h1 {{ font-size:1.5rem; margin-bottom:.25rem; }}
  .meta {{ color:#64748b; margin-bottom:1.5rem; font-size:.875rem; }}
  .cards {{ display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:1.5rem; }}
  .card {{ background:#fff; border:1px solid #e2e8f0; border-radius:.5rem;
           padding:1rem 1.25rem; min-width:140px; }}
  .card .label {{ font-size:.75rem; color:#64748b; text-transform:uppercase; }}
  .card .value {{ font-size:1.5rem; font-weight:700; margin-top:.25rem; }}
  .bar-bg {{ background:#e2e8f0; border-radius:4px; height:8px; width:200px; margin-top:.5rem; }}
  .bar-fg {{ height:8px; border-radius:4px; }}
  table {{ width:100%; border-collapse:collapse; margin-bottom:2rem; background:#fff;
           border:1px solid #e2e8f0; border-radius:.5rem; overflow:hidden; }}
  th {{ background:#f1f5f9; text-align:left; padding:.5rem .75rem; font-size:.75rem;
       text-transform:uppercase; color:#64748b; }}
  td {{ padding:.5rem .75rem; border-top:1px solid #f1f5f9; font-size:.875rem; }}
  tr.fail td {{ background:#fef2f2; }}
  a {{ color:#2563eb; text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  h2 {{ font-size:1.125rem; margin:1.5rem 0 .75rem; }}
</style>
</head>
<body>
<h1>Eval Report</h1>
<p class="meta">{ts}</p>

<div class="cards">
  <div class="card">
    <div class="label">Total</div>
    <div class="value">{total}</div>
  </div>
  <div class="card">
    <div class="label">Passed</div>
    <div class="value" style="color:#16a34a">{passed}</div>
  </div>
  <div class="card">
    <div class="label">Failed</div>
    <div class="value" style="color:#dc2626">{failed}</div>
  </div>
  <div class="card">
    <div class="label">Pass Rate</div>
    <div class="value">{rate:.1%}</div>
    <div class="bar-bg"><div class="bar-fg" style="width:{bar_pct}%;background:{bar_color}"></div></div>
  </div>
  <div class="card">
    <div class="label">Latency P50 / P90</div>
    <div class="value" style="font-size:1rem">{_fmt(lat["total_ms_p50"])} / {_fmt(lat["total_ms_p90"])} ms</div>
  </div>
  <div class="card">
    <div class="label">TTFT P50 / P90</div>
    <div class="value" style="font-size:1rem">{_fmt(lat["ttft_ms_p50"])} / {_fmt(lat["ttft_ms_p90"])} ms</div>
  </div>
</div>

<h2>By Category</h2>
<table>
<tr><th>Category</th><th>Total</th><th>Passed</th><th>Rate</th></tr>
{cat_rows}</table>

<h2>Failures</h2>
{"<p style='color:#64748b'>None — all cases passed.</p>" if not fail_rows else ""}
<table style="{'display:none' if not fail_rows else ''}">
<tr><th>Case</th><th>Category</th><th>Input</th><th>Reasons</th><th>Time (ms)</th></tr>
{fail_rows}</table>

<h2>All Results</h2>
<table>
<tr><th>Case</th><th>Category</th><th>Status</th><th>Total (ms)</th><th>TTFT (ms)</th></tr>
{all_rows}</table>

</body>
</html>"""


def _esc(s: str) -> str:
    """Minimal HTML escaping."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
