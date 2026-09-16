"""A template's heading hierarchy must survive planning, generation and rendering."""

import asyncio
import json
import tempfile
from pathlib import Path

from openpyxl import Workbook

from app.core.ports import LlmService
from app.core.reports import (
    QuestionResolutionInput,
    ResolveQuestionsRequest,
    ChapterWriterInput,
    ChapterWriterResult,
    ChapterDraft,
    CreateReportGenerationRequest,
    ReportGenerationStatus,
    ReportTemplateSection,
    UserQuestion,
    group_template_chapters,
)
from app.data.catalog import DataCatalog
from app.data.sources.excel import ExcelDataSource
from app.infrastructure.artifact_store import InMemoryArtifactStore
from app.infrastructure.report_repositories import (
    InMemoryReportSessionRepository,
    InMemoryReportTemplateRepository,
)
from app.reporting.assembler import ReportAssembler
from app.reporting.chapter_writer import ChapterWriter, StubChapterWriter
from app.reporting.planner import ReportPlanner
from app.reporting.renderer import MarkdownReportRenderer
from app.reporting.report_generation import ReportGenerationService
from app.reporting.template_parser import ReportTemplateParser

NESTED_TEMPLATE = """# 经营分析报告

开篇说明段落。

## 一、经营概况
概况正文

### 1.1 对公业务
对公正文

### 1.2 零售业务
零售正文

## 二、风险情况
风险正文
""".encode()


def section(section_id: str, title: str, level: int, order: int, **extra) -> ReportTemplateSection:
    return ReportTemplateSection(section_id=section_id, title=title, level=level, order=order, **extra)


def test_grouping_uses_heading_levels_not_the_preamble():
    # A template whose real headings start at H2 must not be swallowed by the
    # synthetic level-1 preamble section.
    grouped = group_template_chapters([
        section("s0", "正文", 1, 0, metadata={"preamble": True}),
        section("s1", "二、经营分析", 2, 1),
        section("s2", "2.1 对公", 3, 2),
        section("s3", "2.2 零售", 3, 3),
        section("s4", "三、风险", 2, 4),
    ])
    assert [chapter.root.title for chapter in grouped] == ["正文", "二、经营分析", "三、风险"]
    assert [item.title for item in grouped[1].subsections] == ["2.1 对公", "2.2 零售"]


def test_grouping_nests_deeper_headings_under_their_chapter():
    grouped = group_template_chapters([
        section("s1", "一、经营", 1, 0),
        section("s2", "1.1 对公", 2, 1),
        section("s3", "1.1.1 绿色信贷", 3, 2),
        section("s4", "二、风险", 1, 3),
    ])
    assert [chapter.root.title for chapter in grouped] == ["一、经营", "二、风险"]
    assert [item.title for item in grouped[0].subsections] == ["1.1 对公", "1.1.1 绿色信贷"]


def excel_bytes() -> bytes:
    path = Path(tempfile.mkdtemp()) / "data.xlsx"
    workbook = Workbook()
    workbook.active.append(["value"])
    workbook.active.append([1])
    workbook.save(path)
    return path.read_bytes()


class RecordingWriter(ChapterWriter):
    """Captures what each chapter run was handed."""

    def __init__(self) -> None:
        self.inputs: list[ChapterWriterInput] = []

    async def write(self, input: ChapterWriterInput, session, checkpoint=None) -> ChapterWriterResult:
        self.inputs.append(input)
        body = "章节正文。"
        for item in input.subsections:
            depth = max(1, item.level - input.section.level)
            body += f"\n\n{'#' * (2 + depth)} {item.title}\n\n子节正文。"
        return ChapterWriterResult(
            status="completed",
            draft=ChapterDraft(
                chapter_id=input.section.section_id,
                section_id=input.section.section_id,
                title=input.section.title,
                content=body,
            ),
        )


def build_service(writer: ChapterWriter | None = None, llm: LlmService | None = None):
    return ReportGenerationService(
        sessions=InMemoryReportSessionRepository(),
        templates=InMemoryReportTemplateRepository(),
        template_parser=ReportTemplateParser(),
        planner=ReportPlanner(llm=llm),
        writer=writer or StubChapterWriter(),
        assembler=ReportAssembler(),
        renderer=MarkdownReportRenderer(),
        artifact_store=InMemoryArtifactStore(),
        catalog=DataCatalog(),
    )


