from __future__ import annotations

from ..reporting.session import ReportSessionRepository, ReportTemplateRepository, StoredReportTemplate
from ..core.reports import ReportGenerationSession


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
