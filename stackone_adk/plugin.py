"""StackOne Plugin for Google ADK.

Loads the actions available to a StackOne account and registers them as
native ADK tools.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from google.adk.plugins import BasePlugin
from google.adk.tools import BaseTool
from stackone_ai import ExecuteToolsConfig, StackOneError, StackOneToolSet

from stackone_adk.tools import StackOneAdkTool

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 180.0


class StackOnePlugin(BasePlugin):
    """Plugin that gives ADK agents StackOne's connectors and actions as tools.

    Lists the tools StackOne's MCP endpoint serves for your accounts and exposes
    each one as a native ADK tool. Authentication, account discovery and
    execution are handled by the StackOne AI SDK.

    With no ``account_id`` or ``account_ids``, the SDK uses every active shared
    account linked to the API key.

    Args:
        api_key: StackOne API key. Falls back to the STACKONE_API_KEY env var.
        account_id: Default account ID for all tools.
        base_url: API URL override. Falls back to the STACKONE_BASE_URL env var,
            then to https://api.stackone.com.
        plugin_name: Plugin identifier for ADK.
        providers: Filter by provider names (e.g., ["workday", "hibob"]).
        actions: Filter by action patterns with globs (e.g., ["*_list_*"]).
            Ignored in ``"search_and_execute"`` mode.
        account_ids: Scope tools to specific account IDs.
        mode: Tool registration strategy.
            ``None`` (default): one tool per action.
            ``"search_and_execute"``: ``stackone_search_actions`` and
            ``stackone_execute_action`` (with ``stackone_list_accounts`` for several accounts),
            spanning every account in scope, so the LLM finds and runs actions on
            demand. Keeps the model context small when many accounts or
            connectors are linked.
        execute: Execution configuration (e.g. account scoping), forwarded to
            ``StackOneToolSet``.
        timeout: Per-request timeout in seconds for listing and executing tools.
            Defaults to 180s; increase it for very slow connectors (e.g. some
            Workday endpoints).

    If the tools cannot be loaded (no usable account, or the API refuses the
    request), the plugin logs a warning and registers no tools.
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
        *,
        mode: Literal["search_and_execute"] | None = None,
        execute: ExecuteToolsConfig | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        super().__init__(name=plugin_name)

        resolved_api_key = api_key if api_key is not None else os.getenv("STACKONE_API_KEY", "")
        if not resolved_api_key:
            raise ValueError(
                "StackOne API key is required. Set the STACKONE_API_KEY environment "
                "variable or pass api_key=..."
            )

        search_and_execute = mode == "search_and_execute"
        if search_and_execute and actions:
            logger.warning(
                "`actions` is ignored in search_and_execute mode: the LLM's search query selects actions."
            )

        toolset = StackOneToolSet(
            api_key=resolved_api_key,
            account_id=account_id,
            base_url=base_url,
            execute=execute,
            timeout=timeout,
            tool_mode="search_execute" if search_and_execute else None,
        )
        self._tools = _load_tools(
            toolset,
            account_ids=account_ids,
            providers=providers,
            actions=None if search_and_execute else actions,
        )
        logger.info(f"StackOnePlugin initialized with {len(self._tools)} tools")

    def get_tools(self) -> list[BaseTool]:
        """Return pre-converted ADK tools."""
        return self._tools


def _load_tools(
    toolset: StackOneToolSet,
    *,
    account_ids: list[str] | None,
    providers: list[str] | None,
    actions: list[str] | None,
) -> list[BaseTool]:
    """The toolset's tools as ADK tools, or none, with a warning, when they cannot be loaded."""
    try:
        stackone_tools = toolset.fetch_tools(account_ids=account_ids, providers=providers, actions=actions)
    except StackOneError as e:
        logger.warning(f"Could not load StackOne tools, so none are available: {e}")
        return []

    tools: list[BaseTool] = []
    for tool in stackone_tools:
        try:
            tools.append(StackOneAdkTool(tool))
        except Exception as e:
            logger.warning(f"Failed to convert tool '{tool.name}': {e}")
    return tools
