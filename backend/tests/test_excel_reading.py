import asyncio
import tempfile
from pathlib import Path

from openpyxl import Workbook

from app.core.models import DataReadRequest
from app.data.catalog import DataCatalog
from app.data.sources.excel import ExcelDataSource


def make_workbook(path):
    workbook = Workbook()
    first = workbook.active
    first.title = "销售明细"
    first.append(["客户", "金额", "日期"])
    first.append(["张三", 100, "2026-01-01"])
    first.append(["李四", 200, "2026-01-02"])
    first.append(["张三", 300, "2026-01-03"])
    second = workbook.create_sheet("说明")
    second.append(["内容"])
    second.append(["测试模板"])
    workbook.save(path)


def test_openpyxl_excel_reading_and_catalog_access():
    async def run():
        path = Path(tempfile.mkdtemp()) / "sales.xlsx"
        make_workbook(path)
        source = ExcelDataSource(path, "excel_test", "sales.xlsx")
        catalog = DataCatalog()
        catalog.register(source)

        sheets = await catalog.sheets("excel_test")
        assert [sheet.sheet_name for sheet in sheets] == ["销售明细", "说明"]
        assert sheets[0].row_count == 3

        result = await catalog.read_rows(
            "excel_test",
            "销售明细",
            columns=["客户", "金额"],
            filters={"客户": "张三"},
            offset=1,
            limit=1,
        )
        assert result.columns == ["客户", "金额"]
        assert result.rows == [{"客户": "张三", "金额": 300}]
        assert result.has_more is False

        profile = await catalog.profile("excel_test")
        assert profile.dataset.row_count == 3
        assert profile.distinct_values["客户"] == 2

    asyncio.run(run())


def test_read_request_validates_pagination():
    request = DataReadRequest(sheet_name="销售明细", limit=20, offset=5)
    assert request.limit == 20
    assert request.offset == 5
