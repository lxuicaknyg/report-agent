from __future__ import annotations

import json
import re
from uuid import uuid4
from typing import Any

from ..core.ports import LlmService
from ..core.reports import ChapterPlan, DataSourceMetadata, ReportGlobalContext, ReportPlan, ReportTemplate


class ReportPlanner:
    """Create a lightweight, user-confirmable report plan with an LLM.

    The model infers business intent from the template, instruction and source
    metadata. It must not decide concrete sheets, columns, tables or SQL; that
    discovery remains the chapter agent's runtime job.
    """

    def __init__(self, llm: LlmService | None = None) -> None:
        self.llm = llm

    async def create_plan(
        self,
        template: ReportTemplate,
        data_sources: list[DataSourceMetadata],
        instruction: str,
        title: str | None = None,
        dataset_ids: list[str] | None = None,
    ) -> ReportPlan:
        if self.llm is not None:
            chapter_plans, global_context, model_title = await self._create_with_model(
                template=template,
                data_sources=data_sources,
                instruction=instruction,
                title=title,
            )
        else:
            chapter_plans = self._fallback_chapters(template)
            global_context = self._extract_global_context(instruction)
            model_title = template.title
        return ReportPlan(
            plan_id=f"plan_{uuid4().hex}",
            status="awaiting_confirmation",
            template_id=template.template_id,
            title=title or model_title or template.title,
            instruction=instruction,
            global_context=global_context,
            chapters=chapter_plans,
            assembly_order=[chapter.section_id for chapter in chapter_plans],
        )

    async def _create_with_model(
        self,
        *,
        template: ReportTemplate,
        data_sources: list[DataSourceMetadata],
        instruction: str,
        title: str | None,
    ) -> tuple[list[ChapterPlan], ReportGlobalContext, str]:
        response = await self.llm.complete(
            [
                {"role": "system", "content": self._system_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "template": template.model_dump(mode="json"),
                            "data_sources": [source.model_dump(mode="json") for source in data_sources],
                            "instruction": instruction,
                            "requested_title": title,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            [],
        )
        payload = self._parse_json(response.get("content", ""))
        if not payload:
            raise ValueError("Report planner model returned invalid JSON")

        expected_sections = sorted(template.sections, key=lambda item: item.order)
        expected_ids = [section.section_id for section in expected_sections]
        raw_chapters = payload.get("chapters")
        if not isinstance(raw_chapters, list):
            raise ValueError("Report planner model must return chapters")
        chapters_by_id: dict[str, ChapterPlan] = {}
        for raw_chapter in raw_chapters:
            if not isinstance(raw_chapter, dict):
                raise ValueError("Each report planner chapter must be an object")
            section_id = str(raw_chapter.get("section_id", "")).strip()
            if section_id not in expected_ids:
                raise ValueError(f"Report planner returned unknown section_id: {section_id}")
            if section_id in chapters_by_id:
                raise ValueError(f"Report planner returned duplicate section_id: {section_id}")
            metrics = raw_chapter.get("metrics", [])
            if not isinstance(metrics, list) or not all(isinstance(metric, str) for metric in metrics):
                raise ValueError(f"Metrics must be a string list for section: {section_id}")
            chapter_title = str(raw_chapter.get("title", "")).strip()
            if not chapter_title:
                raise ValueError(f"Report planner returned an empty title for section: {section_id}")
            chapters_by_id[section_id] = ChapterPlan(
                section_id=section_id,
                title=chapter_title,
                metrics=self._clean_metrics(metrics),
            )
        if set(chapters_by_id) != set(expected_ids):
            raise ValueError("Report planner must return every template section")

        try:
            global_context = ReportGlobalContext.model_validate(payload.get("global_context", {}))
        except Exception as exc:
            raise ValueError("Report planner returned an invalid global_context") from exc
        model_title = str(payload.get("title") or template.title).strip()
        if not model_title:
            raise ValueError("Report planner returned an empty report title")
        return [chapters_by_id[section_id] for section_id in expected_ids], global_context, model_title

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是报告计划规划器。请综合用户指令、报告模板的全部章节原文（模板可能是历史成稿）"
            "以及数据源元数据和样例，推断报告真正需要表达的业务指标、报告期间和全局维度。"
            "模板没有明确列出指标时，要从章节正文中的数字、表述、比较关系和数据源字段语义中归纳指标；"
            "不要把底层字段名原样当作业务指标，除非它本身就是用户可理解的指标名称。"
            "计划阶段禁止确定具体 Sheet、表名、字段名、SQL、工具调用顺序或数据读取方式。"
            "必须只返回 JSON，不要 Markdown 或解释，格式为："
            "{\"title\": string, \"global_context\": {\"report_period\": string|null, \"dimensions\": object}, "
            "\"chapters\": [{\"section_id\": string, \"title\": string, \"metrics\": string[]}]}。"
            "chapters 必须覆盖模板的每个 section_id，并保持模板顺序。"
        )

    @staticmethod
    def _parse_json(content: Any) -> dict[str, Any]:
        if not isinstance(content, str):
            return {}
        value = content.strip()
        if value.startswith("```"):
            value = value.split("\n", 1)[1] if "\n" in value else value
            value = value.rsplit("```", 1)[0].strip()
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            start, end = value.find("{"), value.rfind("}")
            if start < 0 or end <= start:
                return {}
            try:
                parsed = json.loads(value[start:end + 1])
            except json.JSONDecodeError:
                return {}
        return parsed if isinstance(parsed, dict) else {}

    def _fallback_chapters(self, template: ReportTemplate) -> list[ChapterPlan]:
        sections = sorted(template.sections, key=lambda item: item.order)
        return [
            ChapterPlan(
                section_id=section.section_id,
                title=section.title,
                metrics=self._extract_metrics(section.required_data, section.instructions, section.template_text),
            )
            for section in sections
        ]

    @classmethod
    def _extract_metrics(cls, required_data: list[str], *texts: str | None) -> list[str]:
        if required_data:
            return cls._clean_metrics(required_data)
        matches: list[str] = []
        for text in texts:
            if not text:
                continue
            for match in re.findall(r"(?:指标|关注指标|涉及指标)\s*[：:]\s*([^\n。；;]+)", text):
                matches.extend(re.split(r"[、,，；;|]", match))
        return cls._clean_metrics(matches)

    @staticmethod
    def _clean_metrics(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            metric = re.sub(r"^[\-*•\s]+", "", str(value)).strip()
            if metric and metric not in seen:
                seen.add(metric)
                result.append(metric)
        return result

    @staticmethod
    def _extract_global_context(instruction: str) -> ReportGlobalContext:
        period: str | None = None
        period_match = re.search(
            r"(?:报告期间|期间|时间范围)\s*[：:]\s*([^\n,，;；]+)", instruction,
        )
        if period_match:
            period = period_match.group(1).strip()
        else:
            period_match = re.search(r"(20\d{2}\s*(?:年|Q[1-4]|季度)|第[一二三四1-4]季度)", instruction, re.I)
            if period_match:
                period = period_match.group(1).strip()

        dimensions: dict[str, str] = {}
        for match in re.finditer(r"(?:机构|区域|地区|部门|维度)\s*[：:=]\s*([^\n,，;；]+)", instruction):
            label_match = re.search(r"(机构|区域|地区|部门|维度)", match.group(0))
            if label_match:
                dimensions[label_match.group(1)] = match.group(1).strip()
        return ReportGlobalContext(report_period=period, dimensions=dimensions)
