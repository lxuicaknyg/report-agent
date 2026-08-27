from __future__ import annotations

from ..core.models import DatasetProfile, Evidence, ReportDraft


class ReportService:
    """报告领域服务；先生成可验证 Markdown，再接入 DOCX/PDF 渲染器。"""

    def create_profile_report(self, profile: DatasetProfile, title: str | None = None) -> ReportDraft:
        dataset = profile.dataset
        summary = f"数据集 {dataset.name} 共包含 {dataset.row_count or '未知'} 行，字段数为 {len(dataset.columns)}。"
        sections = [
            {"title": "数据概览", "content": summary},
            {"title": "字段信息", "content": [column.model_dump() for column in dataset.columns]},
            {"title": "数据质量", "content": {"missing_values": profile.missing_values, "distinct_values": profile.distinct_values, "warnings": profile.warnings}},
            {"title": "样例数据", "content": profile.sample_rows},
        ]
        evidence = [Evidence(evidence_id=f"profile:{dataset.dataset_id}", kind="dataset", title="Dataset profile", source=dataset.dataset_id, value=profile.model_dump())]
        return ReportDraft(title=title or f"{dataset.name} 数据分析报告", executive_summary=summary, sections=sections, evidence=evidence)

    @staticmethod
    def to_markdown(report: ReportDraft) -> str:
        lines = [f"# {report.title}", "", "## 摘要", "", report.executive_summary, ""]
        for section in report.sections:
            lines.extend([f"## {section['title']}", "", f"```json\n{section['content']}\n```", ""])
        lines.extend(["## 证据", ""])
        for evidence in report.evidence:
            lines.append(f"- `{evidence.evidence_id}`：{evidence.title}，来源 `{evidence.source}`")
        return "\n".join(lines)
