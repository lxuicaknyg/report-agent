from __future__ import annotations

from ..core.reports import AssembledReport


class MarkdownReportRenderer:
    format = "markdown"
    content_type = "text/markdown; charset=utf-8"
    extension = ".md"

    async def render(self, report: AssembledReport) -> bytes:
        lines = [f"# {report.title}", "", "## 摘要", "", report.executive_summary, ""]
        for chapter in report.chapters:
            lines.extend([f"## {chapter.title}", "", chapter.content, ""])
            if chapter.assumptions:
                lines.extend(["### 说明", ""])
                lines.extend(f"- {assumption}" for assumption in chapter.assumptions)
                lines.append("")
        return "\n".join(lines).encode("utf-8")

