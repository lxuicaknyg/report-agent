"""Numbers come from the tool, never from the model.

The model was reading a sheet's rows back and totalling them itself, and it got
one of six monthly figures wrong — a customer count off by one that then flowed
into the prose. Research now fills in an aggregation and the data source does
the arithmetic; there is no query for the model to write and nothing for it to
add up.
"""

import asyncio
import tempfile
from pathlib import Path

from datetime import date

from openpyxl import Workbook

from app.core.models import AggregateFilter, AggregateMetric, AggregateRequest
from app.data.sources.excel import ExcelDataSource
from app.reporting.chapter_writer_agent import ChapterWriterAgent
from app.tools import AggregateDatasetTool


def workbook() -> Path:
    path = Path(tempfile.mkdtemp()) / "data.xlsx"
    book = Workbook()
    summary = book.active
    summary.title = "月度汇总"
    summary.append(["统计月份", "区域", "交易客户数", "交易金额(元)"])
    for month in ("2025-12", "2026-01", "2026-02"):
        summary.append([month, "华东", 20, 1000])
        summary.append([month, "华南", 13, 500])
    detail = book.create_sheet("交易明细")
    detail.append(["交易日期", "客户编号"])
    for day in (date(2026, 1, 5), date(2026, 1, 19), date(2026, 2, 3)):
        detail.append([day, "C0001"])
    detail.append([date(2026, 2, 11), "C0002"])
    detail.append([date(2025, 12, 30), "C0009"])
    book.save(path)
    return path


def source(dataset_id: str = "excel_agg") -> ExcelDataSource:
    return ExcelDataSource(workbook(), dataset_id, "data.xlsx")


def test_the_tool_totals_the_column_the_model_used_to_total_by_hand():
    async def run():
        result = await source().aggregate(
            "excel_agg",
            AggregateRequest(
                sheet_name="月度汇总",
                filters=[AggregateFilter(column="统计月份", op="between", value=["2026-01", "2026-02"])],
                group_by=["区域"],
                metrics=[AggregateMetric(column="交易客户数", function="sum", alias="客户数")],
                order_by="客户数",
            ),
        )
        # December is outside the period and must not be in the total.
        assert [(row["区域"], row["客户数"]) for row in result.rows] == [("华东", 40), ("华南", 26)]
        assert result.matched_rows == 4

    asyncio.run(run())


def test_deduplication_is_the_tool_s_job_not_the_model_s():
    """Counting distinct customers used to mean paging every detail row into
    the prompt and tallying them; one tally came back short by one."""

    async def run():
        result = await source().aggregate(
            "excel_agg",
            AggregateRequest(
                sheet_name="交易明细",
                filters=[AggregateFilter(column="交易日期", op="between", value=["2026-01", "2026-02"])],
                metrics=[
                    AggregateMetric(column="客户编号", function="count_distinct", alias="客户数"),
                    AggregateMetric(column="客户编号", function="count", alias="笔数"),
                    AggregateMetric(column="交易日期", function="max", alias="最晚交易日"),
                ],
            ),
        )
        row = result.rows[0]
        assert row["客户数"] == 2 and row["笔数"] == 4
        # The cutoff date is a fact to be read, not the period's end date.
        assert row["最晚交易日"].startswith("2026-02-11")

    asyncio.run(run())


def test_a_month_written_as_text_matches_a_real_date_column():
    """The caller cannot know how a sheet stored its dates, and writing
    "2026-01" is how a report period is actually expressed."""

    async def run():
        result = await source().aggregate(
            "excel_agg",
            AggregateRequest(
                sheet_name="交易明细",
                filters=[AggregateFilter(column="交易日期", op="eq", value="2026-01")],
                metrics=[AggregateMetric(column="客户编号", function="count", alias="笔数")],
            ),
        )
        assert result.rows[0]["笔数"] == 2

    asyncio.run(run())


def test_an_unknown_column_says_what_the_sheet_actually_has():
    async def run():
        try:
            await source().aggregate(
                "excel_agg",
                AggregateRequest(
                    sheet_name="月度汇总",
                    metrics=[AggregateMetric(column="不存在的列", function="sum")],
                ),
            )
        except ValueError as exc:
            # The agent retries on the error text, so it has to be actionable.
            assert "不存在的列" in str(exc) and "交易客户数" in str(exc)
        else:
            raise AssertionError("an unknown column must not aggregate to anything")

    asyncio.run(run())


def test_research_offers_aggregation_and_never_free_form_sql():
    # query_dataset let the model write the calculation in another language;
    # read_dataset survives only for rows a template table lists verbatim.
    assert ChapterWriterAgent._read_tool_names == {"aggregate_dataset", "read_dataset"}


def test_the_tool_schema_only_offers_slots_to_fill():
    schema = AggregateDatasetTool.parameters_schema["properties"]
    assert "sql" not in schema
    functions = schema["metrics"]["items"]["properties"]["function"]["enum"]
    assert functions == ["sum", "count", "count_distinct", "avg", "min", "max"]
    operators = schema["filters"]["items"]["properties"]["op"]["enum"]
    assert "eq" in operators and "between" in operators
