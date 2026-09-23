"""The system decides what a question needs; the user just answers it.

A missing metric is either one figure or a list of rows, and which one it is
was being asked of the user at the moment they were least able to say — while
writing SQL, as a mode switch above the editor. It is decided when the question
is raised now, by whoever just tried to read the data. These tests cover the
three parts that makes: the classification, the ways of answering each kind,
and the correction for when the classification is wrong.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.reports import (
    ChapterWriterInput,
    QuestionResolutionInput,
    ReportTemplateSection,
    UserQuestion,
)
from app.core.tabular import MAX_ROWS, TableParseError, parse_table
from app.main import create_app
from app.reporting.chapter_writer_agent import ChapterWriterAgent
from app.reporting.report_generation import ReportGenerationService

from conftest import API, sign_in


def chapter(metrics: list[str], headers: list[list[str]] | None = None) -> ChapterWriterInput:
    blocks: list[dict] = [{"type": "paragraph", "text": "正文"}]
    for header in headers or []:
        blocks.append({"type": "table", "header": header, "rows": []})
    return ChapterWriterInput(
        section=ReportTemplateSection(
            section_id="section_1", title="信贷投放", order=0, template_blocks=blocks
        ),
        metrics=metrics,
        report_outline=["信贷投放"],
    )


# ── what the question needs ───────────────────────────────────────────────

def test_the_model_decides_when_it_says_so():
    """It has just spent a dozen reads on the metric; its word wins."""
    assert ChapterWriterAgent._expectation("不良贷款余额", chapter(["不良贷款余额"]), "table") == "table"
    assert ChapterWriterAgent._expectation("分行明细", chapter(["分行明细"]), "value") == "value"


def test_a_metric_named_in_a_table_header_is_that_table():
    input = chapter(["分行贷款余额"], headers=[["分行", "分行贷款余额", "占比"]])
    assert ChapterWriterAgent._expectation("分行贷款余额", input) == "table"


def test_a_metric_that_reads_as_a_list_is_a_list():
    for metric in ("分行贷款明细", "前十大客户名单", "行业投向分布"):
        assert ChapterWriterAgent._expectation(metric, chapter([metric])) == "table"


def test_anything_else_is_one_figure():
    for metric in ("不良贷款余额", "净息差", "拨备覆盖率"):
        assert ChapterWriterAgent._expectation(metric, chapter([metric])) == "value"


def test_the_kind_that_no_longer_exists_becomes_a_figure():
    """Sessions stored before the kinds were settled still have to load."""
    question = UserQuestion.model_validate(
        {"question_id": "q1", "content": "缺数据", "expected": "dataset"}
    )
    assert question.expected == "value"


# ── reading what the user pasted ──────────────────────────────────────────

def test_several_metrics_at_once():
    """The shape a user reaches for when they have the figures in hand."""
    parsed = parse_table("不良贷款余额：52,501,109.06 元\n不良率: 1.28%\n拨备覆盖率 = 320%")
    assert parsed.columns == ["指标", "取值"]
    assert parsed.rows[0] == {"指标": "不良贷款余额", "取值": "52,501,109.06 元"}
    assert parsed.row_count == 3


def test_a_block_copied_out_of_excel():
    parsed = parse_table("机构\t余额\t占比\n华东\t1200\t60%\n华南\t800\t40%")
    assert parsed.columns == ["机构", "余额", "占比"]
    assert parsed.rows[1]["占比"] == "40%"


def test_a_markdown_table_from_another_document():
    parsed = parse_table("| 机构 | 余额 |\n|---|---:|\n| 华东 | 1200 |\n| 华南 | 800 |")
    assert parsed.columns == ["机构", "余额"]
    assert parsed.row_count == 2


def test_commas_and_spaces_both_work():
    assert parse_table("机构,余额\n华东,1200").columns == ["机构", "余额"]
    assert parse_table("机构    余额\n华东    1200").columns == ["机构", "余额"]


def test_a_ragged_paste_is_aligned_and_the_repair_is_disclosed():
    parsed = parse_table("机构\t余额\n华东\t1200\t多余的一列\n华南")
    assert parsed.rows == [{"机构": "华东", "余额": "1200"}, {"机构": "华南", "余额": ""}]
    assert any("列数" in item for item in parsed.warnings)


def test_more_rows_than_a_chapter_may_carry():
    parsed = parse_table("a\tb\n" + "\n".join(f"{i}\t{i}" for i in range(MAX_ROWS + 50)))
    assert parsed.row_count == MAX_ROWS
    assert parsed.truncated and parsed.warnings


def test_prose_is_not_a_table():
    for text in ("", "   ", "这一章的数据我回头再补给你"):
        with pytest.raises(TableParseError):
            parse_table(text)


def test_a_header_with_no_rows_says_so():
    with pytest.raises(TableParseError) as exc:
        parse_table("机构\t余额")
    assert "表头" in str(exc.value)


# ── how a question gets answered ──────────────────────────────────────────

def test_a_list_question_takes_the_rows_the_user_pasted():
    question = UserQuestion(
        question_id="q1", metric="分行明细", expected="table", content="缺分行字段"
    )
    ReportGenerationService._resolve_by_paste(
        question,
        QuestionResolutionInput(
            question_id="q1",
            action="table",
            text="分行\t余额\n上海\t1200\n北京\t800",
            note="含贴现",
        ),
    )
    assert question.resolution == "table"
    assert question.columns == ["分行", "余额"]
    assert question.rows[0] == {"分行": "上海", "余额": "1200"}
    # A pasted list is not a figure: nothing must be able to read one out of it.
    assert question.value is None
    assert question.note == "含贴现"


def test_an_unreadable_paste_is_rejected_with_something_to_do_about_it():
    question = UserQuestion(question_id="q1", expected="table", content="缺明细")
    with pytest.raises(Exception) as exc:
        ReportGenerationService._resolve_by_paste(
            question,
            QuestionResolutionInput(question_id="q1", action="table", text="回头补"),
        )
    assert "Excel" in str(exc.value) or "指标" in str(exc.value)
    assert question.resolution == "pending"


def test_the_question_decides_how_a_query_is_read():
    figure = UserQuestion(question_id="q1", metric="不良率", expected="value", content="缺")
    rows = UserQuestion(question_id="q2", metric="分行明细", expected="table", content="缺")
    plain = QuestionResolutionInput(question_id="q1", action="sql", query="SELECT 1")
    assert ReportGenerationService._shape_for(figure, plain) == "value"
    assert ReportGenerationService._shape_for(rows, plain) == "table"


def test_a_figure_question_can_be_corrected_to_a_list():
    """The escape hatch: we classified it wrongly and the user says so, once,
    on the question it actually happened on."""
    figure = UserQuestion(question_id="q1", metric="不良率", expected="value", content="缺")
    corrected = QuestionResolutionInput(
        question_id="q1", action="sql", query="SELECT 1", as_table=True
    )
    assert ReportGenerationService._shape_for(figure, corrected) == "table"


# ── the preview the user checks before submitting ─────────────────────────

@pytest.fixture
def client():
    app = create_app()
    sign_in(app)
    with TestClient(app) as test_client:
        yield test_client


def test_preview_returns_the_table_the_paste_would_become(client):
    response = client.post(
        f"{API}/supplements/preview",
        json={"text": "机构\t余额\n华东\t1200\n华南\t800"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == ["机构", "余额"]
    assert body["row_count"] == 2
    assert body["format"]


def test_preview_explains_a_paste_it_cannot_read(client):
    response = client.post(f"{API}/supplements/preview", json={"text": "回头补给你"})
    assert response.status_code == 400
    assert "Excel" in response.json()["detail"]


def test_preview_is_closed_to_anonymous_callers():
    app = create_app()  # no sign_in
    with TestClient(app) as anonymous:
        response = anonymous.post(f"{API}/supplements/preview", json={"text": "a\tb\n1\t2"})
    assert response.status_code in {401, 403}
