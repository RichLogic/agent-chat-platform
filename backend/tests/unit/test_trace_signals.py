from __future__ import annotations

from eval.live_runner import extract_trace_signals


def test_extract_trace_signals_counts() -> None:
    events = [
        {"type": "planner.start", "data": {}},
        {"type": "tool.call", "data": {}},
        {"type": "tool.retry", "data": {}},
        {"type": "tool.result", "data": {"code": "TIMEOUT"}},
        {"type": "run.finish", "data": {}},
    ]
    sig = extract_trace_signals(events)
    assert sig["planner_stage_seen"] is True
    assert sig["tool_call_count"] == 1
    assert sig["retry_count"] == 1
    assert sig["tool_failure_count"] == 1
    assert sig["final_answer_seen"] is True
