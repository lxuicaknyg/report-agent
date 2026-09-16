from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any, Optional, Tuple
from uuid import uuid4

import sqlglot

from ..core.models import Evidence
from ..core.ports import LlmService
from ..core.tooling import Tool, ToolContext, ToolResult

# ==========================================
# 辅助解析与生成逻辑
# ==========================================
class SQLParser:
    """SQL解析器 - 解析SQL语句并提取关键信息"""

    def __init__(self, dialect: str = "postgres"):
        self.dialect = dialect

    def validate_sql(self, sql: str) -> Tuple[bool, str]:
        try:
            sqlglot.parse_one(sql, dialect=self.dialect)
            return True, "SQL语法正确"
        except sqlglot.ParseError as e:
            return False, f"SQL语法错误: {e}"
        except Exception as e:
            return False, f"验证失败: {e}"

    def is_valid(self, sql: str) -> bool:
        try:
            sqlglot.parse_one(sql, dialect=self.dialect)
            return True
        except Exception:
            return False


def _extract_sql_from_response(llm_response: str) -> Optional[str]:
    sql_pattern = r"```sql\s*\n(.*?)\n```"
    matches = re.findall(sql_pattern, llm_response, re.DOTALL)
    if matches:
        return matches[0].strip()

    backtick_pattern = r"`([^`]+)`"
    matches = re.findall(backtick_pattern, llm_response)
    if matches:
        return matches[0].strip()

    return llm_response.strip()


def _build_analysis_prompt(original_sql: str, analysis_type: str, dialect: str) -> str:
    analysis_type_map = {
        "yoy": (
            "同比增长率 (YoY)",
            "计算与去年同期相比的增长率。\n"
            "关键逻辑：\n"
            "1. 逻辑实现：通过自连接将本期与去年同期数据合并\n"
            "2. 计算公式：(本期值 - 去年同期值) / 去年同期值 * 100\n\n"
            "3. 边界处理：处理除零情况（使用NULLIF或CASE WHEN）\n"
            "4. 日期处理：已知日期时，优先使用实际日期，避免函数日期计算\n"
            "5. 结果展示：最终展示结果同时展示出连接条件或分组条件涉及的字段、本期日期、本期数据、去年日期、去年数据及同比增长率",
        ),
        "mom": (
            "环比增长率 (MoM)",
            "计算与上一个周期相比的增长率。\n"
            "关键逻辑：\n"
            "1. 逻辑实现：使用窗口函数LAG(col) OVER(ORDER BY time)按时间排序获取上期数据\n"
            "2. 计算公式：(本期值 - 上期值) / 上期值 * 100\n"
            "3. 边界处理：处理无上期数据的情况\n"
            "4. 结果展示：最终展示结果同时展示出连接条件或分组条件涉及的字段、本期日期、本期数据、去年日期、去年数据及同比增长率\n"
            "5. 注意：使用窗口函数LAG()，必须先扩展WHERE中的时间范围（覆盖上期及本期），在计算出LAG后，再在最外层过滤出目标日期",
        ),
        "ranking": (
            "排名分析",
            "计算各指标的排名。\n"
            "关键逻辑：\n"
            "1. 逻辑实现：使用窗口函数RANK()进行排名，指定ORDER BY排序规则（降序或升序）\n"
            "2. 针对场景推断处理：\n"
            "   -若原SQL缺乏分组维度，自动按合理主体字段（如客户ID、机构ID、时间等）分组后再做RANK()\n"
            "   -若原SQL已包含分组维度，则对该维度使用RANK()\n"
            "3. 注意：如果原SQL聚合后只有1行结果（例如对日期GROUP BY且WHERE限制具体一天等），计算排名是没有意义的，可以合理减少WHERE条件中的具体时间限制",
        ),
    }

    if analysis_type not in analysis_type_map:
        raise ValueError(
            f"Unsupported analysis type: {analysis_type}. Must be one of {list(analysis_type_map.keys())}"
        )

    type_name, logic_desc = analysis_type_map[analysis_type]
    prompt = f"""你是一个专业的SQL分析专家。请根据以下要求生成分析计算SQL。
**原始SQL：**
```sql
{original_sql}
```
**分析类型：** {type_name}
**计算逻辑要求：**
{logic_desc}
**输出要求：**
1. 仅输出最终SQL代码（用```sql包裹）
2. 添加核心注释说明关键计算逻辑
3. 保持与原SQL相同的表结构和字段引用
4. 确保SQL语法符合{dialect}规范
5. 使用标准的SQL窗口函数和聚合函数，但涉及日期计算时，不允许使用日期函数，必须仿照原始SQL的格式直接使用实际的日期
6. 处理边界情况（如除零、空值等）
请直接输出SQL代码："""
    return prompt

