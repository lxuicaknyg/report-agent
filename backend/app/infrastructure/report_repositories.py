from __future__ import annotations

import json
from pathlib import Path

from ..reporting.session import ReportSessionRepository, ReportTemplateRepository, StoredReportTemplate
from ..core.reports import ReportGenerationSession, ReportGenerationStatus, ReportTemplate


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
        # A process cannot resume an in-flight in-memory worker after restart, so
        # those records are reconciled to a terminal state. A session waiting on
        # the user is not in flight: nothing is running, and the answer can still
        # arrive after a restart, so it is left alone.
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


class PersistentReportTemplateRepository(ReportTemplateRepository):
    """Keep uploaded templates across restarts.

    Sessions are persisted but templates were not, and a session stores only its
    ``template_id``: after a restart, resuming a report re-read its template and
    died with a KeyError. In a container a restart is routine, so that turned
    every redeploy into a graveyard of reports that could no longer be continued.

    The parsed model goes in one JSON file; the original bytes go beside it, one
    file each, because a template may be a .docx and base64 in JSON would
    inflate it for nothing.
    """

    def __init__(self, path: Path, content_dir: Path) -> None:
        self.path = path
        self.content_dir = content_dir
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.content_dir.mkdir(parents=True, exist_ok=True)
        self._templates: dict[str, ReportTemplate] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for template_id, value in raw.items():
                    if isinstance(value, dict):
                        self._templates[template_id] = ReportTemplate.model_validate(value)
        except (FileNotFoundError, OSError, ValueError):
            self._templates = {}

    def _flush(self) -> None:
        payload = {key: value.model_dump(mode="json") for key, value in self._templates.items()}
        tmp = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def _content_path(self, template_id: str) -> Path:
        # Ids are minted from uuid4().hex, so they cannot walk out of the
        # directory; the check is here so that stays true if that ever changes.
        if not template_id.replace("_", "").isalnum():
            raise KeyError(f"Report template not found: {template_id}")
        return self.content_dir / f"{template_id}.bin"

    async def save(self, stored_template: StoredReportTemplate) -> None:
        template_id = stored_template.template.template_id
        # Content first: a template that is listed but unreadable is worse than
        # one that was never listed, because only the first kind fails later, at
        # resume time.
        self._content_path(template_id).write_bytes(stored_template.content)
        self._templates[template_id] = stored_template.template.model_copy(deep=True)
        self._flush()

    async def get(self, template_id: str) -> StoredReportTemplate:
        try:
            template = self._templates[template_id]
            content = self._content_path(template_id).read_bytes()
        except (KeyError, OSError) as exc:
            raise KeyError(f"Report template not found: {template_id}") from exc
        return StoredReportTemplate(template=template.model_copy(deep=True), content=content)

    async def list(self) -> list[StoredReportTemplate]:
        items: list[StoredReportTemplate] = []
        for template_id in list(self._templates):
            try:
                items.append(await self.get(template_id))
            except KeyError:
                # Metadata without its bytes: skip rather than fail the listing,
                # so one damaged upload cannot hide every other template.
                continue
        return items
