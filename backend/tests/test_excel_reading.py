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


def test_a_dataset_registered_by_an_earlier_run_is_recovered_on_demand():
    """Sessions outlive the process; the in-memory catalog does not."""
    from app.data.catalog import DataCatalog
    from app.data.sources.excel import ExcelDataSource

    directory = Path(tempfile.mkdtemp())
    path = directory / "excel_abc123_data.xlsx"
    workbook = Workbook()
    workbook.active.append(["value"])
    workbook.active.append([1])
    workbook.save(path)

    looked_up: list[str] = []

    def restore(dataset_id: str):
        looked_up.append(dataset_id)
        found = next(directory.glob(f"{dataset_id}_*"), None)
        if found is None:
            return None
        return ExcelDataSource(path=found, dataset_id=dataset_id, name=found.name)

    catalog = DataCatalog(restore=restore)
    source = catalog.get_source("excel_abc123")

    assert source is not None
    assert looked_up == ["excel_abc123"]
    # Recovered once, then served from memory.
    assert catalog.get_source("excel_abc123") is source
    assert looked_up == ["excel_abc123"]

    try:
        catalog.get_source("excel_missing")
    except KeyError as exc:
        assert "excel_missing" in str(exc)
    else:
        raise AssertionError("未知数据集仍应报错")
