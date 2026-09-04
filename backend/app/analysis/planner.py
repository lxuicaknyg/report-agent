from __future__ import annotations

from ..core.reports import ReportPlan, ReportTemplate
from ..reporting.planner import ReportPlanner as ReportingPlanner


class ReportPlanner:
    """Compatibility adapter for the legacy analysis package."""

    async def create_plan(
        self,
        template: ReportTemplate,
        dataset_ids: list[str],
        instruction: str,
        title: str | None = None,
    ) -> ReportPlan:
        return await ReportingPlanner().create_plan(
            template=template,
            data_sources=[],
            instruction=instruction,
            dataset_ids=dataset_ids,
            title=title,
        )
