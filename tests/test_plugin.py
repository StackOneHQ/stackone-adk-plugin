"""Tests for StackOne ADK plugin."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from stackone_ai import StackOneAPIError, ToolsetConfigError

from stackone_adk.plugin import StackOnePlugin
from stackone_adk.tools import StackOneAdkTool

PATCH_TOOLSET = "stackone_adk.plugin.StackOneToolSet"


def _mock_tool(name: str) -> MagicMock:
    tool = MagicMock()
    tool.name = name
    tool.description = f"{name} description"
    return tool


def _toolset_serving(*names: str) -> MagicMock:
    toolset = MagicMock()
    toolset.fetch_tools.return_value = [_mock_tool(name) for name in names]
    return toolset


class TestToolsetConstruction:
    @patch(PATCH_TOOLSET)
    def test_default_mode_lists_individual_tools(self, toolset_cls):
        toolset_cls.return_value = _toolset_serving()

        StackOnePlugin(api_key="sk-test", account_id="acct-1", base_url="https://custom.api.com")

        toolset_cls.assert_called_once_with(
            api_key="sk-test",
            account_id="acct-1",
            base_url="https://custom.api.com",
            execute=None,
            timeout=180.0,
            tool_mode=None,
        )

    @patch(PATCH_TOOLSET)
    def test_search_and_execute_mode_asks_for_the_search_execute_tool_mode(self, toolset_cls):
        toolset_cls.return_value = _toolset_serving()

        StackOnePlugin(
            api_key="sk-test",
            mode="search_and_execute",
            execute={"account_ids": ["acct-1"]},
            timeout=200,
        )

        kwargs = toolset_cls.call_args.kwargs
        assert kwargs["tool_mode"] == "search_execute"
        assert kwargs["execute"] == {"account_ids": ["acct-1"]}
        assert kwargs["timeout"] == 200

    @patch.dict("os.environ", {"STACKONE_API_KEY": "env-key"}, clear=True)
    @patch(PATCH_TOOLSET)
    def test_resolves_the_api_key_from_the_environment(self, toolset_cls):
        toolset_cls.return_value = _toolset_serving()

        StackOnePlugin()

        assert toolset_cls.call_args.kwargs["api_key"] == "env-key"

    def test_raises_without_an_api_key(self):
        with patch.dict("os.environ", {}, clear=True), pytest.raises(ValueError, match="API key is required"):
            StackOnePlugin()


class TestToolLoading:
    @patch(PATCH_TOOLSET)
    def test_passes_the_filters_to_fetch_tools(self, toolset_cls):
        toolset = toolset_cls.return_value = _toolset_serving()

        StackOnePlugin(
            api_key="sk-test",
            providers=["calendly"],
            actions=["*_list_*"],
            account_ids=["acct-1", "acct-2"],
        )

        toolset.fetch_tools.assert_called_once_with(
            account_ids=["acct-1", "acct-2"], providers=["calendly"], actions=["*_list_*"]
        )

    @patch(PATCH_TOOLSET)
    def test_wraps_every_tool_as_an_adk_tool(self, toolset_cls):
        toolset_cls.return_value = _toolset_serving("stackone_search_actions", "stackone_execute_action")

        tools = StackOnePlugin(api_key="sk-test", mode="search_and_execute").get_tools()

        assert [tool.name for tool in tools] == ["stackone_search_actions", "stackone_execute_action"]
        assert all(isinstance(tool, StackOneAdkTool) for tool in tools)

    @patch(PATCH_TOOLSET)
    def test_search_and_execute_mode_ignores_actions_with_a_warning(self, toolset_cls, caplog):
        toolset = toolset_cls.return_value = _toolset_serving()

        with caplog.at_level(logging.WARNING, logger="stackone_adk.plugin"):
            StackOnePlugin(
                api_key="sk-test", mode="search_and_execute", providers=["calendly"], actions=["*_list_*"]
            )

        toolset.fetch_tools.assert_called_once_with(account_ids=None, providers=["calendly"], actions=None)
        assert any("`actions` is ignored" in record.message for record in caplog.records)

    @pytest.mark.parametrize(
        "error",
        [
            ToolsetConfigError("None of this API key's 2 active account(s) are shared"),
            StackOneAPIError("Unauthorized", 401, None),
        ],
    )
    @patch(PATCH_TOOLSET)
    def test_registers_no_tools_with_a_warning_when_loading_fails(self, toolset_cls, error, caplog):
        toolset_cls.return_value.fetch_tools.side_effect = error

        with caplog.at_level(logging.WARNING, logger="stackone_adk.plugin"):
            plugin = StackOnePlugin(api_key="sk-test")

        assert plugin.get_tools() == []
        assert any("Could not load StackOne tools" in record.message for record in caplog.records)

    @patch("stackone_adk.plugin.StackOneAdkTool")
    @patch(PATCH_TOOLSET)
    def test_skips_a_tool_that_fails_to_convert(self, toolset_cls, adk_tool_cls):
        toolset_cls.return_value = _toolset_serving("good_tool", "bad_tool")
        good = MagicMock()
        good.name = "good_tool"
        adk_tool_cls.side_effect = [good, ValueError("broken")]

        tools = StackOnePlugin(api_key="sk-test").get_tools()

        assert tools == [good]

    @patch(PATCH_TOOLSET)
    def test_custom_plugin_name(self, toolset_cls):
        toolset_cls.return_value = _toolset_serving()

        assert StackOnePlugin(api_key="sk-test", plugin_name="my_plugin").name == "my_plugin"
