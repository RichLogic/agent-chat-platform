"""Tests for eval.compare — baseline diff and threshold gating."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eval.compare import check_thresholds, compare, load_summary


# ---------------------------------------------------------------------------
# load_summary
# ---------------------------------------------------------------------------

class TestLoadSummary:
    def test_load_report_json(self, tmp_path: Path):
        data = {"summary": {"pass_rate": 0.9, "total": 10}, "results": []}
        (tmp_path / "report.json").write_text(json.dumps(data))
        s = load_summary(str(tmp_path / "report.json"))
        assert s["pass_rate"] == 0.9

    def test_load_summary_json(self, tmp_path: Path):
        data = {"pass_rate": 0.8, "total": 5}
        (tmp_path / "summary.json").write_text(json.dumps(data))
        s = load_summary(str(tmp_path / "summary.json"))
        assert s["pass_rate"] == 0.8


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------

class TestCompare:
    def test_no_change(self):
        base = {"pass_rate": 0.9, "total": 10, "latency": {"total_ms_p90": 1000}}
        curr = {"pass_rate": 0.9, "total": 10, "latency": {"total_ms_p90": 1000}}
        diff = compare(base, curr)
        assert diff["pass_rate"]["delta"] == 0
        assert diff["latency"]["total_ms_p90_delta"] == 0
        assert diff["category_regressions"] == []

    def test_improvement(self):
        base = {"pass_rate": 0.8, "total": 10}
        curr = {"pass_rate": 0.95, "total": 10}
        diff = compare(base, curr)
        assert diff["pass_rate"]["delta"] > 0

    def test_regression(self):
        base = {"pass_rate": 0.9, "total": 10}
        curr = {"pass_rate": 0.7, "total": 10}
        diff = compare(base, curr)
        assert diff["pass_rate"]["delta"] == pytest.approx(-0.2, abs=0.001)

    def test_latency_increase(self):
        base = {"pass_rate": 1.0, "latency": {"total_ms_p90": 1000, "total_ms_p50": 500}}
        curr = {"pass_rate": 1.0, "latency": {"total_ms_p90": 2000, "total_ms_p50": 600}}
        diff = compare(base, curr)
        assert diff["latency"]["total_ms_p90_delta"] == 1000
        assert diff["latency"]["total_ms_p50_delta"] == 100

    def test_category_regression(self):
        base = {
            "pass_rate": 1.0,
            "by_category": {
                "weather": {"total": 5, "passed": 5},
                "search": {"total": 5, "passed": 5},
            },
        }
        curr = {
            "pass_rate": 0.8,
            "by_category": {
                "weather": {"total": 5, "passed": 5},
                "search": {"total": 5, "passed": 3},
            },
        }
        diff = compare(base, curr)
        assert len(diff["category_regressions"]) == 1
        assert diff["category_regressions"][0]["category"] == "search"

    def test_new_category_no_regression(self):
        base = {"pass_rate": 1.0, "by_category": {"weather": {"total": 5, "passed": 5}}}
        curr = {
            "pass_rate": 0.9,
            "by_category": {
                "weather": {"total": 5, "passed": 5},
                "new_cat": {"total": 5, "passed": 4},
            },
        }
        diff = compare(base, curr)
        # new_cat baseline is 0 → current 0.8 → not a regression
        assert all(r["category"] != "new_cat" for r in diff["category_regressions"])

    def test_missing_latency(self):
        diff = compare({"pass_rate": 1.0}, {"pass_rate": 1.0})
        assert diff["latency"]["total_ms_p90_delta"] is None


# ---------------------------------------------------------------------------
# check_thresholds
# ---------------------------------------------------------------------------

class TestCheckThresholds:
    def test_all_ok(self):
        diff = compare(
            {"pass_rate": 0.9, "latency": {"total_ms_p90": 1000}},
            {"pass_rate": 0.88, "latency": {"total_ms_p90": 1200}},
        )
        violations = check_thresholds(diff, max_pass_rate_drop=0.05, max_p90_increase_ms=500)
        assert violations == []

    def test_pass_rate_violation(self):
        diff = compare(
            {"pass_rate": 0.9},
            {"pass_rate": 0.8},
        )
        violations = check_thresholds(diff, max_pass_rate_drop=0.05)
        assert len(violations) == 1
        assert "pass_rate" in violations[0]

    def test_p90_violation(self):
        diff = compare(
            {"pass_rate": 1.0, "latency": {"total_ms_p90": 1000}},
            {"pass_rate": 1.0, "latency": {"total_ms_p90": 2000}},
        )
        violations = check_thresholds(diff, max_pass_rate_drop=0.05, max_p90_increase_ms=500)
        assert len(violations) == 1
        assert "p90" in violations[0].lower()

    def test_no_p90_threshold_set(self):
        diff = compare(
            {"pass_rate": 1.0, "latency": {"total_ms_p90": 1000}},
            {"pass_rate": 1.0, "latency": {"total_ms_p90": 9999}},
        )
        violations = check_thresholds(diff, max_pass_rate_drop=0.05, max_p90_increase_ms=None)
        assert violations == []

    def test_both_violations(self):
        diff = compare(
            {"pass_rate": 0.9, "latency": {"total_ms_p90": 1000}},
            {"pass_rate": 0.7, "latency": {"total_ms_p90": 5000}},
        )
        violations = check_thresholds(diff, max_pass_rate_drop=0.05, max_p90_increase_ms=500)
        assert len(violations) == 2


# ---------------------------------------------------------------------------
# CLI integration (via subprocess-like test)
# ---------------------------------------------------------------------------

class TestCLI:
    def test_output_file(self, tmp_path: Path):
        base_file = tmp_path / "base.json"
        curr_file = tmp_path / "curr.json"
        out_file = tmp_path / "diff.json"

        base_file.write_text(json.dumps({"pass_rate": 0.9, "total": 10}))
        curr_file.write_text(json.dumps({"pass_rate": 0.88, "total": 10}))

        base = load_summary(str(base_file))
        curr = load_summary(str(curr_file))
        diff = compare(base, curr)
        violations = check_thresholds(diff, max_pass_rate_drop=0.05)

        with open(out_file, "w") as f:
            json.dump({"diff": diff, "violations": violations}, f, indent=2)

        result = json.loads(out_file.read_text())
        assert "diff" in result
        assert result["violations"] == []
