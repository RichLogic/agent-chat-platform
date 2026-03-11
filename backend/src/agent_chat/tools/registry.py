"""Tool registry — manages available tools, generates schemas, executes tools."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import jsonschema
import structlog

from agent_chat.tools.base import Tool

logger = structlog.get_logger()

class CommandExecutionError(RuntimeError):
    """Raised when command executor rejects or fails a command."""


@dataclass(slots=True)
class ExecutionRequest:
    command: str
    tool_name: str
    risk_level: str
    context: dict[str, Any] | None = None


@dataclass(slots=True)
class ExecutionResult:
    ok: bool
    code: str
    message: str


class Executor:
    """Executor interface for local/sandbox command execution."""

    async def run(self, request: ExecutionRequest) -> ExecutionResult:
        raise NotImplementedError


class LocalExecutor(Executor):
    """Local executor placeholder (no isolation)."""

    async def run(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(ok=True, code="LOCAL_OK", message="Executed by local executor")


class SandboxExecutor(Executor):
    """Sandbox executor placeholder for future isolated runtime integration."""

    async def run(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(
            ok=False,
            code="SANDBOX_NOT_IMPLEMENTED",
            message="Sandbox backend is not configured yet",
        )


class ApprovalHook:
    """Approval hook interface used by executor guardrails."""

    async def approve(self, request: ExecutionRequest) -> bool:
        raise NotImplementedError


class AllowAllApprovalHook(ApprovalHook):
    async def approve(self, request: ExecutionRequest) -> bool:
        return True


class ExecutionGuard:
    """Minimal command policy guard using allow/deny list and approval hook."""

    def __init__(
        self,
        *,
        allowlist: set[str] | None = None,
        denylist: set[str] | None = None,
        approval_hook: ApprovalHook | None = None,
        needs_approval: set[str] | None = None,
    ) -> None:
        self.allowlist = allowlist or set()
        self.denylist = denylist or set()
        self.approval_hook = approval_hook or AllowAllApprovalHook()
        self.needs_approval = needs_approval or {"write", "destructive", "admin"}

    async def validate(self, request: ExecutionRequest) -> ExecutionResult:
        cmd = request.command.strip()
        if not cmd:
            return ExecutionResult(ok=False, code="EMPTY_COMMAND", message="empty command")

        base = cmd.split()[0]
        if base in self.denylist:
            return ExecutionResult(ok=False, code="DENYLIST_BLOCKED", message=f"command denied: {base}")

        if self.allowlist and base not in self.allowlist:
            return ExecutionResult(ok=False, code="NOT_IN_ALLOWLIST", message=f"command not allowlisted: {base}")

        if request.risk_level in self.needs_approval:
            approved = await self.approval_hook.approve(request)
            if not approved:
                return ExecutionResult(ok=False, code="APPROVAL_REQUIRED", message="command not approved")

        return ExecutionResult(ok=True, code="ALLOWED", message="allowed")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._executor: Executor = LocalExecutor()
        self._guard = ExecutionGuard(denylist={"rm", "sudo", "mkfs", "dd"})

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def set_executor(self, executor: Executor) -> None:
        self._executor = executor

    def set_execution_guard(self, guard: ExecutionGuard) -> None:
        self._guard = guard

    def generate_schema(self) -> str:
        """Generate a JSON string describing all registered tools for prompt injection."""
        tools = []
        for tool in self._tools.values():
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "risk_level": tool.risk_level,
            })
        return json.dumps(tools, ensure_ascii=False, indent=2)

    async def execute(
        self, name: str, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Unknown tool: {name}", "code": "UNKNOWN_TOOL"}

        # --- Schema validation ---
        try:
            jsonschema.validate(instance=arguments, schema=tool.parameters)
        except jsonschema.ValidationError as exc:
            return {"error": exc.message, "code": "INVALID_PARAMS"}

        # --- Optional command guard / executor hook ---
        command = arguments.get("command")
        if isinstance(command, str):
            request = ExecutionRequest(
                command=command,
                tool_name=name,
                risk_level=getattr(tool, "risk_level", "read"),
                context=context,
            )
            guard_result = await self._guard.validate(request)
            if not guard_result.ok:
                return {"error": guard_result.message, "code": guard_result.code}

            exec_result = await self._executor.run(request)
            if not exec_result.ok:
                return {"error": exec_result.message, "code": exec_result.code}

        # --- Execute with timeout + retry ---
        attempts = 1 + tool.max_retries
        last_error: str = ""
        for attempt in range(1, attempts + 1):
            try:
                result = await asyncio.wait_for(
                    tool.execute(arguments, context),
                    timeout=tool.timeout_seconds,
                )
                if isinstance(result, dict):
                    result.setdefault("_meta", {})
                    result["_meta"].setdefault("attempts", attempt)
                return result
            except asyncio.TimeoutError:
                last_error = (
                    f"Tool '{name}' timed out after {tool.timeout_seconds}s"
                )
                logger.warning(
                    "tool_timeout",
                    tool=name,
                    attempt=attempt,
                    timeout=tool.timeout_seconds,
                )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "tool_execution_error",
                    tool=name,
                    attempt=attempt,
                    error=last_error,
                )

            if attempt < attempts:
                await asyncio.sleep(min(2 ** (attempt - 1), 4))

        # All attempts exhausted
        code = "TIMEOUT" if "timed out" in last_error else "EXECUTION_ERROR"
        return {"error": last_error, "code": code, "_meta": {"attempts": attempts}}


_registry: ToolRegistry | None = None


async def get_registry() -> ToolRegistry:
    """Get or create the global tool registry with all tools registered."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        await _register_all_tools(_registry)
        try:
            from agent_chat.config import get_settings
            settings = get_settings()
            deny = set(settings.command_denylist or [])
            allow = set(settings.command_allowlist or [])
            _registry.set_execution_guard(ExecutionGuard(allowlist=allow, denylist=deny))
            if settings.executor_mode == "sandbox":
                _registry.set_executor(SandboxExecutor())
        except Exception as e:
            logger.debug("executor_guard_setup_skipped", reason=str(e))
    return _registry


