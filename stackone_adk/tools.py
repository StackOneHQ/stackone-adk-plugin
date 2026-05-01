"""StackOne tool adapter for Google ADK.

Converts StackOne's dynamically-discovered tools into ADK-compatible BaseTool instances.
Handles JSON Schema to FunctionDeclaration conversion and sync-to-async bridging.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from google.adk.tools import BaseTool, ToolContext
from google.genai import types
from stackone_ai.models import StackOneAPIError, StackOneTool

logger = logging.getLogger(__name__)


class StackOneAdkTool(BaseTool):
    """Adapter that wraps a StackOneTool as an ADK BaseTool.

    Converts StackOne's JSON Schema parameters to ADK FunctionDeclarations
    and bridges the synchronous execute() method to async run_async().
    """

    def __init__(self, stackone_tool: StackOneTool) -> None:
        super().__init__(
            name=stackone_tool.name,
            description=stackone_tool.description,
        )
        self._stackone_tool = stackone_tool

    def _get_declaration(self) -> types.FunctionDeclaration:
        """Convert StackOne tool parameters to an ADK FunctionDeclaration.

        Uses ADK's native ``parameters_json_schema`` which accepts raw
        JSON Schema dicts directly, matching how ADK's own McpTool works.
        """
        properties = self._stackone_tool.parameters.properties

        if not properties:
            return types.FunctionDeclaration(
                name=self.name,
                description=self.description,
            )

        schema = self._stackone_tool.parameters.model_dump()
        required = [
            name
            for name, prop in properties.items()
            if isinstance(prop, dict) and not prop.get("nullable", False)
        ]
        if required:
            schema["required"] = required

        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=schema,
        )

    async def run_async(
        self,
        *,
        args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Execute the StackOne tool asynchronously.

        Runs the synchronous StackOneTool.execute() in a thread pool
        to avoid blocking the event loop.
        """
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, self._stackone_tool.execute, args)
            if isinstance(result, dict):
                return result
            return {"result": result}
        except StackOneAPIError as exc:
            logger.exception("Tool %s API error", self.name)
            return {
                "error": str(exc),
                "status_code": exc.status_code,
                "response_body": exc.response_body,
                "tool_name": self.name,
            }
        except Exception as e:
            logger.exception("Tool %s execution failed", self.name)
            return {"error": str(e), "tool_name": self.name}
