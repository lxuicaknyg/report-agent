from __future__ import annotations

import json
from pathlib import Path

from ..reporting.session import ReportSessionRepository, ReportTemplateRepository, StoredReportTemplate
from ..core.reports import ReportGenerationSession, ReportGenerationStatus


class InMemoryReportSessionRepository(ReportSessionRepository):
    def __init__(self) -> None:
        self._sessions: dict[str, ReportGenerationSession] = {}

    async def save(self, session: ReportGenerationSession) -> None:
        self._sessions[session.session_id] = session.model_copy(deep=True)

    async def get(self, session_id: str) -> ReportGenerationSession:
        try:
            return self._sessions[session_id].model_copy(deep=True)
        except KeyError as exc:
            raise KeyError(f"Report generation session not found: {session_id}") from exc

    async def list(self) -> list[ReportGenerationSession]:
        return [session.model_copy(deep=True) for session in self._sessions.values()]


class InMemoryReportTemplateRepository(ReportTemplateRepository):
    def __init__(self) -> None:
        self._templates: dict[str, StoredReportTemplate] = {}

    async def save(self, stored_template: StoredReportTemplate) -> None:
        template_id = stored_template.template.template_id
        self._templates[template_id] = StoredReportTemplate(
            template=stored_template.template.model_copy(deep=True),
            content=bytes(stored_template.content),
        )

    async def get(self, template_id: str) -> StoredReportTemplate:
        try:
            stored = self._templates[template_id]
        except KeyError as exc:
            raise KeyError(f"Report template not found: {template_id}") from exc
        return StoredReportTemplate(template=stored.template.model_copy(deep=True), content=bytes(stored.content))

    async def list(self) -> list[StoredReportTemplate]:
        return [
            StoredReportTemplate(template=stored.template.model_copy(deep=True), content=bytes(stored.content))
            for stored in self._templates.values()
        ]


class PersistentReportSessionRepository(ReportSessionRepository):
    """Persist report lifecycle state so process termination does not create ghost IDs."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, ReportGenerationSession] = {}
        self._load()
        # A process cannot resume an in-flight in-memory worker after restart.
        # Reconcile those records to a terminal state instead of leaving them running.
        self._reconcile_interrupted()
        self._flush()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for session_id, value in raw.items():
                    if isinstance(value, dict):
                        self._sessions[session_id] = ReportGenerationSession.model_validate(value)
        except (FileNotFoundError, OSError, ValueError):
            self._sessions = {}

    def _flush(self) -> None:
        payload = {key: value.model_dump(mode="json") for key, value in self._sessions.items()}
        tmp = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def _reconcile_interrupted(self) -> None:
        for session in self._sessions.values():
            if session.status in {
                ReportGenerationStatus.CREATED,
                ReportGenerationStatus.RUNNING,
                ReportGenerationStatus.WAITING_USER,
            }:
                session.status = ReportGenerationStatus.CANCELLED
                session.current_step = "cancelled_after_backend_restart"
                session.error = "后端进程终止，报告生成任务已终止，请重新提交"

    async def save(self, session: ReportGenerationSession) -> None:
        self._sessions[session.session_id] = session.model_copy(deep=True)
        self._flush()

    async def get(self, session_id: str) -> ReportGenerationSession:
        try:
            return self._sessions[session_id].model_copy(deep=True)
        except KeyError as exc:
            raise KeyError(f"Report generation session not found: {session_id}") from exc

    async def list(self) -> list[ReportGenerationSession]:
        return [session.model_copy(deep=True) for session in self._sessions.values()]
