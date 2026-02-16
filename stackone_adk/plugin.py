"""StackOne Plugin for Google ADK.

Provides dynamic tool discovery from 200+ SaaS providers via StackOne's
AI Integration Gateway, with lifecycle hooks for monitoring and customization.
"""

from __future__ import annotations

import base64
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
