"""A report planned in conversation, with no template and no data.

The user describes what they want; the model proposes a structure; they refine
it by talking; the agreed outline becomes the template the rest of the pipeline
reads. From confirmation onward this is the template-only flow.
"""

import asyncio
import json

import pytest

from app.core.ports import LlmService
from app.core.reports import (
    ChapterPlan,
    CreateReportGenerationRequest,
    ReportGenerationStatus,
    SubchapterPlan,
    group_template_chapters,
    synthesize_template,
)
from app.data.catalog import DataCatalog
from app.infrastructure.artifact_store import InMemoryArtifactStore
from app.infrastructure.report_repositories import (
    InMemoryReportSessionRepository,
    InMemoryReportTemplateRepository,
)
from app.reporting.assembler import ReportAssembler
from app.reporting.chapter_writer import StubChapterWriter
from app.reporting.planner import ReportPlanner
from app.reporting.renderer import MarkdownReportRenderer
from app.reporting.report_generation import ReportGenerationService
from app.reporting.template_parser import ReportTemplateParser


class ScriptedLlm(LlmService):
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def complete(self, messages, tools):
        self.calls.append((list(messages), tools))
        return {"content": self.responses.pop(0), "tool_calls": []}


OUTLINE = json.dumps(
    {
        "title": "公司金融业务经营分析报告",
        "global_context": {"report_period": "2026年上半年", "dimensions": {}},
        "chapters": [
            {"title": "一、经营概况", "metrics": ["累计交易金额", "交易笔数"],
             "subsections": [{"title": "1.1 整体规模"}]},
            {"title": "二、资产质量", "metrics": ["不良贷款率"], "subsections": []},
        ],
    },
    ensure_ascii=False,
)


def build_service(llm):
    return ReportGenerationService(
        sessions=InMemoryReportSessionRepository(),
        templates=InMemoryReportTemplateRepository(),
        template_parser=ReportTemplateParser(),
        planner=ReportPlanner(llm=llm),
        writer=StubChapterWriter(),
        assembler=ReportAssembler(),
        renderer=MarkdownReportRenderer(),
        artifact_store=InMemoryArtifactStore(),
        catalog=DataCatalog(),
    )


async def planned(llm):
    service = build_service(llm)
    session = await service.create_session(
        CreateReportGenerationRequest(instruction="生成一份公司金融业务经营分析报告"),
        user_id="local-user",
    )
    return service, session


def test_a_sentence_alone_produces_a_plan():
    async def run():
        _, session = await planned(ScriptedLlm([OUTLINE]))
        assert session.status == ReportGenerationStatus.AWAITING_CONFIRMATION
        assert session.dataset_ids == []
        assert [c.title for c in session.plan.chapters] == ["一、经营概况", "二、资产质量"]
        assert session.plan.chapters[0].metrics == ["累计交易金额", "交易笔数"]
        assert session.plan.global_context.report_period == "2026年上半年"

    asyncio.run(run())


def test_the_agreed_outline_becomes_a_template():
    """Everything downstream keys on section_id and reads levels from a
    template, so a conversation-authored report needs one of its own."""

    async def run():
        _, session = await planned(ScriptedLlm([OUTLINE]))
        snapshot = session.template_snapshot
        assert snapshot is not None
        assert snapshot.metadata["synthesized"] is True
        assert session.template_id and session.plan.template_id == session.template_id
        # It reads back as the same chapter tree the plan describes.
        tree = group_template_chapters(snapshot.sections)
        assert [c.root.title for c in tree] == ["一、经营概况", "二、资产质量"]
        assert [i.title for i in tree[0].subsections] == ["1.1 整体规模"]
        # No prose and no table columns: nothing was copied from a document.
        assert all(not s.template_blocks for s in snapshot.sections)

    asyncio.run(run())


def test_a_revision_may_add_a_chapter():
    """With a template the chapter set is fixed and a new id is an error. Here
    the conversation decides the structure, so adding one is the point."""

    async def run():
        revised = json.dumps(
            {
                "title": "公司金融业务经营分析报告",
                "global_context": {"report_period": "2026年上半年", "dimensions": {}},
                "chapters": [
                    {"title": "一、经营概况", "metrics": ["累计交易金额", "交易笔数"],
                     "subsections": [{"title": "1.1 整体规模"}]},
                    {"title": "二、资产质量", "metrics": ["不良贷款率"], "subsections": []},
                    {"title": "三、风险分析", "metrics": ["风险敞口"], "subsections": []},
                ],
            },
            ensure_ascii=False,
        )
        service, session = await planned(ScriptedLlm([OUTLINE, revised]))
        after = await service.revise_plan(session.session_id, "再加一章风险分析")

        assert [c.title for c in after.plan.chapters] == ["一、经营概况", "二、资产质量", "三、风险分析"]
        assert after.plan.version == 2
        # The template is rebuilt from the plan, so it cannot lag behind it.
        stored = await service.sessions.get(session.session_id)
        tree = group_template_chapters(stored.template_snapshot.sections)
        assert [c.root.title for c in tree] == ["一、经营概况", "二、资产质量", "三、风险分析"]

    asyncio.run(run())


