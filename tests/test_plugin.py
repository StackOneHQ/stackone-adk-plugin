"""Tests for StackOne ADK plugin."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from stackone_adk.plugin import StackOnePlugin, _discover_account_ids
from stackone_adk.tools import StackOneAdkTool


def _make_mock_stackone_tool(name: str = "test_tool", description: str = "A test tool") -> MagicMock:
    """Create a mock StackOneTool."""
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.parameters = MagicMock()
    tool.parameters.properties = {"field": {"type": "string", "nullable": True}}
    return tool


def _make_mock_tools(count: int = 3) -> MagicMock:
    """Create a mock Tools collection that is iterable."""
    tools_list = [_make_mock_stackone_tool(name=f"tool_{i}", description=f"Tool {i}") for i in range(count)]
    mock_tools = MagicMock()
    mock_tools.__iter__ = MagicMock(return_value=iter(tools_list))
    return mock_tools


# Patch both StackOneToolSet and _discover_account_ids for all init tests
PLUGIN_PATCH_TOOLSET = "stackone_adk.plugin.StackOneToolSet"
PLUGIN_PATCH_DISCOVER = "stackone_adk.plugin._discover_account_ids"


class TestDiscoverAccountIds:
    @patch("stackone_adk.plugin.httpx")
    def test_returns_all_account_ids(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
                {"id": "acct-1", "provider": "calendly"},
                {"id": "acct-2", "provider": "hibob"},
            ]
        mock_httpx.get.return_value = mock_resp

        result = _discover_account_ids("sk-test", "https://api.stackone.com")
        assert result == ["acct-1", "acct-2"]

    @patch("stackone_adk.plugin.httpx")
    def test_filters_by_provider(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
                {"id": "acct-1", "provider": "calendly"},
                {"id": "acct-2", "provider": "hibob"},
                {"id": "acct-3", "provider": "calendly"},
            ]
        mock_httpx.get.return_value = mock_resp

        result = _discover_account_ids("sk-test", "https://api.stackone.com", providers=["calendly"])
        assert result == ["acct-1", "acct-3"]

    @patch("stackone_adk.plugin.httpx")
    def test_provider_filter_case_insensitive(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": "acct-1", "provider": "Calendly"}]
        mock_httpx.get.return_value = mock_resp

        result = _discover_account_ids("sk-test", "https://api.stackone.com", providers=["CALENDLY"])
        assert result == ["acct-1"]

    @patch("stackone_adk.plugin.httpx")
    def test_skips_accounts_without_id(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
                {"id": "acct-1", "provider": "calendly"},
                {"provider": "hibob"},
                {"id": "", "provider": "bamboohr"},
            ]
        mock_httpx.get.return_value = mock_resp

        result = _discover_account_ids("sk-test", "https://api.stackone.com")
        assert result == ["acct-1"]

    @patch("stackone_adk.plugin.httpx")
    def test_empty_accounts(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_httpx.get.return_value = mock_resp

        result = _discover_account_ids("sk-test", "https://api.stackone.com")
        assert result == []


class TestStackOnePluginInit:
    @patch(PLUGIN_PATCH_DISCOVER, return_value=["acct-auto"])
    @patch(PLUGIN_PATCH_TOOLSET)
    def test_default_init_auto_discovers(self, mock_toolset_cls, mock_discover):
        mock_toolset = MagicMock()
        mock_toolset.fetch_tools.return_value = _make_mock_tools(2)
        mock_toolset_cls.return_value = mock_toolset

        plugin = StackOnePlugin(api_key="sk-test")

        # Auto-discovery should have been called
        mock_discover.assert_called_once()
        # fetch_tools should receive the auto-discovered account_ids
        mock_toolset.fetch_tools.assert_called_once_with(
            account_ids=["acct-auto"], providers=None, actions=None
        )
        assert len(plugin.get_tools()) == 2
        assert plugin.name == "stackone_plugin"

    @patch(PLUGIN_PATCH_DISCOVER, return_value=["acct-auto"])
    @patch(PLUGIN_PATCH_TOOLSET)
    def test_custom_plugin_name(self, mock_toolset_cls, mock_discover):
        mock_toolset = MagicMock()
        mock_toolset.fetch_tools.return_value = _make_mock_tools(0)
        mock_toolset_cls.return_value = mock_toolset

        plugin = StackOnePlugin(api_key="sk-test", plugin_name="my_plugin")
        assert plugin.name == "my_plugin"

    @patch(PLUGIN_PATCH_DISCOVER)
    @patch(PLUGIN_PATCH_TOOLSET)
    def test_skips_discovery_when_account_id_provided(self, mock_toolset_cls, mock_discover):
        mock_toolset = MagicMock()
        mock_toolset.fetch_tools.return_value = _make_mock_tools(0)
        mock_toolset_cls.return_value = mock_toolset

        StackOnePlugin(api_key="sk-test", account_id="acct-123", base_url="https://custom.api.com")

        # Auto-discovery should NOT be called when account_id is provided
        mock_discover.assert_not_called()
        mock_toolset_cls.assert_called_once_with(
            api_key="sk-test",
            account_id="acct-123",
            base_url="https://custom.api.com",
        )

    @patch(PLUGIN_PATCH_DISCOVER)
    @patch(PLUGIN_PATCH_TOOLSET)
    def test_skips_discovery_when_account_ids_provided(self, mock_toolset_cls, mock_discover):
        mock_toolset = MagicMock()
        mock_toolset.fetch_tools.return_value = _make_mock_tools(0)
        mock_toolset_cls.return_value = mock_toolset

        StackOnePlugin(
            api_key="sk-test",
            providers=["calendly"],
            actions=["*_list_*"],
            account_ids=["acct-1", "acct-2"],
        )

        mock_discover.assert_not_called()
        mock_toolset.fetch_tools.assert_called_once_with(
            account_ids=["acct-1", "acct-2"],
            providers=["calendly"],
            actions=["*_list_*"],
        )

    @patch(PLUGIN_PATCH_DISCOVER, return_value=["acct-auto"])
    @patch(PLUGIN_PATCH_TOOLSET)
    def test_passes_providers_to_discovery(self, mock_toolset_cls, mock_discover):
        mock_toolset = MagicMock()
        mock_toolset.fetch_tools.return_value = _make_mock_tools(0)
        mock_toolset_cls.return_value = mock_toolset

        StackOnePlugin(api_key="sk-test", providers=["calendly"])

        mock_discover.assert_called_once_with("sk-test", "https://api.stackone.com", ["calendly"])

    @patch(PLUGIN_PATCH_DISCOVER, return_value=["acct-auto"])
    @patch(PLUGIN_PATCH_TOOLSET)
    def test_tools_converted_to_adk_tools(self, mock_toolset_cls, mock_discover):
        mock_toolset = MagicMock()
        mock_toolset.fetch_tools.return_value = _make_mock_tools(3)
        mock_toolset_cls.return_value = mock_toolset

        plugin = StackOnePlugin(api_key="sk-test")
        tools = plugin.get_tools()

        assert len(tools) == 3
        for tool in tools:
            assert isinstance(tool, StackOneAdkTool)

    @patch("stackone_adk.plugin.StackOneAdkTool")
    @patch(PLUGIN_PATCH_DISCOVER, return_value=["acct-auto"])
    @patch(PLUGIN_PATCH_TOOLSET)
    def test_failed_conversion_skipped(self, mock_toolset_cls, mock_discover, mock_adk_tool_cls):
        mock_toolset = MagicMock()

        good_tool = _make_mock_stackone_tool(name="good_tool")
        bad_tool = _make_mock_stackone_tool(name="bad_tool")

        tools_list = [good_tool, bad_tool]
        mock_tools = MagicMock()
        mock_tools.__iter__ = MagicMock(return_value=iter(tools_list))
        mock_toolset.fetch_tools.return_value = mock_tools
        mock_toolset_cls.return_value = mock_toolset

        # Make StackOneAdkTool succeed for good_tool, raise for bad_tool
        good_adk_tool = MagicMock()
        good_adk_tool.name = "good_tool"
        mock_adk_tool_cls.side_effect = [good_adk_tool, ValueError("broken")]

        plugin = StackOnePlugin(api_key="sk-test")
        assert len(plugin.get_tools()) == 1
        assert plugin.get_tools()[0].name == "good_tool"