async def registered_dataset(service, dataset_id: str) -> str:
    path = Path(tempfile.mkdtemp()) / "data.xlsx"
    path.write_bytes(excel_bytes())
    service.catalog.register(ExcelDataSource(path, dataset_id, "data.xlsx"))
    return dataset_id


def test_plan_chapters_carry_their_subsections():
    async def run():
        service = build_service()
        template = await service.upload_template("t.md", NESTED_TEMPLATE, "text/markdown")
        await registered_dataset(service, "excel_tree_1")

        session = await service.create_session(
            CreateReportGenerationRequest(
                template_id=template.template_id, dataset_ids=["excel_tree_1"], instruction="生成"
            ),
            user_id="local-user",
        )

        chapters = session.plan.chapters
        # The leading body text stays its own chapter; the two H2 headings each
        # own their H3 subsections.
        assert [chapter.title for chapter in chapters] == ["正文", "一、经营概况", "二、风险情况"]
        assert [item.title for item in chapters[1].subsections] == ["1.1 对公业务", "1.2 零售业务"]
        assert chapters[1].level == 2 and chapters[1].subsections[0].level == 3
        assert chapters[0].subsections == [] and chapters[2].subsections == []

    asyncio.run(run())


def test_one_agent_run_per_chapter_not_per_heading():
    async def run():
        writer = RecordingWriter()
        service = build_service(writer)
        template = await service.upload_template("t.md", NESTED_TEMPLATE, "text/markdown")
        await registered_dataset(service, "excel_tree_2")

        session = await service.create_session(
            CreateReportGenerationRequest(
                template_id=template.template_id,
                dataset_ids=["excel_tree_2"],
                instruction="生成",
                auto_start=True,
            ),
            user_id="local-user",
        )

        assert session.status == ReportGenerationStatus.COMPLETED
        # Five sections, three chapters: the H3s do not get their own agent run.
        assert len(writer.inputs) == 3
        assert [item.title for item in writer.inputs[1].subsections] == ["1.1 对公业务", "1.2 零售业务"]
        assert writer.inputs[2].subsections == []
        assert len(session.chapter_drafts) == 3

        artifact, content = await service.get_artifact(
            session.session_id, session.artifacts[0].artifact_id
        )
        markdown = content.decode("utf-8")
        assert "## 一、经营概况" in markdown
        assert "### 1.1 对公业务" in markdown
        assert "### 1.2 零售业务" in markdown
        # The chapter heading is written once, by the renderer.
        assert markdown.count("## 一、经营概况") == 1

    asyncio.run(run())


def test_revision_dropping_a_chapter_drops_its_subsections():
    async def run():
        planner = ReportPlanner(llm=None)
        service = build_service()
        template = await service.upload_template("t.md", NESTED_TEMPLATE, "text/markdown")
        await registered_dataset(service, "excel_tree_3")
        session = await service.create_session(
            CreateReportGenerationRequest(
                template_id=template.template_id, dataset_ids=["excel_tree_3"], instruction="生成"
            ),
            user_id="local-user",
        )

        # A revision that keeps only the second chapter must not leave the
        # first chapter's subsections orphaned in the plan.
        revised = planner._parse_plan_payload(
            {
                "title": "报告",
                "global_context": {"report_period": None, "dimensions": {}},
                "chapters": [{"section_id": "section_5", "title": "二、风险情况", "metrics": []}],
            },
            session.template_snapshot,
            require_every_section=False,
        )
        chapters = revised[0]
        assert [chapter.section_id for chapter in chapters] == ["section_5"]
        dropped = {"section_3", "section_4"}
        assert all(item.section_id not in dropped for chapter in chapters for item in chapter.subsections)

    asyncio.run(run())


