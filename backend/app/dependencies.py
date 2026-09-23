from __future__ import annotations

import logging
import re
import secrets
from functools import lru_cache

from .auth import AuthService, UserRepository
from .conversations import ConversationOrchestrator
from .connections import ConnectionService, PersistentConnectionRepository
from .core.tooling import ToolRegistry
from .data.catalog import DataCatalog
from .data.sources.excel import ExcelDataSource
from .infrastructure.artifact_store import FileSystemArtifactStore
from .infrastructure.conversation_repositories import PersistentConversationRepository
from .infrastructure.llm import OpenAICompatibleLlmService
from .infrastructure.report_repositories import (
    PersistentReportSessionRepository,
    PersistentReportTemplateRepository,
)
from .reporting import (
    MarkdownReportRenderer,
    ReportAssembler,
    ReportGenerationService,
    ChapterWriterAgent,
    ReportPlanner,
    ReportTemplateParser,
    StubChapterWriter,
)
from .config import settings

logger = logging.getLogger(__name__)
from .tools import (
    AggregateDatasetTool,
    GenerateAnalysisSQLTool,
    ListDatasetsTool,
    ListSheetsTool,
    ProfileDatasetTool,
    ReadDatasetTool,
)


@lru_cache
def get_auth_service() -> AuthService:
    secret = settings.auth_secret
    if not secret:
        if settings.environment != "development":
            # A random secret is survivable alone, but this service shares its
            # tokens with other teams' backends: a secret nobody else can know
            # means every one of their requests 401s, and the symptom shows up
            # in their logs rather than ours. Refusing to start is the only way
            # that failure gets diagnosed in seconds instead of an afternoon.
            raise RuntimeError(
                "AUTH_SECRET 未设置。工作台内所有后端必须共用同一个密钥才能互相验签，"
                "请在部署环境里下发 AUTH_SECRET 后再启动。"
            )
        # Better a secret that dies with the process than one committed to the
        # repo: unset AUTH_SECRET only costs everyone a re-login on restart.
        secret = secrets.token_urlsafe(48)
        logger.warning(
            "AUTH_SECRET 未设置，本次启动使用随机密钥；重启后已签发的 token 全部失效。"
        )
    return AuthService(
        UserRepository(settings.auth_database_url),
        secret=secret,
        token_ttl_seconds=settings.auth_token_ttl_seconds,
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
            settings.connection_store
        ),
        analysis_tool=GenerateAnalysisSQLTool(llm=get_llm()),
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
def get_report_generation_service() -> ReportGenerationService:
    return ReportGenerationService(
        sessions=PersistentReportSessionRepository(settings.session_store),
        templates=PersistentReportTemplateRepository(
            settings.template_store, settings.template_content_dir
        ),
        template_parser=ReportTemplateParser(),
        planner=ReportPlanner(llm=get_llm()),
        writer=ChapterWriterAgent(llm=get_llm(), tools=get_registry()),
        assembler=ReportAssembler(),
        renderer=MarkdownReportRenderer(),
        artifact_store=FileSystemArtifactStore(settings.artifact_dir),
        catalog=get_catalog(),
        connections=get_connection_service(),
    )


@lru_cache
def get_conversation_orchestrator() -> ConversationOrchestrator:
    return ConversationOrchestrator(
        conversations=PersistentConversationRepository(
            settings.conversation_store
        ),
        reports=get_report_generation_service(),
        llm=get_llm(),
    )
