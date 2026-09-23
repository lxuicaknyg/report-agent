"""A figure is either right or it says why it is not.

Three ways this aggregation used to hand back a wrong number without anything
going wrong: a column of numbers stored as text summed by string concatenation,
a breakdown cut to ``limit`` and reported as if it were whole, and both of
those reaching the model as a plain success. Each one is checked here from the
data source and, where it matters, from the tool the model actually calls.
"""

import asyncio
import tempfile
from pathlib import Path

from openpyxl import Workbook

from app.core.models import AggregateMetric, AggregateRequest, RequestContext
from app.core.tooling import ToolContext
from app.data.catalog import DataCatalog
from app.data.sources.excel import ExcelDataSource
from app.tools import AggregateDatasetTool


def _book(rows: list[list], headers: list[str], sheet: str = "台账") -> Path:
    path = Path(tempfile.mkdtemp()) / "data.xlsx"
    book = Workbook()
    worksheet = book.active
    worksheet.title = sheet
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    book.save(path)
    return path


def _source(path: Path, dataset_id: str = "excel_acc") -> ExcelDataSource:
    return ExcelDataSource(path, dataset_id, "data.xlsx")


def test_a_balance_stored_as_text_is_summed_as_a_number():
    """'1200.5' + '300' used to come back as '1200.5300'."""

    path = _book(
        [["华东", "1,200.50"], ["华东", "300"], ["华南", "2000"]],
        ["机构", "余额"],
    )

    async def run():
        return await _source(path).aggregate(
            "excel_acc",
            AggregateRequest(
                sheet_name="台账",
                group_by=["机构"],
                metrics=[AggregateMetric(column="余额", function="sum", alias="余额合计")],
            ),
        )

    result = asyncio.run(run())
    totals = {row["机构"]: row["余额合计"] for row in result.rows}
    assert totals == {"华东": 1500.5, "华南": 2000.0}
    # And the reading is disclosed: the workbook did not hold numbers.
    assert any("余额" in item for item in result.warnings)


def test_cells_that_are_not_numbers_are_reported_not_absorbed():
    path = _book(
        [["华东", "1000"], ["华东", "待补充"], ["华东", ""], ["华南", "500"]],
        ["机构", "余额"],
    )

    async def run():
        return await _source(path).aggregate(
            "excel_acc",
            AggregateRequest(
                sheet_name="台账",
                group_by=["机构"],
                metrics=[AggregateMetric(column="余额", function="sum", alias="余额合计")],
            ),
        )

    result = asyncio.run(run())
    assert {row["机构"]: row["余额合计"] for row in result.rows} == {"华东": 1000.0, "华南": 500.0}
    unconvertible = [item for item in result.warnings if "无法解析" in item]
    assert unconvertible and "待补充" in unconvertible[0]
    # A blank cell is missing data, not a broken number: 3 rows in 华东, one
    # bad value, one empty — only the bad one is counted.
    assert "1 行无法解析" in unconvertible[0]


def test_a_column_with_no_numbers_at_all_fails_loudly():
    path = _book([["华东", "优"], ["华南", "良"]], ["机构", "评级"])

    async def run():
        return await _source(path).aggregate(
            "excel_acc",
            AggregateRequest(
                sheet_name="台账",
                group_by=["机构"],
                metrics=[AggregateMetric(column="评级", function="sum")],
            ),
        )

    try:
        asyncio.run(run())
    except ValueError as exc:
        assert "评级" in str(exc)
    else:  # pragma: no cover - the point of the test
        raise AssertionError("summing a text column must not succeed")


def test_min_and_max_still_work_on_dates_and_text():
    """Only sum and avg are arithmetic; the earliest date is a real answer."""

    path = _book(
        [["华东", "2026-01-05"], ["华东", "2026-02-11"]],
        ["机构", "统计日期"],
    )

    async def run():
        return await _source(path).aggregate(
            "excel_acc",
            AggregateRequest(
                sheet_name="台账",
                group_by=["机构"],
                metrics=[AggregateMetric(column="统计日期", function="min", alias="最早")],
            ),
        )

    result = asyncio.run(run())
    assert str(result.rows[0]["最早"]).startswith("2026-01-05")
    assert result.warnings == []


def test_a_cut_breakdown_says_that_it_was_cut():
    path = _book([[f"网点{index:03d}", index] for index in range(30)], ["网点", "笔数"])

    async def run():
        return await _source(path).aggregate(
            "excel_acc",
            AggregateRequest(
                sheet_name="台账",
                group_by=["网点"],
                metrics=[AggregateMetric(column="笔数", function="sum", alias="笔数合计")],
                limit=10,
            ),
        )

    result = asyncio.run(run())
    assert result.row_count == 10
    assert result.total_groups == 30
    assert result.groups_truncated is True
    assert any("30" in item and "10" in item for item in result.warnings)


def test_an_untruncated_result_claims_nothing():
    path = _book([["华东", 1], ["华南", 2]], ["机构", "笔数"])

    async def run():
        return await _source(path).aggregate(
            "excel_acc",
            AggregateRequest(
                sheet_name="台账",
                group_by=["机构"],
                metrics=[AggregateMetric(column="笔数", function="sum", alias="笔数合计")],
            ),
        )

    result = asyncio.run(run())
    assert result.groups_truncated is False
    assert result.total_groups == result.row_count == 2
    assert result.warnings == []


def test_the_model_is_told_when_the_breakdown_is_partial():
    """The tool's text is what the model reads; the flag alone is not enough."""

    path = _book([[f"网点{index:03d}", index] for index in range(30)], ["网点", "笔数"])
    catalog = DataCatalog()
    catalog.register(_source(path, "excel_tool"))

    async def run():
        tool = AggregateDatasetTool(catalog)
        return await tool.execute(
            ToolContext(request=RequestContext()),
            {
                "dataset_id": "excel_tool",
                "sheet_name": "台账",
                "group_by": ["网点"],
                "metrics": [{"column": "笔数", "function": "sum", "alias": "笔数合计"}],
                "limit": 10,
            },
        )

    result = asyncio.run(run())
    assert result.success
    assert "WARNING" in result.result_for_llm
    assert "30" in result.result_for_llm


def test_grouping_by_several_dimensions_at_once():
    """Multi-dimension grouping is the shape a report keeps asking for."""

    path = _book(
        [
            ["华东", "对公", 100],
            ["华东", "零售", 40],
            ["华东", "对公", 60],
            ["华南", "零售", 25],
        ],
        ["机构", "条线", "余额"],
    )

    async def run():
        return await _source(path).aggregate(
            "excel_acc",
            AggregateRequest(
                sheet_name="台账",
                group_by=["机构", "条线"],
                metrics=[AggregateMetric(column="余额", function="sum", alias="余额合计")],
            ),
        )

    result = asyncio.run(run())
    assert {(row["机构"], row["条线"]): row["余额合计"] for row in result.rows} == {
        ("华东", "对公"): 160,
        ("华东", "零售"): 40,
        ("华南", "零售"): 25,
    }
