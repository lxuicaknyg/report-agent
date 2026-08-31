from __future__ import annotations

import logging
from pathlib import Path
from tempfile import gettempdir
from uuid import uuid4

from ..config import settings
from ..core.reports import CreateReportGenerationRequest, ReportGenerationSession
from ..data.catalog import DataCatalog
from ..data.sources.excel import ExcelDataSource
from ..reporting.report_generation import ReportGenerationService
from .router import ExplicitWorkflowRouter, WorkflowDecision

logger = logging.getLogger(__name__)


class WorkflowIntakeService:
    """Accept all report inputs once, classify them, then dispatch a workflow."""

    def __init__(
        self,
        reports: ReportGenerationService,
        catalog: DataCatalog,
        router: ExplicitWorkflowRouter | None = None,
    ) -> None:
        self.reports = reports
        self.catalog = catalog
        self.router = router or ExplicitWorkflowRouter()

    async def intake_report(
        self,
        *,
        template_filename: str,
        template_content: bytes,
        template_content_type: str | None,
        data_filename: str,
        data_content: bytes,
        instruction: str,
        title: str | None,
        workflow: str = "report_generation",
        user_id: str = "local-user",
    ) -> tuple[WorkflowDecision, ReportGenerationSession]:
        if not template_content or not data_content:
            raise ValueError("Template and data files are required")
        decision = self.router.route(
            workflow,
            template_filename=template_filename,
            data_filename=data_filename,
            instruction=instruction,
        )

        template = await self.reports.upload_template(
            template_filename,
            template_content,
            template_content_type,
        )
        data_dir = settings.data_dir
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            data_dir = Path(gettempdir()) / "report-agent-data"
            data_dir.mkdir(parents=True, exist_ok=True)
        dataset_id = f"excel_{uuid4().hex[:10]}"
        safe_filename = Path(data_filename).name
        data_path = data_dir / f"{dataset_id}_{safe_filename}"
        data_path.write_bytes(data_content)
        try:
            source = ExcelDataSource(path=data_path, dataset_id=dataset_id, name=safe_filename)
            self.catalog.register(source)
        except Exception:
            data_path.unlink(missing_ok=True)
            raise

        session = await self.reports.create_session(
            CreateReportGenerationRequest(
                template_id=template.template_id,
                dataset_ids=[dataset_id],
                instruction=instruction,
                title=title,
                auto_start=False,
            ),
            user_id=user_id,
        )
        session.current_step = "accepted"
        await self.reports.sessions.save(session)
        logger.info(
            "workflow_intake_accepted session_id=%s workflow=%s template_id=%s dataset_id=%s",
            session.session_id,
            decision.workflow.value,
            template.template_id,
            dataset_id,
        )
        return decision, session
