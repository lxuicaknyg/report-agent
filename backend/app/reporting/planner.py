from __future__ import annotations

from uuid import uuid4

from ..core.reports import ReportPlan, ReportTemplate


class ReportPlanner:
    """Turn a parsed template into executable chapter tasks."""

    async def create_plan(
        self,
        template: ReportTemplate,
        dataset_ids: list[str],
        instruction: str,
        title: str | None = None,
    ) -> ReportPlan:
        sections = sorted(template.sections, key=lambda item: item.order)
        return ReportPlan(
            plan_id=f"plan_{uuid4().hex}",
            template_id=template.template_id,
            title=title or template.title,
            instruction=instruction,
            sections=sections,
            assembly_order=[section.section_id for section in sections],
        )
