from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import Evidence, utc_now


class ReportGenerationStatus(str, Enum):
    CREATED = "created"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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


QuestionResolution = Literal["pending", "value", "sql", "dropped"]


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
    expected: Literal["value", "dataset", "text"] = "text"
    content: str
    reason: str | None = None
    required: bool = True
    created_at: datetime = Field(default_factory=utc_now)

    resolution: QuestionResolution = "pending"
    value: str | None = None
    note: str | None = None
    dataset_id: str | None = None
    query: str | None = None
    resolved_at: datetime | None = None


class QuestionResolutionInput(BaseModel):
    """The user's decision about one pending question."""

    question_id: str
    action: Literal["value", "sql", "drop"]
    value: str | None = None
    note: str | None = None
    dataset_id: str | None = None
    query: str | None = None


class ChapterSupplement(BaseModel):
    """Data the user supplied for a chapter, labelled by the metric it covers."""

    metric: str
    value: str | None = None
    note: str | None = None


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