def test_a_chapter_that_survives_a_revision_keeps_its_id():
    """Answers and drafts are filed under section_id, so renumbering the
    chapters on every revision would strand them."""

    async def run():
        dropped = json.dumps(
            {
                "title": "公司金融业务经营分析报告",
                "global_context": {"report_period": "2026年上半年", "dimensions": {}},
                "chapters": [
                    {"title": "二、资产质量", "metrics": ["不良贷款率"], "subsections": []},
                ],
            },
            ensure_ascii=False,
        )
        service, session = await planned(ScriptedLlm([OUTLINE, dropped]))
        before = {c.title: c.section_id for c in session.plan.chapters}
        after = await service.revise_plan(session.session_id, "去掉经营概况那章")

        assert [c.title for c in after.plan.chapters] == ["二、资产质量"]
        assert after.plan.chapters[0].section_id == before["二、资产质量"]

    asyncio.run(run())


def test_planning_without_a_template_needs_a_model():
    """There is no structure to fall back on when nothing was uploaded."""

    async def run():
        service = build_service(None)
        with pytest.raises(ValueError, match="model"):
            await service.create_session(
                CreateReportGenerationRequest(instruction="生成一份报告"),
                user_id="local-user",
            )

    asyncio.run(run())


def test_synthesis_numbers_sections_in_reading_order():
    template = synthesize_template(
        "tpl_1",
        "报告",
        [
            ChapterPlan(section_id="s1", title="一、概况", metrics=[],
                        subsections=[SubchapterPlan(section_id="s1_1", title="1.1 规模")]),
            ChapterPlan(section_id="s2", title="二、风险", metrics=[]),
        ],
    )
    assert [(s.section_id, s.level, s.order) for s in template.sections] == [
        ("s1", 1, 0), ("s1_1", 2, 1), ("s2", 1, 2),
    ]


DATA_OUTLINE = json.dumps(
    {
        "title": "交易数据分析报告",
        "global_context": {"report_period": "2026年上半年", "dimensions": {"区域": ["华东", "华南"]}},
        "chapters": [
            {"title": "一、交易总体情况", "metrics": ["交易金额", "交易笔数"], "subsections": []},
        ],
    },
    ensure_ascii=False,
)


def test_a_spreadsheet_alone_plans_against_its_own_columns():
    """The most useful shape of all: the model proposes the report, and every
    figure in it is still read rather than asked for. Planning blind against
    real data would name metrics the columns cannot answer, and each one would
    become a question the user fills in by hand."""

    async def run():
        from pathlib import Path
        import tempfile
        from openpyxl import Workbook
        from app.data.sources.excel import ExcelDataSource

        path = Path(tempfile.mkdtemp()) / "data.xlsx"
        book = Workbook()
        book.active.title = "月度汇总"
        book.active.append(["统计月份", "区域", "交易金额", "交易笔数"])
        book.active.append(["2026-01", "华东", 100, 3])
        book.save(path)

        llm = ScriptedLlm([DATA_OUTLINE])
        service = build_service(llm)
        service.catalog.register(ExcelDataSource(path, "excel_1", "data.xlsx"))
        session = await service.create_session(
            CreateReportGenerationRequest(
                dataset_ids=["excel_1"], instruction="分析一下这份交易数据"
            ),
            user_id="local-user",
        )

        assert session.status == ReportGenerationStatus.AWAITING_CONFIRMATION
        assert session.dataset_ids == ["excel_1"]
        # The outline still becomes a template, exactly as it does with no data.
        assert session.template_snapshot.metadata["synthesized"] is True

        # What the model was shown: the real columns, not just the sentence.
        planning_prompt = llm.calls[0][0][-1]["content"]
        assert "交易金额" in planning_prompt and "月度汇总" in planning_prompt
        system = llm.calls[0][0][0]["content"]
        assert "value_enums" in system
        assert "数据答不上来的指标" in system

    asyncio.run(run())


def test_planning_with_no_data_does_not_point_at_columns():
    """The same call with nothing uploaded must not tell the model to consult
    enumerated values that are not there, or invent a reporting period."""

    async def run():
        llm = ScriptedLlm([OUTLINE])
        service = build_service(llm)
        await service.create_session(
            CreateReportGenerationRequest(instruction="生成一份公司金融业务经营分析报告"),
            user_id="local-user",
        )
        system = llm.calls[0][0][0]["content"]
        assert "value_enums" not in system
        assert "逐项向用户收集" in system
        assert "不要自己假定一个期间" in system

    asyncio.run(run())
