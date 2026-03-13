"""Tests for eval.scorers.rule_scorer and eval.report_html."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.scorers.rule_scorer import score


# ---------------------------------------------------------------------------
# rule_scorer.score — basic assertions (backward compat)
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_classic_assertions_pass(self):
        case = {
            "id": "t1",
            "assertions": [{"tool_called": "search"}, {"no_error": True}],
        }
        result = {"expected_tool": "search", "simulated": True}
        s = score(case, result)
        assert s["passed"] is True
        assert s["reasons"] == []

    def test_classic_assertions_fail(self):
        case = {
            "id": "t2",
            "assertions": [{"tool_called": "search"}],
        }
        result = {"expected_tool": "weather", "simulated": True}
        s = score(case, result)
        assert s["passed"] is False
        assert any("tool_called" in r for r in s["reasons"])

    def test_no_extra_fields_still_works(self):
        case = {"id": "t3", "assertions": []}
        result = {}
        s = score(case, result)
        assert s["passed"] is True


# ---------------------------------------------------------------------------
# must_contain / must_not_contain
# ---------------------------------------------------------------------------

class TestContainRules:
    def test_must_contain_pass(self):
        case = {"id": "c1", "must_contain": ["hello", "world"]}
        result = {"response": "hello beautiful world"}
        s = score(case, result)
        assert s["passed"] is True

    def test_must_contain_fail(self):
        case = {"id": "c2", "must_contain": ["missing"]}
        result = {"response": "nothing here"}
        s = score(case, result)
        assert s["passed"] is False
        assert "must_contain" in s["reasons"][0]

    def test_must_not_contain_pass(self):
        case = {"id": "c3", "must_not_contain": ["ERROR", "FAIL"]}
        result = {"response": "all good"}
        s = score(case, result)
        assert s["passed"] is True

    def test_must_not_contain_fail(self):
        case = {"id": "c4", "must_not_contain": ["bad"]}
        result = {"response": "this is bad"}
        s = score(case, result)
        assert s["passed"] is False
        assert "must_not_contain" in s["reasons"][0]


# ---------------------------------------------------------------------------
# must_call_tools
# ---------------------------------------------------------------------------

class TestMustCallTools:
    def test_pass(self):
        case = {"id": "mt1", "must_call_tools": ["weather", "search"]}
        result = {
            "tool_calls": [
                {"tool_name": "weather", "arguments": {}},
                {"tool_name": "search", "arguments": {}},
            ]
        }
        s = score(case, result)
        assert s["passed"] is True

    def test_fail_missing_tool(self):
        case = {"id": "mt2", "must_call_tools": ["weather", "search"]}
        result = {"tool_calls": [{"tool_name": "weather", "arguments": {}}]}
        s = score(case, result)
        assert s["passed"] is False
        assert any("search" in r for r in s["reasons"])

    def test_no_tool_calls_field(self):
        case = {"id": "mt3", "must_call_tools": ["weather"]}
        result = {}
        s = score(case, result)
        assert s["passed"] is False


# ---------------------------------------------------------------------------
# max_time_ms / max_tool_calls
# ---------------------------------------------------------------------------

class TestLimits:
    def test_max_time_pass(self):
        case = {"id": "l1", "max_time_ms": 5000}
        result = {"total_ms": 3000}
        s = score(case, result)
        assert s["passed"] is True

    def test_max_time_fail(self):
        case = {"id": "l2", "max_time_ms": 5000}
        result = {"total_ms": 8000}
        s = score(case, result)
        assert s["passed"] is False
        assert "max_time_ms" in s["reasons"][0]

    def test_max_time_none_total(self):
        """If total_ms is None, we cannot check — should pass."""
        case = {"id": "l3", "max_time_ms": 5000}
        result = {"total_ms": None}
        s = score(case, result)
        assert s["passed"] is True

    def test_max_tool_calls_pass(self):
        case = {"id": "l4", "max_tool_calls": 3}
        result = {"tool_calls": [{"tool_name": "a"}, {"tool_name": "b"}]}
        s = score(case, result)
        assert s["passed"] is True

    def test_max_tool_calls_fail(self):
        case = {"id": "l5", "max_tool_calls": 1}
        result = {"tool_calls": [{"tool_name": "a"}, {"tool_name": "b"}]}
        s = score(case, result)
        assert s["passed"] is False
        assert "max_tool_calls" in s["reasons"][0]


# ---------------------------------------------------------------------------
# combined rules
# ---------------------------------------------------------------------------

class TestCombined:
    def test_all_rules_together_pass(self):
        case = {
            "id": "combo1",
            "assertions": [{"no_error": True}],
            "must_contain": ["Beijing"],
            "must_not_contain": ["ERROR"],
            "must_call_tools": ["weather"],
            "max_time_ms": 10000,
            "max_tool_calls": 3,
        }
        result = {
            "response": "Beijing weather is sunny",
            "tool_calls": [{"tool_name": "weather", "arguments": {}}],
            "total_ms": 2500,
        }
        s = score(case, result)
        assert s["passed"] is True
        assert s["reasons"] == []

    def test_multiple_failures(self):
        case = {
            "id": "combo2",
            "must_contain": ["missing"],
            "must_call_tools": ["search"],
            "max_time_ms": 100,
        }
        result = {
            "response": "nothing",
            "tool_calls": [],
            "total_ms": 5000,
        }
        s = score(case, result)
        assert s["passed"] is False
        assert len(s["reasons"]) == 3


# ---------------------------------------------------------------------------
# report_html.generate_html_report
# ---------------------------------------------------------------------------

class TestHTMLReport:
    def test_generates_files(self, tmp_path: Path):
        from eval.report_html import generate_html_report

        results = [
            {
                "id": "r1", "category": "weather", "input": "test",
                "passed": True, "failures": [], "reasons": [],
                "total_ms": 1200, "ttft_ms": 300,
            },
            {
                "id": "r2", "category": "search", "input": "query",
                "passed": False, "failures": ["must_contain: 'x' not found"],
                "reasons": ["must_contain: 'x' not found"],
                "total_ms": 5000, "ttft_ms": 800,
            },
        ]
        out = str(tmp_path / "report")
        summary = generate_html_report(results, out)

        assert (tmp_path / "report" / "report.html").exists()
        assert (tmp_path / "report" / "report.json").exists()
        assert summary["total"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert summary["latency"]["total_ms_p50"] is not None

    def test_html_contains_key_elements(self, tmp_path: Path):
        from eval.report_html import generate_html_report

        results = [
            {
                "id": "h1", "category": "weather", "input": "hello",
                "passed": False, "failures": ["oops"], "reasons": ["oops"],
                "total_ms": 999, "ttft_ms": 100,
            },
        ]
        generate_html_report(results, str(tmp_path / "r"))
        html = (tmp_path / "r" / "report.html").read_text()
        assert "Eval Report" in html
        assert "h1" in html  # case id
        assert "oops" in html  # failure reason
        assert "events.jsonl" in html  # artifact link

    def test_json_report_valid(self, tmp_path: Path):
        from eval.report_html import generate_html_report

        results = [
            {
                "id": "j1", "category": "c", "input": "测试",
                "passed": True, "failures": [], "reasons": [],
                "total_ms": 500, "ttft_ms": 50,
            },
        ]
        generate_html_report(results, str(tmp_path / "r"))
        data = json.loads((tmp_path / "r" / "report.json").read_text())
        assert data["summary"]["total"] == 1
        assert data["results"][0]["input"] == "测试"

    def test_latency_stats(self, tmp_path: Path):
        from eval.report_html import generate_html_report

        results = [
            {"id": f"p{i}", "category": "c", "passed": True, "failures": [], "reasons": [],
             "total_ms": i * 100, "ttft_ms": i * 10}
            for i in range(1, 11)
        ]
        summary = generate_html_report(results, str(tmp_path / "r"))
        lat = summary["latency"]
        assert lat["total_ms_p50"] is not None
        assert lat["total_ms_p90"] is not None
        assert lat["total_ms_p90"] >= lat["total_ms_p50"]

    def test_empty_results(self, tmp_path: Path):
        from eval.report_html import generate_html_report

        summary = generate_html_report([], str(tmp_path / "r"))
        assert summary["total"] == 0
        assert summary["pass_rate"] == 0
        assert (tmp_path / "r" / "report.html").exists()
