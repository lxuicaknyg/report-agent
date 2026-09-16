"""
Tests for sql2sql_tool.py (after refactoring to use LlmService)
Run with: pytest backend/app/tools/test_sql2sql_tool.py -v
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 添加 backend 根目录到 sys.path

import pytest
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock
from uuid import UUID

# 使用绝对包路径导入（移除了已删除的 llm_call 和 SQLAnalysisConfig）
from app.tools import sql2sql_tool
from app.tools.sql2sql_tool import (
    SQLParser,
    GenerateAnalysisSQLTool,
    _build_analysis_prompt,
    _build_correction_prompt,
    _extract_sql_from_response,
)

# ===========================
# 辅助函数测试（保持不变）
# ===========================

class TestSQLParser:
    def test_validate_sql_valid(self):
        parser = SQLParser(dialect="mysql")
        valid, msg = parser.validate_sql("SELECT 1")
        assert valid is True
        assert "正确" in msg

    def test_validate_sql_invalid(self):
        parser = SQLParser(dialect="mysql")
        valid, msg = parser.validate_sql("SELEC 1")
        assert valid is False
        assert "错误" in msg

    def test_is_valid_true(self):
        parser = SQLParser(dialect="mysql")
        assert parser.is_valid("SELECT a FROM b") is True

    def test_is_valid_false(self):
        parser = SQLParser(dialect="mysql")
        assert parser.is_valid("SELEKT 1") is False
        assert parser.is_valid("SELECT FROM") is False

class TestExtractSqlFromResponse:
    def test_extract_with_sql_block(self):
        response = "some text\n```sql\nSELECT * FROM t\n```\nend"
        result = _extract_sql_from_response(response)
        assert result == "SELECT * FROM t"

    def test_extract_with_backticks(self):
        response = "use `SELECT 1` as answer"
        result = _extract_sql_from_response(response)
        assert result == "SELECT 1"

    def test_extract_no_markers(self):
        response = "SELECT 1"
        result = _extract_sql_from_response(response)
        assert result == "SELECT 1"

    def test_extract_empty(self):
        assert _extract_sql_from_response("no sql here") == "no sql here"

class TestBuildPrompts:
    def test_build_analysis_prompt_yoy(self):
        sql = "SELECT date, amount FROM sales"
        prompt = _build_analysis_prompt(sql, "yoy", "mysql")
        assert "同比增长率" in prompt
        assert sql in prompt

    def test_build_analysis_prompt_mom(self):
        sql = "SELECT month, revenue FROM finance"
        prompt = _build_analysis_prompt(sql, "mom", "postgresql")
        assert "环比增长率" in prompt
        assert sql in prompt

    def test_build_analysis_prompt_ranking(self):
        sql = "SELECT dept, salary FROM employees"
        prompt = _build_analysis_prompt(sql, "ranking", "hive")
        assert "排名分析" in prompt
        assert sql in prompt

    def test_build_analysis_prompt_invalid_type(self):
        with pytest.raises(ValueError, match="Unsupported analysis type"):
            _build_analysis_prompt("SELECT 1", "unknown", "mysql")

    def test_build_correction_prompt(self):
        prompt = _build_correction_prompt("SELECT 1", "yoy", "SELECT 2", "syntax error")
        assert "语法错误" in prompt
        assert "SELECT 2" in prompt

# ===========================
# GenerateAnalysisSQLTool 集成测试（使用 LlmService mock）
# ===========================

class TestGenerateAnalysisSQLTool:
    @pytest.fixture
    def tool(self):
        """创建注入 mock LlmService 的工具实例"""
        mock_llm = MagicMock()
        # 使 complete 方法成为异步，返回字典格式
        async def async_complete(messages, tools=None):
            return {"content": "default response"}
        mock_llm.complete = async_complete
        return GenerateAnalysisSQLTool(llm=mock_llm)

    # ---------- 参数校验 ----------
    @pytest.mark.asyncio
    async def test_missing_sql(self, tool):
        result = await tool.execute(None, {"analysis_type": "yoy"})
        assert result.success is False
        assert "sql" in result.result_for_llm.lower()

    @pytest.mark.asyncio
    async def test_invalid_analysis_type(self, tool):
        result = await tool.execute(None, {"sql": "SELECT 1", "analysis_type": "invalid"})
        assert result.success is False
        assert "analysis_type" in result.result_for_llm

    # ---------- 正常生成（mock LLM 返回有效 SQL） ----------
    @pytest.mark.asyncio
    async def test_generate_yoy_success(self, tool):
        # 覆盖 fixture 中的 complete 方法
        async def mock_complete(messages, tools=None):
            return {"content": "```sql\nSELECT ...\n```"}
        tool.llm.complete = mock_complete

        with patch.object(SQLParser, 'is_valid', return_value=True):
            result = await tool.execute(
                None,
                {"sql": "SELECT date, amount FROM sales", "analysis_type": "yoy"}
            )
        assert result.success is True
        assert result.data["analysis_type"] == "yoy"
        assert result.data["generated_sql"] == "SELECT ..."
        assert len(result.evidence) == 1

    @pytest.mark.asyncio
    async def test_generate_mom_success(self, tool):
        async def mock_complete(messages, tools=None):
            return {"content": "```sql\nSELECT LAG(...)\n```"}
        tool.llm.complete = mock_complete

        with patch.object(SQLParser, 'is_valid', return_value=True):
            result = await tool.execute(
                None,
                {"sql": "SELECT month, rev FROM finance", "analysis_type": "mom"}
            )
        assert result.success is True
        assert result.data["analysis_type"] == "mom"

    @pytest.mark.asyncio
    async def test_generate_ranking_success(self, tool):
        async def mock_complete(messages, tools=None):
            return {"content": "```sql\nSELECT RANK()...\n```"}
        tool.llm.complete = mock_complete

        with patch.object(SQLParser, 'is_valid', return_value=True):
            result = await tool.execute(
                None,
                {"sql": "SELECT student, score FROM grades", "analysis_type": "ranking"}
            )
        assert result.success is True
        assert result.data["analysis_type"] == "ranking"

    # ---------- 重试机制：第一次 SQL 无效，第二次修正成功 ----------
    @pytest.mark.asyncio
    async def test_retry_and_succeed(self, tool):
        # 第一次返回无效 SQL，第二次返回有效 SQL
        responses = [
            {"content": "```sql\nINVALID SQL\n```"},
            {"content": "```sql\nSELECT 1\n```"},
        ]
        async def mock_complete(messages, tools=None):
            return responses.pop(0)
        tool.llm.complete = mock_complete

        with patch.object(SQLParser, 'is_valid', side_effect=[False, True]):
            result = await tool.execute(
                None,
                {"sql": "SELECT date, amount FROM sales", "analysis_type": "yoy"}
            )
        assert result.success is True
        assert result.data["generated_sql"] == "SELECT 1"
        # complete 被调用了两次（第一次无效，第二次修正后有效）
        # 但由于 pop 消耗了列表，这里无法直接检查 call_count，可以通过记录次数验证

    # ---------- 重试后仍然失败 ----------
    @pytest.mark.asyncio
    async def test_retry_all_fail(self, tool):
        async def mock_complete(messages, tools=None):
            return {"content": "```sql\nBAD SQL\n```"}
        tool.llm.complete = mock_complete

        with patch.object(SQLParser, 'is_valid', return_value=False):
            result = await tool.execute(
                None,
                {"sql": "SELECT 1", "analysis_type": "yoy"}
            )
        assert result.success is False
        assert "Failed to generate" in result.result_for_llm
        # 默认重试次数为2，加上首次共3次调用
        # 可通过检查 mock 被调用的次数来验证（但此处未暴露计数器，可接受）

    # ---------- 异常处理 ----------
    @pytest.mark.asyncio
    async def test_exception_handling(self, tool):
        async def mock_complete(messages, tools=None):
            raise RuntimeError("API down")
        tool.llm.complete = mock_complete

        result = await tool.execute(
            None,
            {"sql": "SELECT 1", "analysis_type": "yoy"}
        )
        assert result.success is False
        assert "API down" in result.error

    # ---------- 调试用测试（可选） ----------
    @pytest.mark.asyncio
    async def test_retry_and_succeed_debug(self, tool):
        responses = [
            {"content": "```sql\nINVALID SQL\n```"},
            {"content": "```sql\nSELECT 1\n```"},
        ]
        async def mock_complete(messages, tools=None):
            return responses.pop(0)
        tool.llm.complete = mock_complete

        with patch.object(SQLParser, 'is_valid', side_effect=[False, True]):
            result = await tool.execute(
                None,
                {"sql": "SELECT date, amount FROM sales", "analysis_type": "yoy"}
            )
        print(f"result: {result}")
        print(f"success: {result.success}, error: '{result.error}'")
        # 可根据需要添加更多断言
        assert result.success is True