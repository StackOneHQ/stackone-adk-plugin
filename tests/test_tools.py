"""Tests for StackOne ADK tool adapter."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest
from stackone_ai import ExecuteConfig, StackOneAPIError, StackOneTool, ToolParameters

from stackone_adk.tools import StackOneAdkTool

# --- Helpers ---


def _served_tool(
    name: str = "test_tool",
    description: str = "A test tool",
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> StackOneTool:
    """A real StackOneTool carrying a served schema, as fetch_tools() builds one."""
    return StackOneTool(
        description=description,
        parameters=ToolParameters(type="object", properties=properties or {}, required=required),
        _execute_config=ExecuteConfig(name=name),
    )


def _executing_tool(name: str = "test_tool") -> MagicMock:
    """A stand-in StackOneTool whose execute() the test controls."""
    tool = MagicMock()
    tool.name = name
    tool.description = "A test tool"
    return tool


# --- Declaration ---


class TestDeclaration:
    def test_name_and_description(self):
        adk_tool = StackOneAdkTool(_served_tool(name="calendly_list_events", description="List events"))

        assert adk_tool.name == "calendly_list_events"
        assert adk_tool.description == "List events"

    def test_declares_the_served_schema_and_required_list(self):
        adk_tool = StackOneAdkTool(
            _served_tool(
                properties={
                    "status": {"type": "string", "enum": ["active", "canceled"]},
                    "query": {"type": "object", "properties": {"page_size": {"type": "integer"}}},
                },
                required=["status"],
            )
        )

        decl = adk_tool._get_declaration()

        assert decl.parameters is None
        assert decl.parameters_json_schema == {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "canceled"]},
                "query": {"type": "object", "properties": {"page_size": {"type": "integer"}}},
            },
            "required": ["status"],
        }

    def test_keeps_the_served_required_order(self):
        adk_tool = StackOneAdkTool(
            _served_tool(properties={"a": {"type": "string"}, "b": {"type": "string"}}, required=["b", "a"])
        )

        assert adk_tool._get_declaration().parameters_json_schema["required"] == ["b", "a"]

    def test_omits_required_when_none_is_served(self):
        adk_tool = StackOneAdkTool(_served_tool(properties={"page_size": {"type": "integer"}}))

        assert "required" not in adk_tool._get_declaration().parameters_json_schema

    def test_declares_no_parameters_for_an_empty_schema(self):
        decl = StackOneAdkTool(_served_tool())._get_declaration()

        assert decl.name == "test_tool"
        assert decl.parameters is None
        assert decl.parameters_json_schema is None


# --- Execution ---


class TestRunAsync:
    @pytest.mark.asyncio
    async def test_returns_the_server_result_unchanged(self):
        tool = _executing_tool()
        served = {"isError": False, "result": {"data": [{"id": "1"}]}}
        tool.execute.return_value = served

        result = await StackOneAdkTool(tool).run_async(args={"page_size": 10}, tool_context=MagicMock())

        assert result == served
        tool.execute.assert_called_once_with({"page_size": 10})

    @pytest.mark.asyncio
    async def test_reports_an_api_error_with_its_status_and_body(self):
        tool = _executing_tool(name="workday_list_workers")
        tool.execute.side_effect = StackOneAPIError(
            "Forbidden", status_code=403, response_body={"detail": "scope missing"}
        )

        result = await StackOneAdkTool(tool).run_async(args={}, tool_context=MagicMock())

        assert result == {
            "error": "Forbidden",
            "status_code": 403,
            "response_body": {"detail": "scope missing"},
            "tool_name": "workday_list_workers",
        }

    @pytest.mark.asyncio
    async def test_reports_any_other_failure(self):
        tool = _executing_tool()
        tool.execute.side_effect = RuntimeError("API connection failed")

        result = await StackOneAdkTool(tool).run_async(args={}, tool_context=MagicMock())

        assert result == {"error": "API connection failed", "tool_name": "test_tool"}

    @pytest.mark.asyncio
    async def test_runs_calls_concurrently(self):
        tool = _executing_tool()
        tool.execute.return_value = {"isError": False, "result": {}}
        adk_tool = StackOneAdkTool(tool)

        results = await asyncio.gather(
            *(adk_tool.run_async(args={"n": n}, tool_context=MagicMock()) for n in range(3))
        )

        assert results == [{"isError": False, "result": {}}] * 3
        assert tool.execute.call_count == 3
