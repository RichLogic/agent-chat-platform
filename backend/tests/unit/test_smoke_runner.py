"""Tests for eval.smoke_runner — smoke eval with mock LLM."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestSmokeRunner:
    @pytest.mark.asyncio
    async def test_run_smoke_passes(self, tmp_path: Path):
        from eval.smoke_runner import run_smoke

        summary = await run_smoke(
            cases_dir="eval/cases",
            case_file="smoke.yaml",
            artifacts_dir=str(tmp_path / "artifacts"),
        )

        assert summary["total"] == 3
        assert summary["passed"] == 3
        assert summary["pass_rate"] == 1.0

        # Artifacts written
        assert (tmp_path / "artifacts" / "summary.json").exists()
        assert (tmp_path / "artifacts" / "report.html").exists()
        assert (tmp_path / "artifacts" / "report.json").exists()

        # Each case has its own dir
        for case_id in ("smoke_chat_basic", "smoke_chat_longer", "smoke_chat_english"):
            case_dir = tmp_path / "artifacts" / case_id
            assert (case_dir / "events.jsonl").exists()
            assert (case_dir / "result.json").exists()

            result = json.loads((case_dir / "result.json").read_text())
            assert result["passed"] is True
            assert result["simulated"] is False
            assert result["response"] != ""

    @pytest.mark.asyncio
    async def test_run_smoke_missing_file(self, tmp_path: Path):
        from eval.smoke_runner import run_smoke

        summary = await run_smoke(
            cases_dir=str(tmp_path),
            case_file="nonexistent.yaml",
            artifacts_dir=str(tmp_path / "artifacts"),
        )
        assert summary["total"] == 0


class TestNightlySkip:
    @pytest.mark.asyncio
    async def test_nightly_skips_without_token(self, monkeypatch):
        from eval.smoke_runner import run_nightly

        monkeypatch.delenv("AC_EVAL_TOKEN", raising=False)
        result = await run_nightly()
        assert result is None