def test_a_subsection_cannot_be_planned_under_the_wrong_chapter():
    async def run():
        planner = ReportPlanner(llm=None)
        service = build_service()
        template = await service.upload_template("t.md", NESTED_TEMPLATE, "text/markdown")
        await registered_dataset(service, "excel_tree_4")
        session = await service.create_session(
            CreateReportGenerationRequest(
                template_id=template.template_id, dataset_ids=["excel_tree_4"], instruction="生成"
            ),
            user_id="local-user",
        )

        try:
            planner._parse_plan_payload(
                {
                    "title": "报告",
                    "global_context": {"report_period": None, "dimensions": {}},
                    "chapters": [
                        {
                            "section_id": "section_5",
                            "title": "二、风险情况",
                            "metrics": [],
                            "subsections": [{"section_id": "section_3", "title": "1.1 对公业务"}],
                        }
                    ],
                },
                session.template_snapshot,
                require_every_section=False,
            )
        except ValueError as exc:
            assert "outside its chapter" in str(exc)
        else:
            raise AssertionError("a misplaced subsection must be rejected")

    asyncio.run(run())


class AskingWriter(ChapterWriter):
    """Asks for a missing metric on the first attempt at the named chapters."""

    def __init__(self, ask_for: dict[str, str]) -> None:
        self.ask_for = dict(ask_for)
        self.attempts: list[str] = []

    async def write(self, input: ChapterWriterInput, session, checkpoint=None) -> ChapterWriterResult:
        section_id = input.section.section_id
        self.attempts.append(section_id)
        metric = self.ask_for.pop(section_id, None)
        if metric is not None:
            return ChapterWriterResult(
                status="waiting_user",
                questions=[
                    UserQuestion(
                        question_id=f"q_{section_id}",
                        metric=metric,
                        expected="value",
                        content=f"请补充{metric}",
                    )
                ],
            )
        return ChapterWriterResult(
            status="completed",
            draft=ChapterDraft(
                chapter_id=section_id,
                section_id=section_id,
                title=input.section.title,
                content="正文",
            ),
        )


def test_a_chapter_short_on_data_stops_the_run_at_that_chapter():
    async def run():
        writer = AskingWriter({"section_2": "2025年同期交易金额"})
        service = build_service(writer)
        template = await service.upload_template("t.md", NESTED_TEMPLATE, "text/markdown")
        await registered_dataset(service, "excel_ask_1")
        session = await service.create_session(
            CreateReportGenerationRequest(
                template_id=template.template_id,
                dataset_ids=["excel_ask_1"],
                instruction="生成",
                auto_start=True,
            ),
            user_id="local-user",
        )

        # A chapter is written only once its data is settled, so the run stops
        # here instead of starting the chapter that follows.
        assert writer.attempts == ["section_1", "section_2"]
        assert session.status == ReportGenerationStatus.WAITING_USER
        assert session.current_step == "await_supplements"
        assert set(session.chapter_drafts) == {"section_1"}
        assert session.current_chapter_id == "section_2"

        question = session.pending_questions[0]
        assert question.chapter_id == "section_2"
        assert question.chapter_title == "一、经营概况"
        assert question.metric == "2025年同期交易金额"
        assert session.assembled_report is None

    asyncio.run(run())


def test_answering_finishes_that_chapter_then_continues_to_the_next():
    async def run():
        writer = AskingWriter({"section_2": "2025年同期交易金额"})
        service = build_service(writer)
        template = await service.upload_template("t.md", NESTED_TEMPLATE, "text/markdown")
        await registered_dataset(service, "excel_ask_2")
        session = await service.create_session(
            CreateReportGenerationRequest(
                template_id=template.template_id,
                dataset_ids=["excel_ask_2"],
                instruction="生成",
                auto_start=True,
            ),
            user_id="local-user",
        )

        resumed = await service.resolve_questions(
            session.session_id,
            ResolveQuestionsRequest(
                resolutions=[
                    QuestionResolutionInput(
                        question_id="q_section_2", action="value", value="76400"
                    )
                ]
            ),
        )

        assert resumed.status == ReportGenerationStatus.COMPLETED
        assert set(resumed.chapter_drafts) == {"section_1", "section_2", "section_5"}
        assert resumed.pending_questions == []
        # section_2 is retried and only then does section_5 start; the chapter
        # that already had a draft is not regenerated.
        assert writer.attempts == ["section_1", "section_2", "section_2", "section_5"]

    asyncio.run(run())


