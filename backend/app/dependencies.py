from __future__ import annotations

from functools import lru_cache

from .analysis.agent import AnalysisAgent
from .core.tooling import ToolRegistry
from .data.catalog import DataCatalog
from .infrastructure.artifact_store import InMemoryArtifactStore
from .infrastructure.llm import OpenAICompatibleLlmService
from .infrastructure.report_repositories import (
    InMemoryReportSessionRepository,
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
from .tools import ListDatasetsTool, ListSheetsTool, ProfileDatasetTool, QueryDatasetTool, ReadDatasetTool


@lru_cache
def get_catalog() -> DataCatalog:
    return DataCatalog()


@lru_cache
def get_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ListDatasetsTool(get_catalog()))
    registry.register(ProfileDatasetTool(get_catalog()))
    registry.register(QueryDatasetTool(get_catalog()))
    registry.register(ListSheetsTool(get_catalog()))
    registry.register(ReadDatasetTool(get_catalog()))
    return registry


@lru_cache
def get_agent() -> AnalysisAgent:
    return AnalysisAgent(get_registry())


@lru_cache
def get_llm() -> OpenAICompatibleLlmService:
    return OpenAICompatibleLlmService(
        base_url=settings.llm_base_url or "",
        api_key=settings.llm_api_key or "",
        model=settings.llm_model_name or "",
    )


@lru_cache
def get_report_service() -> ReportService:
    return ReportService()


@lru_cache
def get_report_generation_service() -> ReportGenerationService:
    return ReportGenerationService(
        sessions=InMemoryReportSessionRepository(),
        templates=InMemoryReportTemplateRepository(),
        template_parser=ReportTemplateParser(),
        planner=ReportPlanner(),
        writer=ChapterWriterAgent(llm=get_llm(), tools=get_registry()),
        assembler=ReportAssembler(),
        renderer=MarkdownReportRenderer(),
        artifact_store=InMemoryArtifactStore(),
        catalog=get_catalog(),
    )
