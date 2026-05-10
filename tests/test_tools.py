"""Unit tests for tools layer."""

import asyncio
import json
import pytest

from context.budget_manager import BudgetManager
from context.shared_context import SharedContext
from tools.base import ToolResult
from tools.web_search import WebSearchTool
from tools.code_exec import CodeExecTool


class TestWebSearchTool:
    """Tests for WebSearchTool."""

    @pytest.fixture
    def tool(self):
        return WebSearchTool()

    @pytest.fixture
    def context(self):
        return SharedContext(job_id="test", query="test")

    @pytest.mark.asyncio
    async def test_basic_search(self, tool, context):
        result = await tool.execute(
            input={"query": "machine learning"},
            context=context,
            agent_id="test_agent",
        )
        assert isinstance(result, ToolResult)
        assert result.success is True
        assert "results" in result.data

    @pytest.mark.asyncio
    async def test_empty_query(self, tool, context):
        result = await tool.execute(
            input={"query": ""},
            context=context,
            agent_id="test_agent",
        )
        # Should either fail or return empty results
        assert isinstance(result, ToolResult)

    @pytest.mark.asyncio
    async def test_search_records_to_context(self, tool, context):
        await tool.execute(
            input={"query": "python"},
            context=context,
            agent_id="test_agent",
        )
        assert len(context.tool_calls) > 0
        assert context.tool_calls[0].tool_name == "web_search"


class TestCodeExecTool:
    """Tests for CodeExecTool."""

    @pytest.fixture
    def tool(self):
        return CodeExecTool()

    @pytest.fixture
    def context(self):
        return SharedContext(job_id="test", query="test")

    @pytest.mark.asyncio
    async def test_safe_code(self, tool, context):
        result = await tool.execute(
            input={"code": "print(2 + 2)"},
            context=context,
            agent_id="test_agent",
        )
        assert result.success is True
        assert "4" in result.data.get("stdout", "")

    @pytest.mark.asyncio
    async def test_blocked_import(self, tool, context):
        result = await tool.execute(
            input={"code": "import os; os.system('ls')"},
            context=context,
            agent_id="test_agent",
        )
        assert result.success is False
        err = (result.error_message or result.error_code or "").lower()
        assert "blocked" in err or "dangerous" in err or "malformed" in err

    @pytest.mark.asyncio
    async def test_syntax_error(self, tool, context):
        result = await tool.execute(
            input={"code": "def foo("},
            context=context,
            agent_id="test_agent",
        )
        assert result.success is False

    @pytest.mark.asyncio
    async def test_code_records_to_context(self, tool, context):
        await tool.execute(
            input={"code": "x = 1"},
            context=context,
            agent_id="test_agent",
        )
        assert len(context.tool_calls) > 0
        assert context.tool_calls[0].tool_name == "code_exec"
