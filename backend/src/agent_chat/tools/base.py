"""Base class for tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]

    @abstractmethod
    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute the tool and return results."""
