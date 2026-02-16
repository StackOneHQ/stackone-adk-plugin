"""StackOne Plugin for Google ADK.

Provides dynamic tool discovery from 200+ SaaS providers via StackOne's
AI Integration Gateway, with lifecycle hooks for monitoring and customization.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

import httpx
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.plugins import BasePlugin
from google.adk.tools import BaseTool, ToolContext
from google.genai import types
from stackone_ai import StackOneToolSet
from stackone_ai.models import ExecuteConfig, StackOneTool, ToolParameters
from stackone_ai.utility_tools import ToolIndex

from stackone_adk.tools import StackOneAdkTool

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.stackone.com"


def _discover_account_ids(
    api_key: str,
    base_url: str,
    providers: list[str] | None = None,
) -> list[str]:
    """Auto-discover connected account IDs from the StackOne API.

    Args:
        api_key: StackOne API key.
        base_url: StackOne API base URL.
        providers: Optional provider filter (case-insensitive).

    Returns:
        List of account IDs.
    """
    token = base64.b64encode(f"{api_key}:".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    resp = httpx.get(f"{base_url.rstrip('/')}/accounts", headers=headers)
    resp.raise_for_status()

    body = resp.json()
    accounts = body.get("data", body) if isinstance(body, dict) else body
    if providers:
        provider_set = {p.lower() for p in providers}
        accounts = [a for a in accounts if a.get("provider", "").lower() in provider_set]

    return [a["id"] for a in accounts if a.get("id")]


def _build_utility_tools(tools: Any) -> list[StackOneTool]:
    """Build enhanced utility tools that include parameter schemas in search results.

    The SDK's default tool_search returns {name, description, score} but not the
    parameter schema. Without the schema, the agent guesses parameter names from
    the description, which leads to 400 errors on execution.

    This version includes parameters in the search results so the agent can
    construct correct tool_execute calls.
    """
    tool_list = list(tools)
    tool_map = {t.name: t for t in tool_list}
    index = ToolIndex(tool_list)

    # --- tool_search (enhanced with parameter schemas) ---

    def execute_search(arguments: str | dict[str, Any] | None = None) -> dict[str, Any]:
        if isinstance(arguments, str):
            kwargs = json.loads(arguments)
        else:
            kwargs = arguments or {}
        query = kwargs.get("query", "")
        limit = int(kwargs["limit"]) if kwargs.get("limit") is not None else 5
        min_score = float(kwargs["minScore"]) if kwargs.get("minScore") is not None else 0.0

        results = index.search(query, limit, min_score)
        tools_data = []
        for r in results:
            tool = tool_map.get(r.name)
            entry: dict[str, Any] = {
                "name": r.name,
                "description": r.description,
                "score": r.score,
            }
            if tool and tool.parameters.properties:
                entry["parameters"] = tool.parameters.properties
            tools_data.append(entry)
        return {"tools": tools_data}

    class EnhancedToolSearch(StackOneTool):
        def __init__(self) -> None:
            super().__init__(
                description=(
                    "Searches for relevant tools based on a natural language query. "
                    "Returns tool names, descriptions, relevance scores, and parameter "
                    "schemas. Call this first to discover available tools before executing them."
                ),
                parameters=ToolParameters(
                    type="object",
                    properties={
                        "query": {
                            "type": "string",
                            "description": (
                                "Natural language query describing what tools you need "
                                '(e.g., "list events", "get current user")'
                            ),
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of tools to return (default: 5)",
                            "nullable": True,
                        },
                        "minScore": {
                            "type": "number",
                            "description": "Minimum relevance score 0-1 (default: 0.0)",
                            "nullable": True,
                        },
                    },
                ),
                _execute_config=ExecuteConfig(name="tool_search", method="POST", url="", headers={}),
                _api_key="",
                _account_id=None,
            )

        def execute(
            self,
            arguments: str | dict[str, Any] | None = None,
            *,
            options: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return execute_search(arguments)

    # --- tool_execute (reuse SDK's version) ---
    from stackone_ai.models import Tools as ToolsCollection
    from stackone_ai.utility_tools import create_tool_execute

    tools_collection = ToolsCollection(tool_list)
    execute_tool = create_tool_execute(tools_collection)

    return [EnhancedToolSearch(), execute_tool]


class StackOnePlugin(BasePlugin):
    """Plugin for connecting ADK agents to 200+ SaaS providers via StackOne.

    Dynamically discovers tools from StackOne's MCP endpoint and exposes them
    as native ADK tools. All authentication, RPC execution, and HTTP calls
    are handled by the StackOne AI SDK.

    When no account_id or account_ids are provided, the plugin automatically
    discovers connected accounts from the StackOne API.

    Args:
        api_key: StackOne API key. Falls back to STACKONE_API_KEY env var.
        account_id: Default account ID for all tools.
        base_url: API URL override (default: https://api.stackone.com).
        plugin_name: Plugin identifier for ADK.
        providers: Filter by provider names (e.g., ["calendly", "hibob"]).
        actions: Filter by action patterns with globs (e.g., ["*_list_*"]).
        account_ids: Scope tools to specific account IDs.
        use_utility_tools: When True, expose only tool_search and tool_execute
            instead of all provider tools. The agent uses tool_search to discover
            relevant tools via keyword search, then tool_execute to run them.
    """

    def __init__(
        self,
        api_key: str | None = None,
        account_id: str | None = None,
        base_url: str | None = None,
        plugin_name: str = "stackone_plugin",
        providers: list[str] | None = None,
        actions: list[str] | None = None,
        account_ids: list[str] | None = None,
        use_utility_tools: bool = False,
    ) -> None:
        super().__init__(name=plugin_name)

        resolved_api_key = api_key if api_key is not None else os.getenv("STACKONE_API_KEY", "")
        resolved_base_url = base_url or DEFAULT_BASE_URL

        # Auto-discover account IDs if none provided
        if not account_id and not account_ids:
            account_ids = _discover_account_ids(resolved_api_key, resolved_base_url, providers)
            logger.info(f"Auto-discovered {len(account_ids)} account(s)")

        self._tools: list[BaseTool] = []

        if not account_id and not account_ids:
            logger.warning("No connected accounts found. No tools will be available.")
            return

        self._toolset = StackOneToolSet(
            api_key=api_key,
            account_id=account_id,
            base_url=base_url,
        )

        stackone_tools = self._toolset.fetch_tools(
            account_ids=account_ids,
            providers=providers,
            actions=actions,
        )

        if use_utility_tools:
            for tool in _build_utility_tools(stackone_tools):
                try:
                    self._tools.append(StackOneAdkTool(tool))
                except Exception as e:
                    logger.warning(f"Failed to convert utility tool '{tool.name}': {e}")
            logger.info(f"StackOnePlugin initialized with {len(self._tools)} utility tools")
        else:
            for tool in stackone_tools:
                try:
                    self._tools.append(StackOneAdkTool(tool))
                except Exception as e:
                    logger.warning(f"Failed to convert tool '{tool.name}': {e}")
            logger.info(f"StackOnePlugin initialized with {len(self._tools)} tools")

    def get_tools(self) -> list[BaseTool]:
        """Return pre-converted ADK tools."""
        return self._tools

    async def before_agent_callback(
        self,
        *,
        agent: BaseAgent,
        callback_context: CallbackContext,
    ) -> types.Content | None:
        """Called before the agent starts processing."""
        return None

    async def after_agent_callback(
        self,
        *,
        agent: BaseAgent,
        callback_context: CallbackContext,
    ) -> types.Content | None:
        """Called after the agent finishes processing."""
        return None

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict[str, Any] | None:
        """Called before a tool is executed."""
        logger.debug(f"Before tool: {tool.name}")
        return None

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Called after a tool is executed."""
        logger.debug(f"After tool: {tool.name}")
        if isinstance(result, dict) and "error" in result:
            logger.warning(f"Tool {tool.name} returned error: {result['error']}")
        return None

    async def on_tool_error_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        error: Exception,
    ) -> dict[str, Any] | None:
        """Called when a tool raises an uncaught exception."""
        logger.error(f"Tool {tool.name} raised uncaught exception: {error}")
        return None

    async def close(self) -> None:
        """Clean up plugin resources.

        StackOneToolSet is stateless HTTP — each execute() is an
        independent request — so no cleanup is needed.
        """
        logger.debug("StackOnePlugin closed")
