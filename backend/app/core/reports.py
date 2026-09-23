from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .models import Evidence, utc_now


class ReportGenerationStatus(str, Enum):
    CREATED = "created"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class UserInputRejected(ValueError):
    """Something the user can fix by doing something different.

    Separated from a system failure so the reply can say what to do, instead of
    pointing at a backend log the user has no way to read. The message is the
    whole explanation; nothing is hidden behind it.
    """


class GenerationCancelled(Exception):
    """Raised inside a run once the user has stopped it.

    Cancellation is cooperative: the stop request only flips the stored status,
    and the run notices at its next checkpoint and unwinds without marking
    itself failed. Whatever it had already saved stays on disk so the session
    can be resumed from the chapter it was interrupted on.
    """

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Report generation cancelled: {session_id}")
        self.session_id = session_id


class ReportTemplateSection(BaseModel):
    section_id: str
    title: str
    level: int = Field(default=1, ge=1)
    order: int = Field(ge=0)
    instructions: str | None = None
    example_content: str | None = None
    template_text: str = ""
    template_blocks: list[dict[str, Any]] = Field(default_factory=list)
    required_data: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReportTemplate(BaseModel):
    template_id: str
    filename: str
    title: str
    #: Who uploaded it. None on templates stored before uploads were attributed;
    #: those are nobody's, not everybody's — see ``api.deps.forbid_unless_owner``.
    owner_id: str | None = None
    content_type: str | None = None
    sections: list[ReportTemplateSection] = Field(default_factory=list)
    assembly_rules: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class TemplateChapter(BaseModel):
    """One top-level chapter: a root heading plus every deeper heading under it.

    The parser produces a flat, faithful list of headings; this is the derived
    view the planner and the chapter writer work in, so an H2 and its H3
    subsections are planned, generated and rendered as a single chapter.
    """

    root: ReportTemplateSection
    subsections: list[ReportTemplateSection] = Field(default_factory=list)

    @property
    def section_ids(self) -> list[str]:
        return [self.root.section_id, *(item.section_id for item in self.subsections)]


def synthesize_template(
    template_id: str,
    title: str,
    chapters: list["ChapterPlan"],
) -> "ReportTemplate":
    """Turn an agreed outline into a template the rest of the pipeline can read.

    Everything downstream keys on ``section_id`` and takes heading levels from
    a template, so a report invented in conversation needs one too. The
    template is derived from the plan rather than parsed from a file: there is
    no example prose and no table columns, only the shape the user confirmed.

    Regenerating it from the current plan on every revision is what keeps the
    two from drifting — the template cannot describe a chapter the plan
    dropped.
    """
    sections: list[ReportTemplateSection] = []
    order = 0
    for chapter in chapters:
        sections.append(
            ReportTemplateSection(
                section_id=chapter.section_id,
                title=chapter.title,
                level=1,
                order=order,
                metadata={"synthesized": True},
            )
        )
        order += 1
        for item in chapter.subsections:
            sections.append(
                ReportTemplateSection(
                    section_id=item.section_id,
                    title=item.title,
                    level=2,
                    order=order,
                    metadata={"synthesized": True},
                )
            )
            order += 1
    return ReportTemplate(
        template_id=template_id,
        filename="对话生成的报告结构",
        title=title,
        sections=sections,
        metadata={"synthesized": True},
    )


def group_template_chapters(sections: list[ReportTemplateSection]) -> list[TemplateChapter]:
    """Group a flat heading list into chapters by heading level.

    The shallowest level present starts a chapter; anything deeper attaches to
    the chapter above it. Templates that start at H2 group by H2, so this does
    not assume the document uses H1 at all.
    """
    ordered = sorted(sections, key=lambda item: item.order)
    if not ordered:
        return []
    # The leading body text is not a heading, so it must not set the base level
    # for a template whose real headings all start at H2.
    headings = [item for item in ordered if not item.metadata.get("preamble")]
    base_level = min((item.level for item in headings), default=1)
    chapters: list[TemplateChapter] = []
    for section in ordered:
        is_root = section.metadata.get("preamble") or section.level <= base_level
        if is_root or not chapters:
            chapters.append(TemplateChapter(root=section))
        else:
            chapters[-1].subsections.append(section)
    return chapters


class ReportGlobalContext(BaseModel):
    report_period: str | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)


class SubchapterPlan(BaseModel):
    """A planned subsection. Its level comes from the template, not the model."""

    section_id: str
    title: str
    level: int = Field(default=2, ge=1)


