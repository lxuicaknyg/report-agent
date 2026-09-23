"""Running a user-written query against a saved connection.

The value a chapter cites is read out of the result here, so what this layer
accepts or refuses is what the report ends up asserting.
"""

import asyncio
import datetime as dt
import decimal

import pytest

from app.connections.service import ConnectionService
from app.core.connections import ConnectionDriver, DataConnection


def connection() -> DataConnection:
    return DataConnection(
        connection_id="conn_1", name="本地 MySQL", driver=ConnectionDriver.MYSQL,
        host="127.0.0.1", port=3306, database="report_agent_demo", username="root",
    )


# ── the read-only guard ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select 1",
        "  SELECT 1 ;  ",
        "WITH t AS (SELECT 1 AS x) SELECT x FROM t",
        # Generated analysis SQL is commented by design.
        "-- 同比增长率(YoY)分析\nSELECT 1",
        "/* block comment */ SELECT 1",
        "SELECT 1 -- trailing comment",
        "# MySQL hash comment\nSELECT 1",
        # A semicolon inside a literal is not a second statement.
        "SELECT 'a;b' AS x",
        # ...and neither is a write keyword inside one a write.
        "WITH t AS (SELECT 'delete me' AS x) SELECT * FROM t",
    ],
)
def test_reading_statements_are_allowed(sql):
    assert ConnectionService._assert_read_only(sql)


@pytest.mark.parametrize(
    "sql,reason",
    [
        ("DELETE FROM t", "只允许执行"),
        ("UPDATE t SET x = 1", "只允许执行"),
        ("SELECT 1; DROP TABLE t", "一次只能执行一条语句"),
        # PostgreSQL and GaussDB let a CTE write, which reads as a SELECT.
        ("WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d", "不允许出现 DELETE"),
        ("   ", "不能为空"),
        ("-- 只有注释", "不能为空"),
        # A comment must not be able to disguise a write.
        ("-- 看起来像查询\nDELETE FROM t", "只允许执行"),
        ("/* SELECT 1 */ DROP TABLE t", "只允许执行"),
    ],
)
def test_writing_statements_are_refused(sql, reason):
    with pytest.raises(ValueError) as caught:
        ConnectionService._assert_read_only(sql)
    assert reason in str(caught.value)


def test_a_trailing_semicolon_is_not_a_second_statement():
    assert ConnectionService._assert_read_only("SELECT 1;") == "SELECT 1"


# ── reading a metric out of a result ──────────────────────────────────────

def test_the_last_column_is_the_value_and_the_rest_are_dimensions():
    extraction = ConnectionService.extract(
        ["统计日期", "机构", "存款余额"],
        [{"统计日期": "2024-04-15", "机构": "BR003", "存款余额": 45000.25}],
    )
    assert extraction.usable
    assert extraction.value == "45000.25"
    assert extraction.dimensions == {"统计日期": "2024-04-15", "机构": "BR003"}


def test_a_bare_scalar_is_allowed_but_carries_no_dimensions():
    """Permitted, because the metric name still says what it is — and left
    unlabelled, so the question card can say so."""
    extraction = ConnectionService.extract(["余额"], [{"余额": 42}])
    assert extraction.usable and extraction.value == "42"
    assert extraction.dimensions == {}


def test_several_rows_are_refused_rather_than_reduced_to_the_first():
    extraction = ConnectionService.extract(
        ["机构", "余额"], [{"机构": "BR001", "余额": 1}, {"机构": "BR002", "余额": 2}]
    )
    assert not extraction.usable
    assert "收敛到一行" in extraction.error


def test_a_result_cut_off_at_the_row_cap_is_refused_even_at_one_row():
    extraction = ConnectionService.extract(["余额"], [{"余额": 1}], truncated=True)
    assert not extraction.usable and "1+ 行" in extraction.error


def test_no_rows_is_refused():
    assert "没有返回任何行" in ConnectionService.extract(["余额"], []).error


def test_a_null_value_is_refused():
    extraction = ConnectionService.extract(["日期", "余额"], [{"日期": "x", "余额": None}])
    assert not extraction.usable and "NULL" in extraction.error


