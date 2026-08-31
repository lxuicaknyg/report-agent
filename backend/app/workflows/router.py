from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class WorkflowKind(str, Enum):
    REPORT_GENERATION = "report_generation"


class WorkflowDecision(BaseModel):
    workflow: WorkflowKind
    confidence: float = Field(ge=0, le=1)
    reason: str


class ExplicitWorkflowRouter:
    """Route explicitly selected workflows; an LLM classifier can be added later."""

    _template_suffixes = {".docx", ".md", ".markdown", ".txt"}
    _data_suffixes = {".xlsx"}

    def route(
        self,
        workflow: str,
        *,
        template_filename: str,
        data_filename: str,
        instruction: str,
    ) -> WorkflowDecision:
        try:
            kind = WorkflowKind(workflow)
        except ValueError as exc:
            raise ValueError(f"Unsupported workflow: {workflow}") from exc
        if kind is not WorkflowKind.REPORT_GENERATION:
            raise ValueError(f"Unsupported workflow: {workflow}")
        if Path(template_filename).suffix.lower() not in self._template_suffixes:
            raise ValueError("Report template must be .docx, .md, .markdown or .txt")
        if Path(data_filename).suffix.lower() not in self._data_suffixes:
            raise ValueError("Report data file must be .xlsx")
        if not instruction.strip():
            raise ValueError("instruction is required")
        return WorkflowDecision(
            workflow=kind,
            confidence=1.0,
            reason="The report-generation workflow was explicitly selected and its inputs passed validation.",
        )