class ChapterPlan(BaseModel):
    section_id: str
    title: str
    level: int = Field(default=1, ge=1)
    metrics: list[str] = Field(default_factory=list)
    subsections: list[SubchapterPlan] = Field(default_factory=list)

    @property
    def section_ids(self) -> list[str]:
        return [self.section_id, *(item.section_id for item in self.subsections)]


class ReportPlan(BaseModel):
    plan_id: str
    version: int = 1
    status: Literal[
        "generated",
        "awaiting_confirmation",
        "approved",
        "executing",
        "completed",
    ] = "generated"
    template_id: str
    title: str
    instruction: str
    global_context: ReportGlobalContext = Field(default_factory=ReportGlobalContext)
    chapters: list[ChapterPlan] = Field(default_factory=list)
    assembly_order: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @property
    def sections(self) -> list[ChapterPlan]:
        """Compatibility view for callers that used the old field name."""
        return self.chapters


class DataSourceMetadata(BaseModel):
    dataset_id: str
    name: str
    source_type: str
    description: str | None = None
    sheets: list[dict[str, Any]] = Field(default_factory=list)
    columns: list[dict[str, Any]] = Field(default_factory=list)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChapterWriterInput(BaseModel):
    section: ReportTemplateSection
    subsections: list[ReportTemplateSection] = Field(default_factory=list)
    chapter_plan: ChapterPlan | None = None
    global_context: ReportGlobalContext = Field(default_factory=ReportGlobalContext)
    metrics: list[str] = Field(default_factory=list)
    report_outline: list[str] = Field(default_factory=list)
    data_sources: list[DataSourceMetadata] = Field(default_factory=list)
    user_instruction: str = ""
    findings: list[MetricFinding] = Field(default_factory=list)
    supplements: list[ChapterSupplement] = Field(default_factory=list)
    dropped_metrics: list[str] = Field(default_factory=list)


QuestionResolution = Literal["pending", "value", "sql", "table", "dropped"]

#: What a chapter is missing, decided when the question is raised rather than
#: by the user when they answer it.
#:
#: ``value`` is one figure the chapter will print in a sentence; ``table`` is a
#: list it will print as rows; ``text`` is a sentence of explanation. The kind
#: decides which ways of answering are offered, which is why the user is not
#: asked to classify their own answer — by the time they are answering, the
#: system already knows which of the two it needs.
QuestionExpectation = Literal["value", "table", "text"]


class UserQuestion(BaseModel):
    """A piece of data a chapter needs before it can be written.

    The user resolves every question of a chapter before that chapter is
    regenerated: either by supplying the data, or by dropping the metric from
    the report altogether.
    """

    question_id: str
    chapter_id: str | None = None
    chapter_title: str | None = None
    metric: str | None = None
    expected: QuestionExpectation = "value"
    content: str
    reason: str | None = None
    required: bool = True
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("expected", mode="before")
    @classmethod
    def _migrate_expected(cls, value: Any) -> Any:
        """Read questions stored before the kinds were settled.

        ``dataset`` used to mean "this needs another dataset", which the card
        then offered no way to supply — users answered it by typing the figure
        in, so that is what it becomes.
        """
        return "value" if value == "dataset" else value

    resolution: QuestionResolution = "pending"
    value: str | None = None
    note: str | None = None
    dataset_id: str | None = None
    #: Set when the value came from SQL: which saved connection it was run
    #: against, the statement itself, and the dimensions that statement
    #: selected. Kept so a supplied number can be re-derived, not just trusted.
    connection_id: str | None = None
    connection_name: str | None = None
    query: str | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)
    #: Set instead of ``value`` when the answer is a detail table.
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, str]] = Field(default_factory=list)
    rows_truncated: bool = False
    resolved_at: datetime | None = None


class QuestionResolutionInput(BaseModel):
    """The user's decision about one pending question.

    ``action="sql"`` supplies ``connection_id`` and ``query`` instead of a
    typed ``value``: the backend runs the statement and reads the value out of
    it, so what lands on the question is what the database actually returned.
    """

    question_id: str
    action: Literal["value", "sql", "table", "drop"]
    value: str | None = None
    note: str | None = None
    dataset_id: str | None = None
    connection_id: str | None = None
    query: str | None = None
    #: For ``action="table"``: the rows as the user pasted them, parsed here
    #: rather than in the browser so the preview they approved and the table
    #: that lands in the report are the same read of the same text.
    text: str | None = None
    #: The escape hatch for a question the system classified wrongly: a
    #: single-figure question whose query turns out to return a list is
    #: answered as one, without the user having had to choose a mode upfront.
    as_table: bool = False