def _build_correction_prompt(
    original_sql: str, analysis_type: str, generated_sql: str, error_msg: str
) -> str:
    return f"""SQL语法验证失败，请修正以下SQL语句。
**原始SQL：**
```sql
{original_sql}
```
**分析类型：** {analysis_type}
**当前SQL（有语法错误）：**
```sql
{generated_sql}
```
**错误信息：**
{error_msg}
**修正要求：**
1. 仔细检查并修复SQL语法错误
2. 确保所有关键字、函数、括号匹配正确
3. 保持原有的分析逻辑不变
4. 仅输出修正后的SQL代码（用```sql包裹）
请输出修正后的SQL："""

# ==========================================
# 工具封装层 (Tool Standard Core Implementation)
# ==========================================

class GenerateAnalysisSQLTool(Tool):
    """根据原子指标SELECT语句生成同比(YoY)、环比(MoM)或排名(ranking)SQL分析语句的工具"""

    name = "generate_analysis_sql"
    description = (
        "Generate YoY (year-over-year), MoM (month-over-month), or ranking SQL statements "
        "from an atomic indicator SELECT query."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "Original raw SELECT SQL statement",
            },
            "analysis_type": {
                "type": "string",
                "enum": ["yoy", "mom", "ranking"],
                "description": "Type of analysis SQL to generate: 'yoy' (year-over-year), 'mom' (month-over-month), or 'ranking'",
            },
            "dialect": {
                "type": "string",
                "default": "postgres",
                "description": "SQL dialect, e.g., 'postgres', 'mysql', 'hive', 'spark'",
            },
        },
        "required": ["sql", "analysis_type"],
        "additionalProperties": False,
    }

    def __init__(self, llm: LlmService):
        """注入 LlmService 实例"""
        self.llm = llm

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        original_sql = arguments.get("sql")
        analysis_type = arguments.get("analysis_type")
        dialect = arguments.get("dialect", "postgres")

        # 校验必填参数
        if not original_sql:
            return ToolResult(
                success=False,
                result_for_llm="Parameter 'sql' is required and cannot be empty.",
                error="missing_parameter",
            )
        if not analysis_type or analysis_type not in ["yoy", "mom", "ranking"]:
            return ToolResult(
                success=False,
                result_for_llm="Parameter 'analysis_type' must be one of: 'yoy', 'mom', 'ranking'.",
                error="invalid_parameter",
            )

        try:
            sql_parser = SQLParser(dialect=dialect)
            prompt = _build_analysis_prompt(original_sql, analysis_type, dialect)

            generated_sql = None
            max_retries = 2

            valid = False
            for attempt in range(max_retries + 1):
                messages = [{"role": "user", "content": prompt}]
                response = await self.llm.complete(messages, [])  # 无需工具，传空列表
                llm_response = response.get("content", "")
                generated_sql = _extract_sql_from_response(llm_response)

                if not generated_sql:
                    continue

                # 验证 SQL 语法
                if sql_parser.is_valid(generated_sql):
                    valid = True
                    break
                else:
                    _, error_msg = sql_parser.validate_sql(generated_sql)

                    if attempt < max_retries:
                        prompt = _build_correction_prompt(
                            original_sql, analysis_type, generated_sql, error_msg
                        )

            if not generated_sql or not valid:
                return ToolResult(
                    success=False,
                    result_for_llm="Failed to generate valid executable SQL after retries.",
                    error="sql_generation_failed",
                )

            # 生成证据项 (Evidence)
            evidence = Evidence(
                evidence_id=str(uuid4()),
                kind="generated_sql",
                title=f"Generated {analysis_type.upper()} SQL",
                source="GenerateAnalysisSQLTool",
                value={
                    "original_sql": original_sql,
                    "generated_sql": generated_sql,
                    "analysis_type": analysis_type,
                    "dialect": dialect,
                },
                method="generate_analysis_sql",
            )

            return ToolResult(
                success=True,
                result_for_llm=f"Successfully generated {analysis_type.upper()} SQL:\n\n```sql\n{generated_sql}\n```",
                data={
                    "generated_sql": generated_sql,
                    "analysis_type": analysis_type,
                    "dialect": dialect,
                },
                evidence=[evidence],
            )

        except Exception as exc:
            return ToolResult(
                success=False,
                result_for_llm=f"An error occurred while generating analysis SQL: {str(exc)}",
                error=str(exc),
            )