def test_the_chapter_in_progress_is_observable_while_it_runs():
    async def run():
        service = build_service()
        template = await service.upload_template("t.md", NESTED_TEMPLATE, "text/markdown")
        await registered_dataset(service, "excel_live_1")
        session = await service.create_session(
            CreateReportGenerationRequest(
                template_id=template.template_id, dataset_ids=["excel_live_1"], instruction="生成"
            ),
            user_id="local-user",
        )
        seen: list[str | None] = []

        class ObservingWriter(ChapterWriter):
            async def write(self, input, session_arg, checkpoint=None) -> ChapterWriterResult:
                # What a poller would read from storage mid-chapter.
                stored = await service.sessions.get(session_arg.session_id)
                seen.append(stored.current_chapter_id)
                return ChapterWriterResult(
                    status="completed",
                    draft=ChapterDraft(
                        chapter_id=input.section.section_id,
                        section_id=input.section.section_id,
                        title=input.section.title,
                        content="正文",
                    ),
                )

        service.writer = ObservingWriter()
        await service.approve_plan(session.session_id)
        assert seen == ["section_1", "section_2", "section_5"]

    asyncio.run(run())


class TwoQuestionWriter(ChapterWriter):
    """Asks for two metrics on the first attempt at one chapter."""

    def __init__(self, section_id: str) -> None:
        self.section_id = section_id
        self.asked = False
        self.inputs: list[ChapterWriterInput] = []

    async def write(self, input: ChapterWriterInput, session, checkpoint=None) -> ChapterWriterResult:
        self.inputs.append(input)
        if input.section.section_id == self.section_id and not self.asked:
            self.asked = True
            return ChapterWriterResult(
                status="waiting_user",
                questions=[
                    UserQuestion(question_id="q_yoy", metric="同比增速", expected="value", content="缺同期数据"),
                    UserQuestion(question_id="q_branch", metric="分行明细", expected="dataset", content="缺分行字段"),
                ],
            )
        return ChapterWriterResult(
            status="completed",
            draft=ChapterDraft(
                chapter_id=input.section.section_id,
                section_id=input.section.section_id,
                title=input.section.title,
                content="正文",
            ),
        )


async def build_waiting_session(service, writer, dataset_id: str):
    template = await service.upload_template("t.md", NESTED_TEMPLATE, "text/markdown")
    await registered_dataset(service, dataset_id)
    session = await service.create_session(
        CreateReportGenerationRequest(
            template_id=template.template_id,
            dataset_ids=[dataset_id],
            instruction="生成",
            auto_start=True,
        ),
        user_id="local-user",
    )
    return session


def test_a_chapter_resumes_only_after_every_question_is_settled():
    async def run():
        writer = TwoQuestionWriter("section_2")
        service = build_service(writer)
        session = await build_waiting_session(service, writer, "excel_res_1")
        assert len(session.pending_questions) == 2

        # Settling one of two leaves the chapter waiting: the chapter is
        # rewritten only once nothing about it is open.
        partial = await service.resolve_questions(
            session.session_id,
            ResolveQuestionsRequest(
                resolutions=[QuestionResolutionInput(question_id="q_yoy", action="value", value="76400")]
            ),
        )
        assert partial.status == ReportGenerationStatus.WAITING_USER
        assert [item.question_id for item in partial.pending_questions] == ["q_branch"]
        assert set(partial.chapter_drafts) == {"section_1"}

        done = await service.resolve_questions(
            session.session_id,
            ResolveQuestionsRequest(
                resolutions=[QuestionResolutionInput(question_id="q_branch", action="drop")]
            ),
        )
        assert done.status == ReportGenerationStatus.COMPLETED
        assert set(done.chapter_drafts) == {"section_1", "section_2", "section_5"}

    asyncio.run(run())