def test_a_decimals_trailing_zeros_are_the_databases_scale_not_noise():
    """DECIMAL(18,2) returning 1996000.00 is a balance to two places. Reducing
    it to 1996000 — or routing it through a float into 1996000.0 — changes what
    the chapter prints."""
    assert ConnectionService._render(decimal.Decimal("1996000.00")) == "1996000.00"
    assert ConnectionService._render(decimal.Decimal("0.00")) == "0.00"


def test_preview_rows_show_the_same_digits_the_value_is_recorded_with():
    """The trial run is what the user approves, so it must not display a
    rounder number than the one that gets stored."""
    assert ConnectionService._jsonable(decimal.Decimal("1996000.00")) == "1996000.00"


@pytest.mark.parametrize(
    "text,expected",
    [
        # MySQL wraps the whole message in double quotes, so the first quoted
        # run is the word "Table", not the table.
        ('(1146, "Table \'demo.orders\' doesn\'t exist")', "demo.orders"),
        ("Unknown column 'no_such_col' in 'field list'", "no_such_col"),
        ('relation "public.orders" does not exist', "public.orders"),
        ("nothing quoted here", None),
    ],
)
def test_the_quoted_object_name_is_pulled_out_of_a_driver_error(text, expected):
    assert ConnectionService._first_quoted(text) == expected


def test_a_null_dimension_is_dropped_rather_than_recorded_as_none():
    extraction = ConnectionService.extract(
        ["机构", "余额"], [{"机构": None, "余额": 1}]
    )
    assert extraction.usable and extraction.dimensions == {}


def test_a_decimal_keeps_the_scale_the_database_returned():
    """A balance must not reach the chapter as 2049900.2500000002 because it
    passed through a float on the way."""
    extraction = ConnectionService.extract(
        ["余额"], [{"余额": decimal.Decimal("2049900.25")}]
    )
    assert extraction.value == "2049900.25"


def test_a_date_dimension_is_rendered_as_a_date_not_a_repr():
    extraction = ConnectionService.extract(
        ["统计日期", "余额"], [{"统计日期": dt.date(2024, 4, 15), "余额": 1}]
    )
    assert extraction.dimensions == {"统计日期": "2024-04-15"}


# ── the service surface ───────────────────────────────────────────────────

class Repository:
    def __init__(self, item: DataConnection) -> None:
        self.item = item

    async def get(self, connection_id: str) -> DataConnection:
        if connection_id != self.item.connection_id:
            raise KeyError(connection_id)
        return self.item


def test_a_refused_statement_comes_back_as_a_result_not_an_exception():
    """Same contract as /test: the reason belongs beside the editor."""

    async def run():
        service = ConnectionService(Repository(connection()))
        result = await service.query("conn_1", "DROP TABLE t")
        assert result.success is False
        assert "只允许执行" in result.message
        assert result.extraction is None

    asyncio.run(run())


def test_an_unknown_connection_still_raises():
    async def run():
        service = ConnectionService(Repository(connection()))
        with pytest.raises(KeyError):
            await service.query("nope", "SELECT 1")

    asyncio.run(run())


# ── detail tables ─────────────────────────────────────────────────────────

def test_a_detail_table_keeps_every_column_as_content():
    """No column is 'the value' in a list: forcing the positional convention
    onto a detail table would invent a distinction the data does not have."""
    extraction = ConnectionService.extract(
        ["项目编号", "客户名称", "投放金额"],
        [{"项目编号": "P01", "客户名称": "甲公司", "投放金额": 1200},
         {"项目编号": "P02", "客户名称": "乙公司", "投放金额": 800}],
        shape="table",
    )
    assert extraction.usable and extraction.shape == "table"
    assert extraction.value is None and extraction.dimensions == {}
    assert extraction.columns == ["项目编号", "客户名称", "投放金额"]
    assert extraction.rows[1] == {"项目编号": "P02", "客户名称": "乙公司", "投放金额": "800"}
    assert extraction.truncated is False


def test_several_rows_are_fine_for_a_table_and_refused_for_a_value():
    rows = [{"机构": "BR001", "余额": 1}, {"机构": "BR002", "余额": 2}]
    assert ConnectionService.extract(["机构", "余额"], rows, shape="table").usable
    assert not ConnectionService.extract(["机构", "余额"], rows, shape="value").usable