async def refresh_mcp_tools() -> int:
    """Re-discover MCP tools and register them. Returns count of newly registered tools."""
    registry = await get_registry()
    try:
        from agent_chat.config import get_settings
        settings = get_settings()
        if not settings.mcp_notes_url:
            return 0
        from agent_chat.tools.mcp_adapter import discover_and_register_mcp_tools
        count = await discover_and_register_mcp_tools(registry, settings.mcp_notes_url)
        logger.info("mcp_tools_refreshed", count=count, url=settings.mcp_notes_url)
        return count
    except Exception as e:
        logger.error("mcp_refresh_failed", error=str(e))
        raise


async def _register_all_tools(registry: ToolRegistry) -> None:
    from agent_chat.tools.weather import WeatherTool
    from agent_chat.tools.news import NewsTool
    from agent_chat.tools.search import SearchTool
    from agent_chat.tools.read_pdf import ReadPdfTool
    from agent_chat.tools.search_memory import SearchMemoryTool
    from agent_chat.tools.kb_search import KBSearchTool
    from agent_chat.tools.ingest_webpage import IngestWebpageTool
    from agent_chat.tools.web_fetch import WebFetchTool
    registry.register(WeatherTool())
    registry.register(NewsTool())
    registry.register(SearchTool())
    registry.register(ReadPdfTool())
    registry.register(SearchMemoryTool())
    registry.register(KBSearchTool())
    registry.register(IngestWebpageTool())
    registry.register(WebFetchTool())

    # MCP tool discovery (optional, non-blocking)
    try:
        from agent_chat.config import get_settings
        settings = get_settings()
        if settings.mcp_notes_url:
            from agent_chat.tools.mcp_adapter import discover_and_register_mcp_tools
            count = await discover_and_register_mcp_tools(registry, settings.mcp_notes_url)
            logger.info("mcp_tools_discovered", count=count, url=settings.mcp_notes_url)
    except Exception as e:
        logger.debug("mcp_tools_skipped", reason=str(e))
