"""Tests for StackOne ADK tool adapter."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from google.genai import types

from stackone_adk.tools import StackOneAdkTool


# --- Helper ---


def _make_mock_tool(
    name: str = "test_tool",
    description: str = "A test tool",
    properties: dict | None = None,
) -> MagicMock:
    """Create a mock StackOneTool for testing."""
    tool = MagicMock()
    tool.name = name
    tool.description = description
    tool.parameters = MagicMock()
    tool.parameters.properties = properties or {}
    tool.parameters.model_dump.return_value = {
        "type": "object",
        "properties": properties or {},
    }
    return tool


# --- Tool adapter tests ---


class TestStackOneAdkTool:
    def test_name_and_description(self):
        mock_tool = _make_mock_tool(name="calendly_list_events", description="List Calendly events")
        adk_tool = StackOneAdkTool(mock_tool)
        assert adk_tool.name == "calendly_list_events"
        assert adk_tool.description == "List Calendly events"

    def test_declaration_with_parameters(self):
        mock_tool = _make_mock_tool(
            name="calendly_list_events",
            description="List events",
            properties={
                "page_size": {"type": "integer", "description": "Number of results", "nullable": True},
                "status": {"type": "string", "description": "Filter by status", "nullable": False},
            },
        )
        adk_tool = StackOneAdkTool(mock_tool)
        decl = adk_tool._get_declaration()

        assert decl.name == "calendly_list_events"
        assert decl.description == "List events"
        assert decl.parameters_json_schema is not None
        assert "page_size" in decl.parameters_json_schema["properties"]
        assert "status" in decl.parameters_json_schema["properties"]
        assert decl.parameters_json_schema["required"] == ["status"]

    def test_declaration_empty_properties(self):
        mock_tool = _make_mock_tool(properties={})
        adk_tool = StackOneAdkTool(mock_tool)
        decl = adk_tool._get_declaration()

        assert decl.name == "test_tool"
        assert decl.parameters is None
        assert decl.parameters_json_schema is None

    def test_declaration_no_required_fields(self):
        mock_tool = _make_mock_tool(
            properties={
                "page_size": {"type": "integer", "nullable": True},
            },
        )
        adk_tool = StackOneAdkTool(mock_tool)
        decl = adk_tool._get_declaration()

        assert decl.parameters_json_schema is not None
        assert "required" not in decl.parameters_json_schema

    def test_declaration_all_required_fields(self):
        mock_tool = _make_mock_tool(
            properties={
                "a": {"type": "string", "nullable": False},
                "b": {"type": "integer", "nullable": False},
            },
        )
        adk_tool = StackOneAdkTool(mock_tool)
        decl = adk_tool._get_declaration()

        assert set(decl.parameters_json_schema["required"]) == {"a", "b"}

    def test_declaration_nullable_not_set_means_required(self):
        mock_tool = _make_mock_tool(
            properties={
                "field": {"type": "string"},
            },
        )
        adk_tool = StackOneAdkTool(mock_tool)
        decl = adk_tool._get_declaration()

        assert decl.parameters_json_schema["required"] == ["field"]

    def test_declaration_passes_raw_json_schema(self):
        """Verify the declaration uses parameters_json_schema (not parameters)."""
        mock_tool = _make_mock_tool(
            properties={
                "name": {"type": "string", "nullable": False},
            },
        )
        adk_tool = StackOneAdkTool(mock_tool)
        decl = adk_tool._get_declaration()

        assert decl.parameters_json_schema is not None
        assert decl.parameters is None

    @pytest.mark.asyncio
    async def test_run_async_success(self):
        mock_tool = _make_mock_tool()
        mock_tool.execute.return_value = {"data": [{"id": "1", "name": "Event"}]}

        adk_tool = StackOneAdkTool(mock_tool)
        tool_context = MagicMock()
        result = await adk_tool.run_async(args={"page_size": 10}, tool_context=tool_context)

        assert result == {"data": [{"id": "1", "name": "Event"}]}
        mock_tool.execute.assert_called_once_with({"page_size": 10})

    @pytest.mark.asyncio
    async def test_run_async_wraps_non_dict_result(self):
        mock_tool = _make_mock_tool()
        mock_tool.execute.return_value = "plain string result"

        adk_tool = StackOneAdkTool(mock_tool)
        tool_context = MagicMock()
        result = await adk_tool.run_async(args={}, tool_context=tool_context)

        assert result == {"result": "plain string result"}

    @pytest.mark.asyncio
    async def test_run_async_handles_exception(self):
        mock_tool = _make_mock_tool()
        mock_tool.execute.side_effect = RuntimeError("API connection failed")

        adk_tool = StackOneAdkTool(mock_tool)
        tool_context = MagicMock()
        result = await adk_tool.run_async(args={}, tool_context=tool_context)

        assert "error" in result
        assert "API connection failed" in result["error"]
        assert result["tool_name"] == "test_tool"

    @pytest.mark.asyncio
    async def test_run_async_preserves_stackone_api_error(self):
        from stackone_ai.models import StackOneAPIError

        mock_tool = _make_mock_tool(name="workday_list_workers")
        mock_tool.execute.side_effect = StackOneAPIError(
            "Forbidden", status_code=403, response_body={"detail": "scope missing"}
        )

        adk_tool = StackOneAdkTool(mock_tool)
        result = await adk_tool.run_async(args={}, tool_context=MagicMock())

        assert result["status_code"] == 403
        assert result["response_body"] == {"detail": "scope missing"}
        assert result["tool_name"] == "workday_list_workers"
        assert "Forbidden" in result["error"]

    @pytest.mark.asyncio
    async def test_run_async_concurrent_execution(self):
        """Verify multiple tools can execute concurrently via run_in_executor."""
        mock_tool = _make_mock_tool()
        mock_tool.execute.return_value = {"ok": True}

        adk_tool = StackOneAdkTool(mock_tool)
        tool_context = MagicMock()

        results = await asyncio.gather(
            adk_tool.run_async(args={"a": 1}, tool_context=tool_context),
            adk_tool.run_async(args={"b": 2}, tool_context=tool_context),
            adk_tool.run_async(args={"c": 3}, tool_context=tool_context),
        )

        assert len(results) == 3
        assert all(r == {"ok": True} for r in results)
        assert mock_tool.execute.call_count == 3