def test_a_table_past_the_cap_is_cut_and_says_so():
    rows = [{"n": i} for i in range(150)]
    extraction = ConnectionService.extract(["n"], rows, shape="table", max_rows=100)
    assert extraction.usable
    assert len(extraction.rows) == 100
    assert extraction.truncated is True


def test_a_table_cell_keeps_the_databases_precision():
    extraction = ConnectionService.extract(
        ["分行", "余额"], [{"分行": "上海分行", "余额": decimal.Decimal("1996000.00")}],
        shape="table",
    )
    assert extraction.rows[0]["余额"] == "1996000.00"


def test_an_empty_table_is_still_refused():
    assert not ConnectionService.extract(["a"], [], shape="table").usable


def test_the_single_row_error_points_at_the_table_option():
    """We may simply have classified the question wrongly, so the message has
    to offer that reading rather than only telling the user to aggregate."""
    error = ConnectionService.extract(["a", "b"], [{"a": 1, "b": 2}, {"a": 3, "b": 4}]).error
    assert "收敛到一行" in error and "按明细清单补充" in error


# ── derived-analysis SQL ──────────────────────────────────────────────────

class StubTool:
    """Stands in for GenerateAnalysisSQLTool, recording what it was asked."""

    def __init__(self, generated: str | None = "SELECT 1", success: bool = True) -> None:
        self.generated = generated
        self.success = success
        self.calls: list[dict] = []

    async def execute(self, context, arguments):
        from app.core.tooling import ToolResult
        self.calls.append(arguments)
        if not self.success or self.generated is None:
            return ToolResult(success=False, result_for_llm="模型没有返回可用的 SQL", error="x")
        return ToolResult(
            success=True, result_for_llm="ok",
            data={"generated_sql": self.generated, "analysis_type": arguments["analysis_type"],
                  "dialect": arguments["dialect"]},
        )


def service_with(tool, driver=ConnectionDriver.MYSQL):
    item = connection().model_copy(update={"driver": driver})
    return ConnectionService(Repository(item), analysis_tool=tool), item


def test_the_dialect_comes_from_the_connection_not_a_default():
    """Generated SQL is written for the database it will be run against, so a
    MySQL connection must not be handed Postgres syntax to imitate."""

    async def run():
        for driver, dialect in (
            (ConnectionDriver.MYSQL, "mysql"),
            (ConnectionDriver.GAUSSDB, "postgres"),
            (ConnectionDriver.OPENLOOKENG, "presto"),
        ):
            tool = StubTool()
            service, _ = service_with(tool, driver)
            result = await service.analysis_sql("conn_1", "SELECT 1", "yoy")
            assert result.success and result.dialect == dialect
            assert tool.calls[0]["dialect"] == dialect

    asyncio.run(run())


def test_a_generated_query_is_returned_not_executed():
    """Generation and execution stay separate: the user reads the SQL first."""

    async def run():
        tool = StubTool(generated="SELECT a, b FROM t")
        service, _ = service_with(tool)
        result = await service.analysis_sql("conn_1", "SELECT a FROM t", "mom")
        assert result.generated_sql == "SELECT a, b FROM t"
        assert result.analysis_type == "mom"
        assert tool.calls[0]["analysis_type"] == "mom"

    asyncio.run(run())


def test_a_statement_that_could_not_be_run_is_not_worth_rewriting():
    """Rejected before the model call, not after: a write statement cannot be
    executed afterwards either, so spending a generation on it is waste."""

    async def run():
        tool = StubTool()
        service, _ = service_with(tool)
        result = await service.analysis_sql("conn_1", "DELETE FROM t", "yoy")
        assert result.success is False
        assert "只允许执行" in result.message
        assert tool.calls == []

    asyncio.run(run())


def test_a_failed_generation_comes_back_as_a_result():
    async def run():
        service, _ = service_with(StubTool(generated=None, success=False))
        result = await service.analysis_sql("conn_1", "SELECT 1", "yoy")
        assert result.success is False and result.generated_sql is None
        assert "没有返回可用的 SQL" in result.message

    asyncio.run(run())


def test_without_the_tool_the_feature_reports_itself_off():
    async def run():
        service = ConnectionService(Repository(connection()))
        result = await service.analysis_sql("conn_1", "SELECT 1", "yoy")
        assert result.success is False and "未启用" in result.message

    asyncio.run(run())