class ChapterSupplement(BaseModel):
    """Data the user supplied for a chapter, labelled by the metric it covers.

    One structure covers both ways of answering, with ``source`` saying which.
    It is declared rather than inferred from which fields are filled: reading
    the origin off the presence of ``query`` worked while there were exactly
    two ways to answer, and would quietly mislabel a third.
    """

    metric: str
    source: Literal["manual", "sql", "pasted"] = "manual"
    #: A single figure. ``None`` when the answer is a detail table instead.
    value: str | None = None
    note: str | None = None
    #: The columns the query grouped or filtered on, for a single value fetched
    #: by SQL. A bare scalar leaves this empty, and the value then means only
    #: whatever ``metric`` claims it means. Never set for a table.
    dimensions: dict[str, str] = Field(default_factory=dict)
    #: The detail rows, when the metric is a list rather than a figure. Every
    #: column is content here — the positional value/dimension convention does
    #: not apply, because a detail table has no one column that is "the value".
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, str]] = Field(default_factory=list)
    rows_truncated: bool = False
    connection_id: str | None = None
    connection_name: str | None = None
    query: str | None = None


class MetricFinding(BaseModel):
    """A metric's settled value, produced while researching it.

    The value is decided once, in a context holding only this metric's own
    rows, so the writing step narrates a fact instead of re-deriving it — the
    same quantity was previously computed separately for the prose and for the
    table, and the two disagreed.
    """

    metric: str
    value: str
    basis: str | None = None
    reads: list[dict[str, Any]] = Field(default_factory=list)
    #: The evidence this value was read out of, so a number printed in the
    #: chapter can be traced back to the query that produced it. Ids rather
    #: than objects: one read often settles several metrics, and the evidence
    #: itself is held once on the chapter.
    evidence_ids: list[str] = Field(default_factory=list)


class ReportFact(BaseModel):
    fact_id: str
    label: str
    value: Any
    unit: str | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class ChapterDraft(BaseModel):
    chapter_id: str
    section_id: str
    title: str
    content: str = ""
    tables: list[dict[str, Any]] = Field(default_factory=list)
    charts: list[dict[str, Any]] = Field(default_factory=list)
    facts: list[ReportFact] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    #: What research settled for each metric, kept so the finished chapter can
    #: still say where every number came from. Without it the values existed
    #: only for the length of one run.
    findings: list[MetricFinding] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    questions: list[UserQuestion] = Field(default_factory=list)
    completed: bool = True


class ChapterWriterResult(BaseModel):
    status: Literal["completed", "waiting_user", "failed"]
    draft: ChapterDraft | None = None
    questions: list[UserQuestion] = Field(default_factory=list)
    error: str | None = None


class AssembledReport(BaseModel):
    title: str
    executive_summary: str = ""
    chapters: list[ChapterDraft] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReportArtifact(BaseModel):
    artifact_id: str
    name: str
    content_type: str
    uri: str
    format: str
    created_at: datetime = Field(default_factory=utc_now)


class ReportGenerationSession(BaseModel):
    session_id: str
    user_id: str
    template_id: str
    dataset_ids: list[str]
    instruction: str
    title: str | None = None
    status: ReportGenerationStatus = ReportGenerationStatus.CREATED
    current_step: str | None = None
    current_chapter_id: str | None = None
    template_snapshot: ReportTemplate | None = None
    data_source_metadata: list[DataSourceMetadata] = Field(default_factory=list)
    plan: ReportPlan | None = None
    chapter_drafts: dict[str, ChapterDraft] = Field(default_factory=dict)
    pending_questions: list[UserQuestion] = Field(default_factory=list)
    resolved_questions: list[UserQuestion] = Field(default_factory=list)
    dropped_metrics: dict[str, list[str]] = Field(default_factory=dict)
    chapter_attempts: dict[str, int] = Field(default_factory=dict)
    assembled_report: AssembledReport | None = None
    artifacts: list[ReportArtifact] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CreateReportGenerationRequest(BaseModel):
    template_id: str | None = None
    dataset_ids: list[str] = Field(default_factory=list)
    instruction: str = Field(min_length=1)
    title: str | None = None
    auto_start: bool = False



class ResolveQuestionsRequest(BaseModel):
    resolutions: list[QuestionResolutionInput] = Field(min_length=1)
    auto_resume: bool = True
