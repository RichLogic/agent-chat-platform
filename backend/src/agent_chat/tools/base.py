"""Base class for tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal


class Tool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]
    risk_level: Literal["read", "write", "admin"] = "read"
    timeout_seconds: float = 30.0
    max_retries: int = 0

    @abstractmethod
    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute the tool and return results."""