def test_a_dropped_metric_leaves_the_plan_and_reaches_the_writer_as_dropped():
    async def run():
        writer = TwoQuestionWriter("section_2")
        service = build_service(writer)
        session = await build_waiting_session(service, writer, "excel_res_2")
        planned = next(c for c in session.plan.chapters if c.section_id == "section_2")
        planned.metrics = ["同比增速", "分行明细", "交易金额"]
        await service.sessions.save(session)

        resumed = await service.resolve_questions(
            session.session_id,
            ResolveQuestionsRequest(
                resolutions=[
                    QuestionResolutionInput(question_id="q_yoy", action="drop"),
                    QuestionResolutionInput(question_id="q_branch", action="value", value="见附表"),
                ]
            ),
        )

        # The metric is gone from the plan, not merely marked.
        chapter = next(c for c in resumed.plan.chapters if c.section_id == "section_2")
        assert "同比增速" not in chapter.metrics
        assert "交易金额" in chapter.metrics
        assert resumed.dropped_metrics["section_2"] == ["同比增速"]

        rewritten = [item for item in writer.inputs if item.section.section_id == "section_2"][-1]
        assert rewritten.dropped_metrics == ["同比增速"]
        assert [(s.metric, s.value) for s in rewritten.supplements] == [("分行明细", "见附表")]

    asyncio.run(run())


def test_sql_supplements_are_refused_until_the_data_source_page_exists():
    async def run():
        writer = TwoQuestionWriter("section_2")
        service = build_service(writer)
        session = await build_waiting_session(service, writer, "excel_res_3")
        try:
            await service.resolve_questions(
                session.session_id,
                ResolveQuestionsRequest(
                    resolutions=[
                        QuestionResolutionInput(
                            question_id="q_branch", action="sql", dataset_id="sql_x", query="select 1"
                        )
                    ]
                ),
            )
        except ValueError as exc:
            assert "尚未开放" in str(exc)
        else:
            raise AssertionError("SQL 补充当前应被拒绝")

    asyncio.run(run())


def test_a_chapter_past_its_ask_limit_drops_the_metric_instead_of_killing_the_report():
    """The user answered every round it was allowed to ask. Killing the whole
    report at that point throws away the chapters that did work."""

    async def run():
        class AsksUntilDropped(ChapterWriter):
            async def write(self, input, session, checkpoint=None) -> ChapterWriterResult:
                if input.section.section_id == "section_2" and "X" not in input.dropped_metrics:
                    return ChapterWriterResult(
                        status="waiting_user",
                        questions=[UserQuestion(question_id="q_loop", metric="X", content="还是缺")],
                    )
                return ChapterWriterResult(
                    status="completed",
                    draft=ChapterDraft(
                        chapter_id=input.section.section_id,
                        section_id=input.section.section_id,
                        title=input.section.title,
                        content="正文",
                    ),
                )

        service = build_service(AsksUntilDropped())
        service.max_chapter_attempts = 2
        session = await build_waiting_session(service, None, "excel_res_4")

        for _ in range(2):
            if session.status != ReportGenerationStatus.WAITING_USER:
                break
            session = await service.resolve_questions(
                session.session_id,
                ResolveQuestionsRequest(
                    resolutions=[
                        QuestionResolutionInput(question_id="q_loop", action="value", value="1")
                    ]
                ),
            )

        assert session.status == ReportGenerationStatus.COMPLETED
        assert "section_2" in session.chapter_drafts
        assert session.dropped_metrics["section_2"] == ["X"]
        # The give-up is on the record, which is how the user gets told.
        given_up = [
            item for item in session.resolved_questions
            if item.resolution == "dropped" and item.note and "已自动移出报告" in item.note
        ]
        assert [item.metric for item in given_up] == ["X"]

    asyncio.run(run())


