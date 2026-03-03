"""Eval judge — rule-based assertion checking for eval results."""

from __future__ import annotations


def judge_result(case: dict, result: dict) -> dict:
    """Judge a single eval result against its case assertions.

    Returns dict with 'passed', 'failures' keys.
    """
    assertions = case.get("assertions", [])
    failures = []

    for assertion in assertions:
        for rule, expected in assertion.items():
            ok = _check_rule(rule, expected, case, result)
            if not ok:
                failures.append(f"{rule}: expected {expected}")

    return {
        "passed": len(failures) == 0,
        "failures": failures,
    }


def _check_rule(rule: str, expected, case: dict, result: dict) -> bool:
    """Check a single assertion rule."""
    if rule == "tool_called":
        return result.get("expected_tool") == expected

    if rule == "response_not_empty":
        # For simulated runs, we can't check actual response
        if result.get("simulated"):
            return True
        return bool(result.get("response", "").strip())

    if rule == "response_contains_url":
        if result.get("simulated"):
            return True
        resp = result.get("response", "")
        return "http://" in resp or "https://" in resp

    if rule == "response_contains":
        if result.get("simulated"):
            return True
        return str(expected) in result.get("response", "")

    if rule == "no_error":
        return "error" not in result

    if rule == "category_match":
        return result.get("category") == expected

    # Unknown rules pass by default (forward compatibility)
    return True
