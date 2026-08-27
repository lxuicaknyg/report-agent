from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..core.reports import ReportGenerationSession, ReportTemplate


@dataclass(frozen=True)
class StoredReportTemplate:
    template: ReportTemplate
    content: bytes


class ReportSessionRepository(ABC):
    @abstractmethod
    async def save(self, session: ReportGenerationSession) -> None:
        pass

    @abstractmethod
    async def get(self, session_id: str) -> ReportGenerationSession:
        pass


class ReportTemplateRepository(ABC):
    @abstractmethod
    async def save(self, stored_template: StoredReportTemplate) -> None:
        pass

    @abstractmethod
    async def get(self, template_id: str) -> StoredReportTemplate:
        pass

