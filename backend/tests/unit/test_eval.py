"""Tests for eval framework — runner, judge, report."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Tests — load_cases
# ---------------------------------------------------------------------------

class TestLoadCases:
    def test_load_all_yaml_files(self, tmp_path: Path) -> None:
        from eval.runner import load_cases

        cases_dir = tmp_path / "cases"
        cases_dir.mkdir()
        (cases_dir / "a.yaml").write_text(yaml.dump([
            {"id": "a_001", "category": "a", "input": "hello", "expected_tool": "search"},
        ]))
        (cases_dir / "b.yaml").write_text(yaml.dump([
            {"id": "b_001", "category": "b", "input": "world", "expected_tool": "weather"},
        ]))

        cases = load_cases(str(cases_dir))
        assert len(cases) == 2
        assert cases[0]["id"] == "a_001"
        assert cases[1]["id"] == "b_001"

    def test_adds_source_file(self, tmp_path: Path) -> None:
        from eval.runner import load_cases

        cases_dir = tmp_path / "cases"
        cases_dir.mkdir()
        (cases_dir / "test.yaml").write_text(yaml.dump([
            {"id": "t_001", "category": "test", "input": "x"},
        ]))

        cases = load_cases(str(cases_dir))
        assert cases[0]["source_file"] == "test.yaml"

    def test_empty_directory(self, tmp_path: Path) -> None:
        from eval.runner import load_cases

        cases_dir = tmp_path / "cases"
        cases_dir.mkdir()
        cases = load_cases(str(cases_dir))
        assert cases == []

    def test_load_real_cases(self) -> None:
        from eval.runner import load_cases

        cases = load_cases("eval/cases")
        assert len(cases) >= 56
        ids = [c["id"] for c in cases]
        assert len(ids) == len(set(ids)), "Case IDs must be unique"


# ---------------------------------------------------------------------------
# Tests — judge_result
# ---------------------------------------------------------------------------

class TestJudgeResult:
    def test_tool_called_pass(self) -> None:
        from eval.judge import judge_result

        case = {
            "id": "t1",
            "assertions": [{"tool_called": "search"}],
        }
        result = {"expected_tool": "search"}
        judgment = judge_result(case, result)
        assert judgment["passed"] is True
        assert judgment["failures"] == []

    def test_tool_called_fail(self) -> None:
        from eval.judge import judge_result

        case = {
            "id": "t2",
            "assertions": [{"tool_called": "search"}],
        }
        result = {"expected_tool": "weather"}
        judgment = judge_result(case, result)
        assert judgment["passed"] is False
        assert len(judgment["failures"]) == 1

    def test_response_not_empty_simulated(self) -> None:
        from eval.judge import judge_result

        case = {
            "id": "t3",
            "assertions": [{"response_not_empty": True}],
        }
        result = {"simulated": True}
        judgment = judge_result(case, result)
        assert judgment["passed"] is True

    def test_response_not_empty_live(self) -> None:
        from eval.judge import judge_result

        case = {
            "id": "t4",
            "assertions": [{"response_not_empty": True}],
        }
        result = {"response": "some content"}
        judgment = judge_result(case, result)
        assert judgment["passed"] is True

    def test_response_not_empty_live_fails(self) -> None:
        from eval.judge import judge_result

        case = {
            "id": "t5",
            "assertions": [{"response_not_empty": True}],
        }
        result = {"response": ""}
        judgment = judge_result(case, result)
        assert judgment["passed"] is False

    def test_no_error_pass(self) -> None:
        from eval.judge import judge_result

        case = {
            "id": "t6",
            "assertions": [{"no_error": True}],
        }
        result = {"status": "ok"}
        judgment = judge_result(case, result)
        assert judgment["passed"] is True

    def test_no_error_fail(self) -> None:
        from eval.judge import judge_result

        case = {
            "id": "t7",
            "assertions": [{"no_error": True}],
        }
        result = {"error": "something went wrong"}
        judgment = judge_result(case, result)
        assert judgment["passed"] is False

    def test_multiple_assertions(self) -> None:
        from eval.judge import judge_result

        case = {
            "id": "t8",
            "assertions": [
                {"tool_called": "search"},
                {"response_not_empty": True},
                {"no_error": True},
            ],
        }
        result = {"expected_tool": "search", "simulated": True}
        judgment = judge_result(case, result)
        assert judgment["passed"] is True

    def test_unknown_rule_passes(self) -> None:
        from eval.judge import judge_result

        case = {
            "id": "t9",
            "assertions": [{"future_rule": "whatever"}],
        }
        result = {}
        judgment = judge_result(case, result)
        assert judgment["passed"] is True


# ---------------------------------------------------------------------------
# Tests — generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_report_files_created(self, tmp_path: Path) -> None:
        from eval.report import generate_report

        results = [
            {"id": "a_001", "category": "a", "passed": True, "failures": []},
            {"id": "a_002", "category": "a", "passed": False, "failures": ["tool_called: expected search"]},
            {"id": "b_001", "category": "b", "passed": True, "failures": []},
        ]

        output_dir = str(tmp_path / "reports")
        summary = generate_report(results, output_dir)

        assert (tmp_path / "reports" / "report.json").exists()
        assert (tmp_path / "reports" / "report.md").exists()

    def test_summary_correct(self, tmp_path: Path) -> None:
        from eval.report import generate_report

        results = [
            {"id": "a_001", "category": "a", "passed": True, "failures": []},
            {"id": "a_002", "category": "a", "passed": False, "failures": ["err"]},
            {"id": "b_001", "category": "b", "passed": True, "failures": []},
        ]

        summary = generate_report(results, str(tmp_path / "reports"))
        assert summary["total"] == 3
        assert summary["passed"] == 2
        assert summary["failed"] == 1
        assert abs(summary["pass_rate"] - 2 / 3) < 0.01

    def test_category_breakdown(self, tmp_path: Path) -> None:
        from eval.report import generate_report

        results = [
            {"id": "a_001", "category": "weather", "passed": True, "failures": []},
            {"id": "a_002", "category": "weather", "passed": True, "failures": []},
            {"id": "b_001", "category": "search", "passed": False, "failures": ["err"]},
        ]

        summary = generate_report(results, str(tmp_path / "reports"))
        assert summary["by_category"]["weather"]["total"] == 2
        assert summary["by_category"]["weather"]["passed"] == 2
        assert summary["by_category"]["search"]["total"] == 1
        assert summary["by_category"]["search"]["passed"] == 0

    def test_json_report_valid(self, tmp_path: Path) -> None:
        from eval.report import generate_report

        results = [
            {"id": "x", "category": "c", "passed": True, "failures": [], "input": "测试中文"},
        ]

        generate_report(results, str(tmp_path / "reports"))
        data = json.loads((tmp_path / "reports" / "report.json").read_text())
        assert "summary" in data
        assert "results" in data
        assert data["results"][0]["input"] == "测试中文"

    def test_markdown_contains_failures(self, tmp_path: Path) -> None:
        from eval.report import generate_report

        results = [
            {"id": "f1", "category": "x", "passed": False, "failures": ["tool_called: expected search"],
             "input": "test input"},
        ]

        generate_report(results, str(tmp_path / "reports"))
        md = (tmp_path / "reports" / "report.md").read_text()
        assert "f1" in md
        assert "test input" in md


# ---------------------------------------------------------------------------
# Tests — run_case + run_all
# ---------------------------------------------------------------------------

class TestRunner:
    @pytest.mark.asyncio
    async def test_run_case_simulated(self) -> None:
        from eval.runner import run_case

        case = {
            "id": "test_001",
            "category": "test",
            "input": "some input",
            "expected_tool": "search",
            "assertions": [{"tool_called": "search"}],
        }
        result = await run_case(case)
        assert result["id"] == "test_001"
        assert result["simulated"] is True
        assert result["needs_live_eval"] is True

    @pytest.mark.asyncio
    async def test_run_all_produces_report(self, tmp_path: Path) -> None:
        from eval.runner import run_all

        cases_dir = tmp_path / "cases"
        cases_dir.mkdir()
        (cases_dir / "t.yaml").write_text(yaml.dump([
            {"id": "t_001", "category": "t", "input": "q", "expected_tool": "search",
             "assertions": [{"tool_called": "search"}]},
            {"id": "t_002", "category": "t", "input": "q2", "expected_tool": "weather",
             "assertions": [{"tool_called": "weather"}]},
        ]))

        output_dir = str(tmp_path / "reports")
        summary = await run_all(str(cases_dir), output_dir)
        assert summary["total"] == 2
        assert summary["passed"] == 2
        assert summary["pass_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_run_all_empty(self, tmp_path: Path) -> None:
        from eval.runner import run_all

        cases_dir = tmp_path / "cases"
        cases_dir.mkdir()
        summary = await run_all(str(cases_dir), str(tmp_path / "reports"))
        assert summary["total"] == 0


# ---------------------------------------------------------------------------
# Tests — real case files validation
# ---------------------------------------------------------------------------

class TestCaseFilesValidation:
    def test_all_cases_have_required_fields(self) -> None:
        from eval.runner import load_cases

        cases = load_cases("eval/cases")
        for case in cases:
            assert "id" in case, f"Missing id in case"
            assert "category" in case, f"Missing category in {case.get('id')}"
            assert "input" in case, f"Missing input in {case.get('id')}"
            assert "expected_tool" in case, f"Missing expected_tool in {case.get('id')}"

    def test_all_cases_have_assertions(self) -> None:
        from eval.runner import load_cases

        cases = load_cases("eval/cases")
        for case in cases:
            assertions = case.get("assertions", [])
            assert len(assertions) > 0, f"No assertions in {case['id']}"

    def test_category_counts(self) -> None:
        from eval.runner import load_cases
        from collections import Counter

        cases = load_cases("eval/cases")
        counts = Counter(c["category"] for c in cases)
        assert counts["weather"] == 6
        assert counts["news"] == 5
        assert counts["search"] == 6
        assert counts["pdf_rag"] == 10
        assert counts["memory"] == 10
        assert counts["mcp_notes"] == 5
        assert counts["webpage"] == 5
        assert counts["multi_step"] == 6
        assert counts["smoke"] == 3
