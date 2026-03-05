"""LangGraph plan-and-execute graph with concurrent tool execution and checkpoint support.

Graph flow:  START → planner → executor → synthesizer → END

The planner calls the LLM to produce a structured JSON plan listing tool calls.
The executor runs those tool calls concurrently (grouped by parallel_group).
The synthesizer streams a final answer using tool results as context.

All SSE events are emitted via LangGraph's custom stream writer so the outer
service can yield them directly to the client.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, TypedDict

import structlog
from langgraph.config import get_stream_writer
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from agent_chat.llm.factory import FallbackProvider
from agent_chat.tools.registry import ToolRegistry

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: list[dict]         # conversation history (role/content dicts)
    user_content: str            # current user message
    plan: dict | None            # raw planner output
    tool_calls: list[dict]       # [{name, arguments, parallel_group, risk_level}]
    tool_results: list[dict]     # [{name, result, ok, error?}]
    final_text: str              # synthesizer's streamed answer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(event_type: str, data: dict) -> dict:
    return {
        "type": event_type,
        "ts": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


PLANNER_PROMPT = """\
你是一个任务规划器。根据用户的问题和可用工具，生成一个执行计划。

当前时间：{current_datetime}

可用工具：
{tools_schema}

请输出 **仅** 一个 JSON 对象（不要输出其他文字），格式如下：
{{
  "thought": "你的分析思路",
  "tool_calls": [
    {{
      "name": "工具名称",
      "arguments": {{"参数名": "参数值"}},
      "parallel_group": 0,
      "reason": "为什么需要调用这个工具"
    }}
  ]
}}

