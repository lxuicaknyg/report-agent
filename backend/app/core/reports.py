from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import Evidence, utc_now


class ReportGenerationStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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


class ReportPlan(BaseModel):
    plan_id: str
    template_id: str
    title: str
    instruction: str
    sections: list[ReportTemplateSection] = Field(default_factory=list)
    assembly_order: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class DataSourceMetadata(BaseModel):
    dataset_id: str
    name: str
    source_type: str
    description: str | None = None
    sheets: list[dict[str, Any]] = Field(default_factory=list)
    columns: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChapterWriterInput(BaseModel):
    section: ReportTemplateSection
    report_outline: list[str] = Field(default_factory=list)
    data_sources: list[DataSourceMetadata] = Field(default_factory=list)
    user_instruction: str = ""
    previous_answers: dict[str, str] = Field(default_factory=dict)


class UserQuestion(BaseModel):
    question_id: str
    chapter_id: str | None = None
    content: str
    reason: str | None = None
    required: bool = True
    answer: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    answered_at: datetime | None = None


class ChapterDraft(BaseModel):
    chapter_id: str
    section_id: str
    title: str
    content: str = ""
    tables: list[dict[str, Any]] = Field(default_factory=list)
    charts: list[dict[str, Any]] = Field(default_factory=list)
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
    plan: ReportPlan | None = None
    chapter_drafts: dict[str, ChapterDraft] = Field(default_factory=dict)
    pending_questions: list[UserQuestion] = Field(default_factory=list)
    answers: dict[str, str] = Field(default_factory=dict)
    assembled_report: AssembledReport | None = None
    artifacts: list[ReportArtifact] = Field(default_factory=list)
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CreateReportGenerationRequest(BaseModel):
    template_id: str
    dataset_ids: list[str] = Field(min_length=1)
    instruction: str = Field(min_length=1)
    title: str | None = None
    auto_start: bool = True


class AnswerReportQuestionRequest(BaseModel):
    question_id: str
    answer: str = Field(min_length=1)
    auto_resume: bool = True