def test_a_chapter_still_asking_after_the_drop_parks_rather_than_failing():
    """Dropping is the last lever; if it does not settle the chapter the run
    waits for the user instead of destroying the session."""

    async def run():
        class NeverSatisfiedWriter(ChapterWriter):
            async def write(self, input, session, checkpoint=None) -> ChapterWriterResult:
                if input.section.section_id == "section_2":
                    return ChapterWriterResult(
                        status="waiting_user",
                        questions=[UserQuestion(question_id="q_loop", metric="X", content="还是缺")],
                    )
                return ChapterWriterResult(
                    status="completed",
                    draft=ChapterDraft(
                        chapter_id=input.section.section_id,
                        section_id=input.section.section_id,
                        title=input.section.title,
                        content="正文",
                    ),
                )

        service = build_service(NeverSatisfiedWriter())
        service.max_chapter_attempts = 2
        session = await build_waiting_session(service, None, "excel_res_5")

        for _ in range(3):
            session = await service.resolve_questions(
                session.session_id,
                ResolveQuestionsRequest(
                    resolutions=[
                        QuestionResolutionInput(question_id="q_loop", action="value", value="1")
                    ]
                ),
            )

        assert session.status == ReportGenerationStatus.WAITING_USER
        assert session.error is None



NESTED_THREE_LEVEL = """# 报告

前言段落。

## 一、经营概况
概况正文

### 1.1 整体规模
规模正文

### 1.2 区域分布
区域正文

## 二、风险情况
风险正文
""".encode()


def test_a_subsection_returned_as_a_chapter_is_put_back_under_its_parent():
    """One misplaced heading must not fail the whole plan."""

    async def run():
        service = build_service()
        template = await service.upload_template("t.md", NESTED_THREE_LEVEL, "text/markdown")
        planner = ReportPlanner(llm=None)

        chapters, _, _ = planner._parse_plan_payload(
            {
                "title": "报告",
                "global_context": {"report_period": None, "dimensions": {}},
                "chapters": [
                    {"section_id": "section_1", "title": "正文", "metrics": [], "subsections": []},
                    {"section_id": "section_2", "title": "一、经营概况", "metrics": ["规模"], "subsections": []},
                    # The model flattened these two out of their parent.
                    {"section_id": "section_4", "title": "1.2 区域分布", "metrics": []},
                    {"section_id": "section_3", "title": "1.1 整体规模", "metrics": []},
                    {"section_id": "section_5", "title": "二、风险情况", "metrics": [], "subsections": []},
                ],
            },
            template,
            require_every_section=True,
        )

        assert [item.section_id for item in chapters] == ["section_1", "section_2", "section_5"]
        overview = next(item for item in chapters if item.section_id == "section_2")
        # Relocated in template order, not in the order the model happened to emit.
        assert [item.section_id for item in overview.subsections] == ["section_3", "section_4"]
        assert overview.metrics == ["规模"]

    asyncio.run(run())


def test_a_genuinely_unknown_section_is_still_rejected():
    async def run():
        service = build_service()
        template = await service.upload_template("t.md", NESTED_THREE_LEVEL, "text/markdown")
        try:
            ReportPlanner(llm=None)._parse_plan_payload(
                {
                    "title": "报告",
                    "global_context": {"report_period": None, "dimensions": {}},
                    "chapters": [{"section_id": "section_99", "title": "凭空捏造", "metrics": []}],
                },
                template,
                require_every_section=False,
            )
        except ValueError as exc:
            assert "unknown section_id" in str(exc)
        else:
            raise AssertionError("模板里不存在的 section_id 仍应被拒绝")

    asyncio.run(run())


def test_sheet_metadata_enumerates_column_values():
    """Planning picks the period and the dimensions from what the data holds."""

    async def run():
        service = build_service()
        dataset_id = await registered_dataset(service, "excel_enum_1")
        metadata = await service._build_data_source_metadata([dataset_id])

        sheet = metadata[0].sheets[0]
        assert sheet["value_enums"]["value"] == ["1"]
        # A column wide enough to be uninteresting is described by its range.
        assert "value_ranges" not in sheet or "value" not in sheet["value_ranges"]

    asyncio.run(run())


def test_numeric_ranges_are_ordered_as_numbers():
    """Sorting as text puts 997000 after 1000000 and reports a nonsense range."""
    from app.reporting.report_generation import ReportGenerationService

    assert ReportGenerationService._ordered({1000000, 997000, 2855600})[0] == 997000
    assert ReportGenerationService._ordered({1000000, 997000, 2855600})[-1] == 2855600
    # Mixed types must still produce a stable order rather than raising.
    assert ReportGenerationService._ordered({"b", 1, "a"})