规则：
1. parallel_group 相同的工具会被并发执行。如果两个工具之间没有依赖关系，应该放在同一个 parallel_group。
2. 如果不需要调用任何工具，返回 {{"thought": "...", "tool_calls": []}}
3. 最多安排 5 个工具调用。
4. 只使用上面列出的工具。
"""


def _build_planner_messages(
    tools_schema: str,
    history: list[dict],
    user_content: str,
) -> list[dict]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    system = PLANNER_PROMPT.format(current_datetime=now, tools_schema=tools_schema)
    messages = [{"role": "system", "content": system}]
    # Include recent history for context (last 10 messages)
    for msg in history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    # Ensure the latest user message is present
    if not messages or messages[-1].get("content") != user_content:
        messages.append({"role": "user", "content": user_content})
    return messages


def _parse_plan(text: str) -> dict:
    """Best-effort parse of planner output. Falls back to no-tool plan."""
    stripped = text.strip()
    # Try to extract JSON from markdown fences
    if "```" in stripped:
        for block in stripped.split("```"):
            block = block.strip()
            if block.startswith("json"):
                block = block[4:].strip()
            if block.startswith("{"):
                try:
                    return json.loads(block)
                except json.JSONDecodeError:
                    pass
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        logger.warning("planner_parse_failed", raw=stripped[:200])
        return {"thought": stripped, "tool_calls": []}


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def planner_node(state: AgentState, config: dict) -> dict:
    """Call LLM to generate a structured execution plan."""
    writer = get_stream_writer()
    provider: FallbackProvider = config["configurable"]["provider"]
    registry: ToolRegistry = config["configurable"]["registry"]
    tools_schema = registry.generate_schema()

    planner_messages = _build_planner_messages(
        tools_schema, state["messages"], state["user_content"]
    )

    # Write messages.sent event for replay
    writer(_make_event("messages.sent", {
        "call_index": 0,
        "messages": planner_messages,
    }))

    response = await provider.chat(planner_messages)
    plan = _parse_plan(response.content)
    raw_calls = plan.get("tool_calls", [])

    # Enrich each call with risk_level from the registry
    tool_calls = []
    for tc in raw_calls:
        tool = registry.get(tc.get("name", ""))
        risk = tool.risk_level if tool else "read"
        tool_calls.append({
            "name": tc.get("name", ""),
            "arguments": tc.get("arguments", {}),
            "parallel_group": tc.get("parallel_group", 0),
            "risk_level": risk,
        })

    logger.info("planner_done", thought=plan.get("thought", ""), n_tools=len(tool_calls))
    return {"plan": plan, "tool_calls": tool_calls}


async def executor_node(state: AgentState, config: dict) -> dict:
    """Execute planned tool calls with concurrency and interrupt for risky ops."""
    writer = get_stream_writer()
    registry: ToolRegistry = config["configurable"]["registry"]
    user_id: str = config["configurable"]["user_id"]
    tool_calls = state.get("tool_calls") or []

    if not tool_calls:
        return {"tool_results": []}

    # --- Interrupt for dangerous operations ---
    dangerous = [tc for tc in tool_calls if tc.get("risk_level") not in ("read", None)]
    if dangerous:
        # interrupt() pauses the graph; the value is surfaced to the caller.
        # When the user resumes, interrupt() returns the resume value.
        user_decision = interrupt({
            "type": "confirmation_required",
            "message": "以下操作需要确认后才能执行：",
            "pending_tools": [
                {"name": tc["name"], "arguments": tc["arguments"], "risk_level": tc["risk_level"]}
                for tc in dangerous
            ],
        })
        # If user explicitly rejected, skip dangerous tools
        if isinstance(user_decision, str) and user_decision.lower() in ("no", "cancel", "reject"):
            tool_calls = [tc for tc in tool_calls if tc.get("risk_level") in ("read", None)]
            if not tool_calls:
                return {"tool_results": [{"name": "user_cancelled", "ok": False,
                                          "result": {"message": "用户取消了操作"}}]}

    # --- Group by parallel_group and execute concurrently ---
    groups: dict[int, list[dict]] = {}
    for tc in tool_calls:
        g = tc.get("parallel_group", 0)
        groups.setdefault(g, []).append(tc)

    all_results: list[dict] = []
    step_index = 0

    for group_id in sorted(groups.keys()):
        group = groups[group_id]

        async def _execute_one(tc: dict, idx: int) -> dict:
            """Execute a single tool call with error handling."""
            name = tc["name"]
            args = tc["arguments"]

            # Emit tool.call event
            writer(_make_event("tool.call", {
                "name": name,
                "arguments": args,
                "risk_level": tc.get("risk_level", "read"),
                "step_index": idx,
            }))

            try:
                result = await asyncio.wait_for(
                    registry.execute(name, args, context={"user_id": user_id}),
                    timeout=60.0,  # per-tool timeout cap
                )
                ok = "error" not in result or result.get("code") is None
                entry = {"name": name, "result": result, "ok": ok}
            except asyncio.TimeoutError:
                entry = {"name": name, "ok": False,
                         "result": {"error": f"Tool '{name}' timed out after 60s"}}
                writer(_make_event("error", {"message": f"Tool '{name}' timed out"}))
            except Exception as exc:
                entry = {"name": name, "ok": False,
                         "result": {"error": f"{type(exc).__name__}: {exc}"}}
                writer(_make_event("error", {"message": str(exc)}))

            # Emit tool.result event
            writer(_make_event("tool.result", {
                "name": name,
                "result": entry["result"],
                "step_index": idx,
                "code": entry["result"].get("code"),
            }))
            return entry

        # Concurrent execution within the group
        tasks = [_execute_one(tc, step_index + i) for i, tc in enumerate(group)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, r in enumerate(results):
            if isinstance(r, Exception):
                tc = group[i]
                entry = {"name": tc["name"], "ok": False,
                         "result": {"error": str(r)}}
                all_results.append(entry)
            else:
                all_results.append(r)

        step_index += len(group)

    return {"tool_results": all_results}


async def synthesizer_node(state: AgentState, config: dict) -> dict:
    """Stream a final answer using tool results as context."""
    writer = get_stream_writer()
    provider: FallbackProvider = config["configurable"]["provider"]
    tool_results = state.get("tool_results") or []
    plan = state.get("plan") or {}

    # Build synthesis messages
    messages: list[dict] = []

    # System prompt for synthesis
    messages.append({
        "role": "system",
        "content": (
            "你是一个智能 AI 助手。下面是你通过工具获取到的信息，"
            "请根据这些数据用自然语言回复用户的问题。"
            "请用简洁、专业的方式回复，适当组织信息使其易于阅读。"
            "如果结果中包含来源链接（url），请在回复中引用这些来源，格式如：[来源标题](url)。"
        ),
    })

    # Include conversation history for context
    for msg in state["messages"][-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # If there are tool results, add them as context
    if tool_results:
        context_parts = []
        for tr in tool_results:
            status = "成功" if tr.get("ok") else "失败"
            context_parts.append(
                f"[工具: {tr['name']}] (状态: {status})\n"
                f"{json.dumps(tr['result'], ensure_ascii=False, indent=2)}"
            )
        context = "\n\n---\n\n".join(context_parts)
        messages.append({
            "role": "user",
            "content": f"以下是工具执行结果，请据此回答我之前的问题：\n\n{context}",
        })
    else:
        # No tools needed — just answer directly
        messages.append({"role": "user", "content": state["user_content"]})

    # Stream final answer
    full_text = ""
    async for chunk in provider.stream_chat(messages):
        if chunk.content:
            full_text += chunk.content
            writer(_make_event("text.delta", {"content": chunk.content}))

    return {"final_text": full_text}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

# Module-level cache for compiled graph
_compiled_graph = None


def build_graph(checkpointer: Any = None):
    """Build and compile the plan-execute-synthesize graph.

    Uses a module-level cache so the graph is compiled only once.
    The checkpointer enables checkpoint/resume across requests.
    """
    global _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph

    builder = StateGraph(AgentState)
    builder.add_node("planner", planner_node)
    builder.add_node("executor", executor_node)
    builder.add_node("synthesizer", synthesizer_node)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "executor")
    builder.add_edge("executor", "synthesizer")
    builder.add_edge("synthesizer", END)

    _compiled_graph = builder.compile(checkpointer=checkpointer)
    return _compiled_graph
