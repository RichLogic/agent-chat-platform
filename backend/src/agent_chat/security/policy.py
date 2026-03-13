"""PolicyEngine — decides ALLOW / DENY / CONFIRM for tool calls.

Default policy:
  - read          → ALLOW
  - write         → CONFIRM  (requires user confirmation)
  - destructive   → CONFIRM
  - admin         → DENY     (unless scopes match)

Tools can declare ``requires_confirmation = True`` to force CONFIRM
regardless of risk_level.

Tools can declare ``arg_redaction`` (list of argument keys) whose values
should be redacted in logs and approval events.

Tools can declare ``required_scopes`` — the user must have these scopes
for the tool to be allowed at all.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

import structlog

from agent_chat.tools.base import Tool

logger = structlog.get_logger()


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    CONFIRM = "confirm"


class PolicyResult:
    __slots__ = ("decision", "reason", "redacted_args")

    def __init__(
        self,
        decision: Decision,
        reason: str = "",
        redacted_args: dict[str, Any] | None = None,
    ) -> None:
        self.decision = decision
        self.reason = reason
        self.redacted_args = redacted_args


class PolicyEngine:
    """Evaluate whether a tool call should be allowed, denied, or require confirmation."""

    def evaluate(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        *,
        user_scopes: set[str] | None = None,
    ) -> PolicyResult:
        scopes = user_scopes or set()

        # 1. required_scopes check
        required = getattr(tool, "required_scopes", None) or set()
        if required:
            missing = set(required) - scopes
            if missing:
                return PolicyResult(
                    Decision.DENY,
                    f"Missing required scopes: {', '.join(sorted(missing))}",
                )

        # 2. Build redacted args
        redact_keys = getattr(tool, "arg_redaction", None) or []
        redacted = _redact_args(arguments, redact_keys) if redact_keys else arguments

        # 3. Explicit requires_confirmation
        if getattr(tool, "requires_confirmation", False):
            return PolicyResult(Decision.CONFIRM, "Tool requires confirmation", redacted)

        # 4. Risk-level based policy
        risk = tool.get_risk_level(arguments)

        if tool.name == "command":
            command = str(arguments.get("command", "")).strip()
            base = command.split()[0] if command.split() else ""
            if base in {"rm", "dd", "mkfs", "sudo"}:
                return PolicyResult(Decision.DENY, f"High-risk command denied: {base}", redacted)

        if risk == "read":
            return PolicyResult(Decision.ALLOW, "", redacted)

        if risk in ("write", "destructive"):
            return PolicyResult(
                Decision.CONFIRM,
                f"Write/destructive operation ({tool.name})",
                redacted,
            )

        if risk == "admin":
            return PolicyResult(
                Decision.DENY,
                f"Admin tool '{tool.name}' requires explicit scope authorization",
            )

        # Unknown risk level → deny by default
        return PolicyResult(Decision.DENY, f"Unknown risk_level: {risk}")


def _redact_args(args: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    """Return a copy of args with specified keys redacted."""
    redacted = dict(args)
    for key in keys:
        if key in redacted:
            redacted[key] = "***REDACTED***"
    return redacted


# Module-level singleton
_engine: PolicyEngine | None = None


def get_policy_engine() -> PolicyEngine:
    global _engine
    if _engine is None:
        _engine = PolicyEngine()
    return _engine
