"""Tests for live_runner — SSE parsing and result extraction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.live_runner import extract_result_from_events, load_cases, parse_sse_line


# ---------------------------------------------------------------------------
# parse_sse_line
# ---------------------------------------------------------------------------

class TestParseSSELine:
    def test_valid_data_line(self):
        line = 'data: {"type": "text.delta", "data": {"content": "hi"}}'
        result = parse_sse_line(line)
        assert result == {"type": "text.delta", "data": {"content": "hi"}}

    def test_empty_line(self):
        assert parse_sse_line("") is None

    def test_comment_line(self):
        assert parse_sse_line(": keep-alive") is None

    def test_event_line_ignored(self):
        assert parse_sse_line("event: text.delta") is None

    def test_invalid_json(self):
        assert parse_sse_line("data: {broken") is None

    def test_whitespace_padding(self):
        line = '  data: {"ok": true}  '
        result = parse_sse_line(line)
        assert result == {"ok": True}


# ---------------------------------------------------------------------------
# extract_result_from_events
# ---------------------------------------------------------------------------

def _make_events() -> list[dict]:
    """Build a realistic sequence of SSE events."""
    return [
        {
            "type": "run.start",
            "ts": "2026-01-01T00:00:00+00:00",
            "data": {"run_id": "r1", "provider": "poe", "model": "test"},
        },
        {
            "type": "tool.call",
            "ts": "2026-01-01T00:00:00.100+00:00",
            "data": {"tool_name": "weather", "arguments": {"city": "Beijing"}},
        },
        {
            "type": "tool.result",
            "ts": "2026-01-01T00:00:01+00:00",
            "data": {"tool_name": "weather", "result": {"temp": 22}},
        },
        {
            "type": "text.delta",
            "ts": "2026-01-01T00:00:01.200+00:00",
            "data": {"content": "The weather "},
        },
        {
            "type": "text.delta",
            "ts": "2026-01-01T00:00:01.300+00:00",
            "data": {"content": "is 22°C."},
        },
        {
            "type": "run.finish",
            "ts": "2026-01-01T00:00:02+00:00",
            "data": {
                "finish_reason": "stop",
                "token_usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            },
        },
    ]


class TestExtractResult:
    def test_final_answer(self):
        result = extract_result_from_events(_make_events())
        assert result["response"] == "The weather is 22°C."

    def test_tool_calls(self):
        result = extract_result_from_events(_make_events())
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool_name"] == "weather"
        assert result["tool_calls"][0]["arguments"] == {"city": "Beijing"}

    def test_tool_calls_accept_name_field(self):
        events = _make_events()
        events[1]["data"] = {"name": "weather", "arguments": {"city": "Beijing"}}
        result = extract_result_from_events(events)
        assert result["tool_calls"][0]["tool_name"] == "weather"

    def test_ttft_ms(self):
        result = extract_result_from_events(_make_events())
        # run.start = 0s, first text.delta = 1.2s → 1200 ms
        assert result["ttft_ms"] is not None
        assert result["ttft_ms"] == pytest.approx(1200, abs=5)

    def test_total_ms(self):
        result = extract_result_from_events(_make_events())
        # run.start = 0s, run.finish = 2s → 2000 ms
        assert result["total_ms"] is not None
        assert result["total_ms"] == pytest.approx(2000, abs=5)

    def test_token_usage(self):
        result = extract_result_from_events(_make_events())
        assert result["token_usage"]["total_tokens"] == 70

    def test_no_error_by_default(self):
        result = extract_result_from_events(_make_events())
        assert "error" not in result

    def test_error_captured(self):
        events = [
            {"type": "run.start", "ts": "2026-01-01T00:00:00+00:00", "data": {}},
            {"type": "error", "ts": "2026-01-01T00:00:01+00:00", "data": {"message": "boom"}},
        ]
        result = extract_result_from_events(events)
        assert result["error"] == "boom"

    def test_empty_events(self):
        result = extract_result_from_events([])
        assert result["response"] == ""
        assert result["tool_calls"] == []
        assert result["ttft_ms"] is None
        assert result["total_ms"] is None


# ---------------------------------------------------------------------------
# Integration: extract → judge round-trip
# ---------------------------------------------------------------------------

class TestExtractAndJudge:
    def test_live_result_passes_judge(self):
        from eval.judge import judge_result

        case = {
            "id": "w001",
            "category": "weather",
            "input": "北京天气",
            "expected_tool": "weather",
            "assertions": [
                {"tool_called": "weather"},
                {"response_not_empty": True},
                {"no_error": True},
            ],
        }
        extracted = extract_result_from_events(_make_events())
        result = {
            **extracted,
            "id": case["id"],
            "category": case["category"],
            "expected_tool": case["expected_tool"],
            "simulated": False,
        }
        judgment = judge_result(case, result)
        assert judgment["passed"] is True
        assert judgment["failures"] == []

    def test_live_result_fails_wrong_tool(self):
        from eval.judge import judge_result

        case = {
            "id": "s001",
            "assertions": [{"tool_called": "search"}],
        }
        result = {"tool_calls": [{"tool_name": "weather"}], "simulated": False}
        judgment = judge_result(case, result)
        assert judgment["passed"] is False


class TestLoadCases:
    def test_load_specific_case_file(self, tmp_path: Path):
        (tmp_path / "a.yaml").write_text("- id: a1\n  category: a\n  input: hi\n")
        (tmp_path / "b.yaml").write_text("- id: b1\n  category: b\n  input: hi\n")

        cases = load_cases(str(tmp_path), case_file="b.yaml")

        assert len(cases) == 1
        assert cases[0]["id"] == "b1"


# ---------------------------------------------------------------------------
# Artifact writing (via run_case_live with mocked SSE)
# ---------------------------------------------------------------------------

class TestArtifactWriting:
    @pytest.mark.asyncio
    async def test_run_case_writes_artifacts(self, tmp_path: Path, test_app):
        """Run a case against the TestClient and verify artifact files."""
        import httpx as _httpx

        from eval.live_runner import run_case_live

        transport = _httpx.ASGITransport(app=test_app)
        async with _httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            case = {
                "id": "artifact_test_001",
                "category": "test",
                "input": "hello",
                "expected_tool": "search",
                "assertions": [{"response_not_empty": True}],
            }
            result = await run_case_live(
                case,
                base_url="http://test",
                auth_token="ignored",  # overridden by test_app
                agent_mode=False,
                artifacts_dir=tmp_path / "artifacts",
                http_client=client,
            )

        # Artifact files exist
        case_dir = tmp_path / "artifacts" / "artifact_test_001"
        assert (case_dir / "events.jsonl").exists()
        assert (case_dir / "result.json").exists()

        # events.jsonl has valid JSONL
        lines = (case_dir / "events.jsonl").read_text().strip().split("\n")
        assert len(lines) >= 1
        for line in lines:
            json.loads(line)  # must not raise

        # result.json is valid and has expected fields
        result_data = json.loads((case_dir / "result.json").read_text())
        assert result_data["id"] == "artifact_test_001"
        assert "response" in result_data
        assert "tool_calls" in result_data
        assert "ttft_ms" in result_data
        assert "total_ms" in result_data
        assert "passed" in result_data
        assert result_data["simulated"] is False
