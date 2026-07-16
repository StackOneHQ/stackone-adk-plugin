"""StackOne Plugin for Google ADK.

Provides dynamic tool discovery from 200+ SaaS providers via StackOne's
AI Integration Gateway, with lifecycle hooks for monitoring and customization.
"""

from __future__ import annotations

import base64
import logging
import os
from importlib import metadata
from typing import Literal

import httpx
from google.adk.plugins import BasePlugin
from google.adk.tools import BaseTool
from stackone_ai import ExecuteToolsConfig, SearchConfig, StackOneToolSet

from stackone_adk.tools import StackOneAdkTool

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.stackone.com"
DEFAULT_TIMEOUT = 180.0

try:
    _PLUGIN_VERSION = metadata.version("stackone-adk")
except metadata.PackageNotFoundError:  # pragma: no cover
    _PLUGIN_VERSION = "dev"
_USER_AGENT = f"stackone-adk-plugin/{_PLUGIN_VERSION}"


def _discover_account_ids(
    api_key: str,
    base_url: str,
    providers: list[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[str]:
    """Auto-discover connected account IDs from the StackOne API.

    Args:
        api_key: StackOne API key.
        base_url: StackOne API base URL.
        providers: Optional provider filter (case-insensitive).
        timeout: HTTP timeout in seconds.

    Returns:
        List of account IDs.
    """
    token = base64.b64encode(f"{api_key}:".encode()).decode()
    headers = {
        "Authorization": f"Basic {token}",
        "User-Agent": _USER_AGENT,
    }
    resp = httpx.get(f"{base_url.rstrip('/')}/accounts", headers=headers, timeout=timeout)
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
        providers: Filter by provider names (e.g., ["workday", "hibob"]).
        actions: Filter by action patterns with globs (e.g., ["*_list_*"]).
        account_ids: Scope tools to specific account IDs.
        mode: Tool registration strategy.
            ``None`` (default): expose every discovered tool to the agent.
            ``"search_and_execute"``: expose just two meta tools — ``tool_search``
            and ``tool_execute`` — letting the LLM discover and invoke tools
            on demand. Keeps the model context small when many accounts/connectors
            are linked.
        search: Search backend configuration. Forwarded to ``StackOneToolSet``
            unconditionally; takes effect only when ``mode="search_and_execute"``.
            Defaults to ``{"method": "auto"}`` in that mode if not specified.
        execute: Execution configuration (e.g. account scoping). Forwarded to
            ``StackOneToolSet`` unconditionally; takes effect only when
            ``mode="search_and_execute"``.
        timeout: Per-request timeout in seconds for HTTP calls (account
            discovery and tool execution). Defaults to 180s — increase further
            for very slow connectors (e.g. some Workday endpoints).
        feedback: Whether to expose the global ``submit_feedback`` tool, which the
            StackOne MCP server provides on every account. Enabled by default in both
            modes; set to ``False`` to omit it.
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
        search: SearchConfig | None = None,
        execute: ExecuteToolsConfig | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        feedback: bool = True,
    ) -> None:
        super().__init__(name=plugin_name)

        resolved_api_key = api_key if api_key is not None else os.getenv("STACKONE_API_KEY", "")
        if not resolved_api_key:
            raise ValueError(
                "StackOne API key is required. Set the STACKONE_API_KEY environment variable or pass api_key=..."
            )
        resolved_base_url = base_url or DEFAULT_BASE_URL

        if not account_id and not account_ids:
            try:
                account_ids = _discover_account_ids(
                    resolved_api_key, resolved_base_url, providers, timeout=timeout
                )
                logger.info(f"Auto-discovered {len(account_ids)} account(s)")
            except Exception as e:
                logger.warning(f"Auto-discovery failed: {e}")
                account_ids = []

        self._tools: list[BaseTool] = []
        self._toolset: StackOneToolSet | None = None

        if not account_id and not account_ids:
            logger.warning("No connected accounts found. No tools will be available.")
            return

        effective_search: SearchConfig | None = search
        if effective_search is None and mode == "search_and_execute":
            effective_search = {"method": "auto"}

        self._toolset = StackOneToolSet(
            api_key=resolved_api_key,
            account_id=account_id,
            base_url=resolved_base_url,
            search=effective_search,
            execute=execute,
            timeout=timeout,
        )

        if mode == "search_and_execute":
            if actions or providers:
                logger.warning(
                    "`actions` is ignored in search_and_execute mode. `providers` may "
                    "still scope auto-discovery but does not filter the tool catalog "
                    "(the LLM's search query handles that)."
                )
            # Use SDK's internal builder until a public API is exposed.
            meta_tools = self._toolset._build_tools(account_ids=account_ids, feedback=feedback)
            for tool in meta_tools:
                self._tools.append(StackOneAdkTool(tool))
        else:
            stackone_tools = self._toolset.fetch_tools(
                account_ids=account_ids,
                providers=providers,
                actions=actions,
                feedback=feedback,
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
