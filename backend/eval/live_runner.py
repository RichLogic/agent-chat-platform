"""Live eval runner — hits a real (or test) server via SSE and collects artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
import yaml

from eval.report_html import generate_html_report
from eval.scorers.rule_scorer import score as rule_score


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


# ---------------------------------------------------------------------------
# SSE parsing
# ---------------------------------------------------------------------------

def parse_sse_line(line: str) -> dict | None:
    """Parse a single SSE data line into a dict, or return None."""
    line = line.strip()
    if line.startswith("data: "):
        try:
            return json.loads(line[6:])
        except json.JSONDecodeError:
            return None
    return None


def extract_result_from_events(events: list[dict]) -> dict:
    """Derive final_answer, tool_calls, ttft_ms, total_ms, error from raw SSE events."""
    text_parts: list[str] = []
    tool_calls: list[dict] = []
    first_text_ts: float | None = None
    run_start_ts: float | None = None
    run_finish_ts: float | None = None
    token_usage: dict | None = None
    error: str | None = None

    for ev in events:
        ev_type = ev.get("type", "")

        if ev_type == "run.start":
            run_start_ts = _ts_ms(ev)

        elif ev_type == "text.delta":
            if first_text_ts is None:
                first_text_ts = _ts_ms(ev)
            text_parts.append(ev.get("data", {}).get("content", ""))

        elif ev_type == "tool.call":
            data = ev.get("data", {})
            tool_calls.append({
                "tool_name": data.get("tool_name"),
                "arguments": data.get("arguments"),
            })

        elif ev_type == "run.finish":
            run_finish_ts = _ts_ms(ev)
            token_usage = ev.get("data", {}).get("token_usage")

        elif ev_type == "error":
            error = ev.get("data", {}).get("message", "unknown error")

    final_answer = "".join(text_parts)

    ttft_ms: float | None = None
    if run_start_ts is not None and first_text_ts is not None:
        ttft_ms = round(first_text_ts - run_start_ts, 1)

    total_ms: float | None = None
    if run_start_ts is not None and run_finish_ts is not None:
        total_ms = round(run_finish_ts - run_start_ts, 1)

    result: dict = {
        "response": final_answer,
        "tool_calls": tool_calls,
        "ttft_ms": ttft_ms,
        "total_ms": total_ms,
        "token_usage": token_usage,
    }
    if error:
        result["error"] = error

    return result


def _ts_ms(ev: dict) -> float:
    """Extract a millisecond-precision wall-clock timestamp from an event.

    Tries the ``ts`` field first (ISO string → epoch ms).  Falls back to 0.
    """
    ts_raw = ev.get("ts")
    if ts_raw is None:
        return 0.0
    if isinstance(ts_raw, (int, float)):
        return float(ts_raw)
    # ISO string
    from datetime import datetime, timezone

    try:
        dt = datetime.fromisoformat(str(ts_raw))
        return dt.timestamp() * 1000
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Single-case live runner
# ---------------------------------------------------------------------------

async def run_case_live(
    case: dict,
    *,
    base_url: str,
    auth_token: str,
    agent_mode: bool,
    artifacts_dir: Path,
    http_client: httpx.AsyncClient,
) -> dict:
    """Run one eval case against a live server and return result dict."""
    case_id = case["id"]
    case_artifacts = artifacts_dir / case_id
    case_artifacts.mkdir(parents=True, exist_ok=True)

    headers = {"Authorization": f"Bearer {auth_token}"}

    # 1. Create a conversation
    resp = await http_client.post(f"{base_url}/api/conversations", headers=headers)
    resp.raise_for_status()
    conversation_id = resp.json()["id"]

    # 2. Stream chat via SSE
    events: list[dict] = []
    wall_start = time.monotonic()

    async with http_client.stream(
        "POST",
        f"{base_url}/api/chat",
        json={
            "conversation_id": conversation_id,
            "content": case["input"],
            "agent_mode": agent_mode,
        },
        headers={**headers, "Accept": "text/event-stream"},
        timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10),
    ) as sse_resp:
        sse_resp.raise_for_status()
        buffer = ""
        async for chunk in sse_resp.aiter_text():
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                ev = parse_sse_line(line)
                if ev is not None:
                    events.append(ev)
        # flush remaining
        if buffer.strip():
            ev = parse_sse_line(buffer)
            if ev is not None:
                events.append(ev)

    wall_ms = round((time.monotonic() - wall_start) * 1000, 1)

    # 3. Write events.jsonl artifact
    jsonl_path = case_artifacts / "events.jsonl"
    with open(jsonl_path, "w") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")

    # 4. Extract structured result
    extracted = extract_result_from_events(events)

    # Build result dict (compatible with judge)
    result: dict = {
        "id": case_id,
        "category": case.get("category", "unknown"),
        "input": case["input"],
        "expected_tool": case.get("expected_tool"),
        "assertions": case.get("assertions", []),
        "response": extracted["response"],
        "tool_calls": extracted["tool_calls"],
        "ttft_ms": extracted["ttft_ms"],
        "total_ms": extracted.get("total_ms") or wall_ms,
        "token_usage": extracted["token_usage"],
        "simulated": False,
    }
    if "error" in extracted:
        result["error"] = extracted["error"]

    # Score (rule_scorer includes classic assertions + extended rules)
    scoring = rule_score(case, result)
    result["passed"] = scoring["passed"]
    result["failures"] = scoring["reasons"]
    result["reasons"] = scoring["reasons"]
    result["fail_reason"] = "; ".join(scoring["reasons"]) if scoring["reasons"] else None

    # 5. Write result.json artifact
    result_path = case_artifacts / "result.json"
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)

    return result


# ---------------------------------------------------------------------------
# Batch runner with concurrency control
# ---------------------------------------------------------------------------

async def run_all_live(
    cases_dir: str,
    *,
    base_url: str,
    auth_token: str,
    agent_mode: bool = False,
    artifacts_dir: str = "eval/artifacts",
    concurrency: int = 4,
) -> dict:
    """Run all cases against a live server with bounded concurrency."""
    cases = load_cases(cases_dir)
    if not cases:
        print(f"No cases found in {cases_dir}", file=sys.stderr)
        return {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0}

    art_path = Path(artifacts_dir)
    art_path.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(concurrency)
    results: list[dict] = []

    async with httpx.AsyncClient() as http_client:

        async def _run(case: dict) -> dict:
            async with sem:
                label = case["id"]
                print(f"  [{label}] starting …")
                try:
                    r = await run_case_live(
                        case,
                        base_url=base_url,
                        auth_token=auth_token,
                        agent_mode=agent_mode,
                        artifacts_dir=art_path,
                        http_client=http_client,
                    )
                    status = "PASS" if r["passed"] else "FAIL"
                    print(f"  [{label}] {status}  ({r.get('total_ms', '?')} ms)")
                    return r
                except Exception as exc:
                    print(f"  [{label}] ERROR: {exc}", file=sys.stderr)
                    return {
                        "id": case["id"],
                        "category": case.get("category", "unknown"),
                        "input": case["input"],
                        "passed": False,
                        "failures": [f"runner_exception: {exc}"],
                        "fail_reason": str(exc),
                        "error": str(exc),
                        "simulated": False,
                    }

        tasks = [asyncio.create_task(_run(c)) for c in cases]
        results = await asyncio.gather(*tasks)

    results = list(results)

    # Summary
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    failed = total - passed
    pass_rate = passed / total if total else 0

    summary = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
    }

    # Write overall summary
    summary_path = art_path / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Generate HTML report (writes report.html + report.json into artifacts dir)
    generate_html_report(results, str(art_path))

    return summary


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Live eval runner (SSE)")
    parser.add_argument("--base-url", default="http://localhost:8301", help="Backend base URL")
    parser.add_argument("--token", required=True, help="JWT auth token")
    parser.add_argument("--cases", default="eval/cases", help="YAML case directory")
    parser.add_argument("--artifacts", default="eval/artifacts", help="Artifacts output dir")
    parser.add_argument("--agent-mode", action="store_true", help="Use agent mode")
    parser.add_argument("--concurrency", type=int, default=4, help="Max parallel cases")
    args = parser.parse_args()

    summary = asyncio.run(
        run_all_live(
            args.cases,
            base_url=args.base_url,
            auth_token=args.token,
            agent_mode=args.agent_mode,
            artifacts_dir=args.artifacts,
            concurrency=args.concurrency,
        )
    )

    print(f"\nTotal: {summary['total']}, Passed: {summary['passed']}, "
          f"Failed: {summary['failed']}, Pass Rate: {summary['pass_rate']:.1%}")
    sys.exit(0 if summary["pass_rate"] >= 0.8 else 1)


if __name__ == "__main__":
    main()
