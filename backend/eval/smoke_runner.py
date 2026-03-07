"""Smoke eval runner — runs a handful of cases against an in-process mock server.

No external API keys needed.  Designed for CI ``make eval-smoke``.

Also serves as the ``eval-nightly`` entry-point: when ``AC_EVAL_TOKEN`` and
``AC_EVAL_BASE_URL`` are set, it delegates to ``live_runner.run_all_live``
against a real server instead.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from eval.live_runner import load_cases, run_case_live
from eval.report_html import generate_html_report
from eval.scorers.rule_scorer import score as rule_score


# ---------------------------------------------------------------------------
# Smoke runner (in-process, mock LLM)
# ---------------------------------------------------------------------------

async def run_smoke(
    cases_dir: str = "eval/cases",
    case_file: str = "smoke.yaml",
    artifacts_dir: str = "eval/artifacts-smoke",
) -> dict:
    """Run smoke cases against an in-process TestClient with mock LLM."""
    # Load only smoke cases
    smoke_path = Path(cases_dir) / case_file
    if not smoke_path.exists():
        print(f"Smoke case file not found: {smoke_path}", file=sys.stderr)
        return {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0}

    import yaml

    with open(smoke_path) as f:
        cases = yaml.safe_load(f) or []
    for case in cases:
        case.setdefault("source_file", case_file)

    if not cases:
        return {"total": 0, "passed": 0, "failed": 0, "pass_rate": 0}

    art_path = Path(artifacts_dir)
    art_path.mkdir(parents=True, exist_ok=True)

    # Build in-process test app (mock LLM, mock DB — no keys needed)
    import httpx
    from mongomock_motor import AsyncMongoMockClient
    from unittest.mock import patch

    from agent_chat.auth.middleware import get_current_user_id
    from agent_chat.config import Settings, set_settings
    from agent_chat.llm.provider import ChatResponse, StreamChunk

    settings = Settings(
        _env_file=None,
        mongo_uri="mongodb://localhost:27017",
        mongo_db="smoke_db",
        data_dir=str(art_path / "_data"),
        jwt_secret="smoke-test-secret",
        jwt_expiry_minutes=60,
        github_client_id="smoke",
        github_client_secret="smoke",
        frontend_url="http://localhost:3000",
        llm_provider="poe",
        poe_api_key="smoke-key",
        poe_model="smoke-model",
        poe_base_url="https://smoke.example.com/v1",
        log_level="WARNING",
    )
    set_settings(settings)

    # Mock LLM
    class _MockLLM:
        provider_name = "mock"
        model = "mock-model"

        async def stream_chat(self, messages):
            yield StreamChunk(content="Hello! ")
            yield StreamChunk(content="I'm an AI assistant. How can I help you today?")
            yield StreamChunk(
                usage={"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22}
            )

        async def chat(self, messages):
            return ChatResponse(
                content="Smoke Test",
                usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            )

    mock_provider = _MockLLM()

    # Patch DB
    mock_client = AsyncMongoMockClient()
    mock_db = mock_client["smoke_db"]

    from fastapi import FastAPI
    from agent_chat.api.router import api_router

    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_current_user_id] = lambda: "smoke_user"

    results: list[dict] = []

    with (
        patch("agent_chat.db.mongo._db", mock_db),
        patch("agent_chat.services.chat_service.create_provider", return_value=mock_provider),
        patch("agent_chat.services.title_service.create_provider", return_value=mock_provider),
    ):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://smoke") as client:
            for case in cases:
                label = case["id"]
                print(f"  [{label}] running …")
                try:
                    r = await run_case_live(
                        case,
                        base_url="http://smoke",
                        auth_token="ignored",
                        agent_mode=False,
                        artifacts_dir=art_path,
                        http_client=client,
                    )
                    status = "PASS" if r["passed"] else "FAIL"
                    print(f"  [{label}] {status}")
                    results.append(r)
                except Exception as exc:
                    print(f"  [{label}] ERROR: {exc}", file=sys.stderr)
                    results.append({
                        "id": case["id"],
                        "category": case.get("category", "unknown"),
                        "input": case.get("input", ""),
                        "passed": False,
                        "failures": [f"runner_exception: {exc}"],
                        "reasons": [f"runner_exception: {exc}"],
                        "fail_reason": str(exc),
                        "error": str(exc),
                        "simulated": False,
                    })

    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    failed = total - passed
    pass_rate = passed / total if total else 0

    summary = {"total": total, "passed": passed, "failed": failed, "pass_rate": pass_rate}

    with open(art_path / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    generate_html_report(results, str(art_path))

    return summary


# ---------------------------------------------------------------------------
# Nightly runner (live, needs env vars)
# ---------------------------------------------------------------------------

async def run_nightly(
    cases_dir: str = "eval/cases",
    artifacts_dir: str = "eval/artifacts-nightly",
) -> dict | None:
    """Run full live eval if AC_EVAL_TOKEN + AC_EVAL_BASE_URL are set.

    Returns None (skipped) if env vars are missing.
    """
    token = os.environ.get("AC_EVAL_TOKEN")
    base_url = os.environ.get("AC_EVAL_BASE_URL", "http://localhost:8301")

    if not token:
        print("AC_EVAL_TOKEN not set — skipping nightly eval.", file=sys.stderr)
        return None

    from eval.live_runner import run_all_live

    return await run_all_live(
        cases_dir,
        base_url=base_url,
        auth_token=token,
        agent_mode=False,
        artifacts_dir=artifacts_dir,
        concurrency=int(os.environ.get("AC_EVAL_CONCURRENCY", "4")),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Smoke / nightly eval runner")
    sub = parser.add_subparsers(dest="cmd")

    smoke_p = sub.add_parser("smoke", help="Run smoke cases (mock LLM, no keys)")
    smoke_p.add_argument("--cases", default="eval/cases")
    smoke_p.add_argument("--artifacts", default="eval/artifacts-smoke")

    nightly_p = sub.add_parser("nightly", help="Run nightly live eval (needs AC_EVAL_TOKEN)")
    nightly_p.add_argument("--cases", default="eval/cases")
    nightly_p.add_argument("--artifacts", default="eval/artifacts-nightly")

    args = parser.parse_args()

    if args.cmd == "nightly":
        summary = asyncio.run(run_nightly(args.cases, args.artifacts))
        if summary is None:
            print("Skipped (no token).")
            sys.exit(0)
    else:
        # Default to smoke
        cases = getattr(args, "cases", "eval/cases")
        artifacts = getattr(args, "artifacts", "eval/artifacts-smoke")
        summary = asyncio.run(run_smoke(cases, artifacts_dir=artifacts))

    print(f"\nTotal: {summary['total']}, Passed: {summary['passed']}, "
          f"Failed: {summary['failed']}, Pass Rate: {summary['pass_rate']:.1%}")
    sys.exit(0 if summary.get("pass_rate", 0) >= 1.0 else 1)


if __name__ == "__main__":
    main()
