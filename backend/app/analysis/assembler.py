from __future__ import annotations

from ..core.reports import AssembledReport, ChapterDraft, ReportPlan, ReportTemplate


class ReportAssembler:
    async def assemble(
        self,
        template: ReportTemplate,
        plan: ReportPlan,
        drafts: dict[str, ChapterDraft],
    ) -> AssembledReport:
        chapters = [drafts[section_id] for section_id in plan.assembly_order if section_id in drafts]
        evidence = [item for chapter in chapters for item in chapter.evidence]
        return AssembledReport(
            title=plan.title,
            executive_summary=f"本报告参考模板“{template.filename}”生成，共包含 {len(chapters)} 个章节。",
            chapters=chapters,
            evidence=evidence,
            metadata={"template_id": template.template_id, "plan_id": plan.plan_id},
        )
