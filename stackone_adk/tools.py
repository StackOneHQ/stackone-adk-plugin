"""StackOne tool adapter for Google ADK.

Converts the tools StackOne serves into ADK-compatible BaseTool instances.
Handles the JSON Schema declaration and sync-to-async bridging.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from google.adk.tools import BaseTool, ToolContext
from google.genai import types
from stackone_ai import StackOneAPIError, StackOneTool

logger = logging.getLogger(__name__)


class StackOneAdkTool(BaseTool):
    """Adapter that wraps a StackOneTool as an ADK BaseTool.

    Declares the tool with the JSON Schema StackOne served and bridges the
    synchronous execute() method to async run_async().
    """

    def __init__(self, stackone_tool: StackOneTool) -> None:
        super().__init__(
            name=stackone_tool.name,
            description=stackone_tool.description,
        )
        self._stackone_tool = stackone_tool

    def _get_declaration(self) -> types.FunctionDeclaration:
        """Declare the tool with its served JSON Schema.

        Uses ADK's native ``parameters_json_schema``, which accepts a raw JSON
        Schema dict, as ADK's own McpTool does. The schema is the SDK's OpenAI
        form of it: the served properties and ``required`` list, verbatim.
        """
        schema = self._stackone_tool.to_openai_function()["function"]["parameters"]

        if not schema.get("properties"):
            return types.FunctionDeclaration(
                name=self.name,
                description=self.description,
            )

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

        Runs the synchronous StackOneTool.execute() in a worker thread to avoid
        blocking the event loop. Returns the server's result as it wrote it: for
        an action, ``{"isError": False, "result": ..., ...}``.
        """
        try:
            return await asyncio.to_thread(self._stackone_tool.execute, args)
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
