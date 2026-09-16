from __future__ import annotations

import logging
import re
import tempfile
from functools import lru_cache
from pathlib import Path

from .conversations import ConversationOrchestrator
from .connections import ConnectionService, PersistentConnectionRepository
from .core.tooling import ToolRegistry
from .data.catalog import DataCatalog
from .data.sources.excel import ExcelDataSource
from .infrastructure.artifact_store import InMemoryArtifactStore
from .infrastructure.conversation_repositories import PersistentConversationRepository
from .infrastructure.llm import OpenAICompatibleLlmService
from .infrastructure.report_repositories import (
    PersistentReportSessionRepository,
    InMemoryReportTemplateRepository,
)
from .reporting import (
    MarkdownReportRenderer,
    ReportAssembler,
    ReportGenerationService,
    ChapterWriterAgent,
    ReportPlanner,
    ReportService,
    ReportTemplateParser,
    StubChapterWriter,
)
from .config import settings

logger = logging.getLogger(__name__)
from .tools import (
    AggregateDatasetTool,
    ListDatasetsTool,
    ListSheetsTool,
    ProfileDatasetTool,
    ReadDatasetTool,
)


@lru_cache
def get_catalog() -> DataCatalog:
    return DataCatalog(restore=_restore_excel_upload)


def _restore_excel_upload(dataset_id: str) -> ExcelDataSource | None:
    """Find an upload from an earlier run still sitting on disk.

    Report sessions are persisted but the catalog is not, so without this a
    report that outlives a restart cannot read the data it was built on: every
    read comes back "Dataset not found", which is exactly the failure — a dead
    process — that makes resuming a run worth having. The lookup is by id, so
    a directory full of old uploads costs nothing.
    """
    if not re.fullmatch(r"excel_[0-9a-f]+", dataset_id):
        return None
    data_dir = settings.data_dir
    if not data_dir.is_dir():
        return None
    for path in sorted(data_dir.glob(f"{dataset_id}_*")):
        if path.suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
            continue
        logger.info("dataset_restored dataset_id=%s path=%s", dataset_id, path.name)
        # Uploads are stored as "<dataset_id>_<original filename>".
        return ExcelDataSource(path=path, dataset_id=dataset_id, name=path.name[len(dataset_id) + 1:])
    return None


@lru_cache
def get_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ListDatasetsTool(get_catalog()))
    registry.register(ProfileDatasetTool(get_catalog()))
    registry.register(ListSheetsTool(get_catalog()))
    registry.register(ReadDatasetTool(get_catalog()))
    registry.register(AggregateDatasetTool(get_catalog()))
    return registry


@lru_cache
def get_connection_service() -> ConnectionService:
    # Beside the session store rather than in the project tree: the file holds
    # credentials, and ./data is watched by uvicorn --reload.
    return ConnectionService(
        PersistentConnectionRepository(
            Path(tempfile.gettempdir()) / "report-agent-connections.json"
        )
    )


@lru_cache
def get_llm() -> OpenAICompatibleLlmService:
    return OpenAICompatibleLlmService(
        base_url=settings.llm_base_url or "",
        api_key=settings.llm_api_key or "",
        model=settings.llm_model_name or "",
        timeout=settings.llm_timeout_seconds,
        max_attempts=settings.llm_max_attempts,
        backoff_seconds=settings.llm_backoff_seconds,
    )


@lru_cache
def get_report_service() -> ReportService:
    return ReportService()


@lru_cache
def get_report_generation_service() -> ReportGenerationService:
    return ReportGenerationService(
        sessions=PersistentReportSessionRepository(Path(tempfile.gettempdir()) / "report-agent-sessions.json"),
        templates=InMemoryReportTemplateRepository(),
        template_parser=ReportTemplateParser(),
        planner=ReportPlanner(llm=get_llm()),
        writer=ChapterWriterAgent(llm=get_llm(), tools=get_registry()),
        assembler=ReportAssembler(),
        renderer=MarkdownReportRenderer(),
        artifact_store=InMemoryArtifactStore(),
        catalog=get_catalog(),
    )


@lru_cache
def get_conversation_orchestrator() -> ConversationOrchestrator:
    return ConversationOrchestrator(
        conversations=PersistentConversationRepository(
            Path(tempfile.gettempdir()) / "report-agent-conversations.json"
        ),
        reports=get_report_generation_service(),
        llm=get_llm(),
    )
