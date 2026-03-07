"""Rule-based scorer — evaluates a live result against extended case rules.

Supported case-level rule fields (all optional, backward-compatible):
  must_contain:      list[str]   — response must contain every substring
  must_not_contain:  list[str]   — response must NOT contain any substring
  must_call_tools:   list[str]   — these tool names must appear in tool_calls
  max_time_ms:       int/float   — total_ms must not exceed this value
  max_tool_calls:    int         — number of tool calls must not exceed this

The scorer also evaluates the classic ``assertions`` list (delegated to
``eval.judge.judge_result``), so old cases work unchanged.
"""

from __future__ import annotations

from eval.judge import judge_result


def score(case: dict, result: dict) -> dict:
    """Score a single result against its case.

    Returns::

        {
            "passed": bool,
            "reasons": list[str],   # human-readable failure reasons (empty if passed)
        }
    """
    reasons: list[str] = []

    # 1. Classic assertions (backward compat)
    judgment = judge_result(case, result)
    reasons.extend(judgment.get("failures", []))

    # 2. must_contain
    for substr in case.get("must_contain", []):
        if substr not in result.get("response", ""):
            reasons.append(f"must_contain: '{substr}' not found in response")

    # 3. must_not_contain
    for substr in case.get("must_not_contain", []):
        if substr in result.get("response", ""):
            reasons.append(f"must_not_contain: '{substr}' found in response")

    # 4. must_call_tools
    called = {tc.get("tool_name") for tc in result.get("tool_calls", [])}
    for tool in case.get("must_call_tools", []):
        if tool not in called:
            reasons.append(f"must_call_tools: '{tool}' was not called")

    # 5. max_time_ms
    max_time = case.get("max_time_ms")
    if max_time is not None:
        total = result.get("total_ms")
        if total is not None and total > max_time:
            reasons.append(f"max_time_ms: {total:.0f} ms > {max_time} ms limit")

    # 6. max_tool_calls
    max_calls = case.get("max_tool_calls")
    if max_calls is not None:
        actual = len(result.get("tool_calls", []))
        if actual > max_calls:
            reasons.append(f"max_tool_calls: {actual} calls > {max_calls} limit")

    return {
        "passed": len(reasons) == 0,
        "reasons": reasons,
    }
