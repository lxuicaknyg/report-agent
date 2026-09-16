from __future__ import annotations

import json
import logging
import re
from uuid import uuid4
from typing import Any

from ..core.models import utc_now
from ..core.ports import LlmService
from ..core.reports import (
    ChapterPlan,
    DataSourceMetadata,
    ReportGlobalContext,
    ReportPlan,
    ReportTemplate,
    SubchapterPlan,
    TemplateChapter,
    group_template_chapters,
)

logger = logging.getLogger(__name__)


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

    async def revise_plan(
        self,
        plan: ReportPlan,
        template: ReportTemplate,
        data_sources: list[DataSourceMetadata],
        feedback: str,
    ) -> ReportPlan:
        """Produce the next plan version from a natural-language revision request.

        The user edits the plan by talking about it, so every accepted revision
        becomes a new version that goes back to ``awaiting_confirmation``.
        """
        if self.llm is None:
            raise ValueError("Plan revision requires a configured model")
        response = await self.llm.complete(
            [
                {"role": "system", "content": self._revise_system_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "current_plan": plan.model_dump(mode="json"),
                            "template": self._template_payload(template),
                            "data_sources": [source.model_dump(mode="json") for source in data_sources],
                            "original_instruction": plan.instruction,
                            "revision_request": feedback,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            [],
        )
        chapters, global_context, title = self._parse_plan_payload(
            self._parse_json(response.get("content", "")),
            template,
            require_every_section=False,
        )
        return plan.model_copy(
            update={
                "plan_id": f"plan_{uuid4().hex}",
                "version": plan.version + 1,
                "status": "awaiting_confirmation",
                "title": title,
                "global_context": global_context,
                "chapters": chapters,
                "assembly_order": [chapter.section_id for chapter in chapters],
                "created_at": utc_now(),
            }
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
                            "template": self._template_payload(template),
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
        return self._parse_plan_payload(
            self._parse_json(response.get("content", "")),
            template,
            require_every_section=True,
        )

    @staticmethod
    def _template_payload(template: ReportTemplate) -> dict[str, Any]:
        """The template as a chapter tree, which is the shape the plan mirrors."""
        return {
            "template_id": template.template_id,
            "filename": template.filename,
            "title": template.title,
            "assembly_rules": template.assembly_rules,
            "chapters": [
                {
                    **chapter.root.model_dump(mode="json"),
                    "subsections": [item.model_dump(mode="json") for item in chapter.subsections],
                }
                for chapter in group_template_chapters(template.sections)
            ],
        }

    def _parse_plan_payload(
        self,
        payload: dict[str, Any],
        template: ReportTemplate,
        *,
        require_every_section: bool,
    ) -> tuple[list[ChapterPlan], ReportGlobalContext, str]:
        """Validate a model-authored plan against the template's chapter tree.

        A chapter is a top-level heading together with every deeper heading
        under it. Revisions may drop or reorder either level on the user's
        request; initial planning requires the whole tree. Heading levels
        always come from the template, never from the model.
        """
        if not payload:
            raise ValueError("Report planner model returned invalid JSON")

        template_chapters = group_template_chapters(template.sections)
        by_root = {chapter.root.section_id: chapter for chapter in template_chapters}
        parent_of = {
            item.section_id: chapter.root.section_id
            for chapter in template_chapters
            for item in chapter.subsections
        }
        raw_chapters = payload.get("chapters")
        if not isinstance(raw_chapters, list):
            raise ValueError("Report planner model must return chapters")
        chapters_by_id: dict[str, ChapterPlan] = {}
        returned_order: list[str] = []
        relocated: dict[str, list[str]] = {}
        for raw_chapter in raw_chapters:
            if not isinstance(raw_chapter, dict):
                raise ValueError("Each report planner chapter must be an object")
            section_id = str(raw_chapter.get("section_id", "")).strip()
            template_chapter = by_root.get(section_id)
            if template_chapter is None:
                # The template's tree is authoritative, so a subsection listed as
                # a chapter is put back where it belongs rather than failing the
                # whole plan over one misplaced heading.
                parent_id = parent_of.get(section_id)
                if parent_id is None:
                    raise ValueError(f"Report planner returned unknown section_id: {section_id}")
                relocated.setdefault(parent_id, []).append(section_id)
                continue
            if section_id in chapters_by_id:
                raise ValueError(f"Report planner returned duplicate section_id: {section_id}")
            metrics = raw_chapter.get("metrics", [])
            if not isinstance(metrics, list) or not all(isinstance(metric, str) for metric in metrics):
                raise ValueError(f"Metrics must be a string list for section: {section_id}")
            chapters_by_id[section_id] = ChapterPlan(
                section_id=section_id,
                title=self._required_title(raw_chapter.get("title"), section_id),
                level=template_chapter.root.level,
                metrics=self._clean_metrics(metrics),
                subsections=self._parse_subsections(
                    raw_chapter.get("subsections"),
                    template_chapter,
                    require_every_section=require_every_section,
                ),
            )
            returned_order.append(section_id)
        if relocated:
            logger.warning(
                "planner_relocated_subsections %s",
                {parent: ids for parent, ids in relocated.items()},
            )
            for parent_id, section_ids in relocated.items():
                chapter = chapters_by_id.get(parent_id)
                if chapter is None:
                    continue  # the parent was dropped, so its subsections go too
                known = {item.section_id for item in chapter.subsections}
                available = {item.section_id: item for item in by_root[parent_id].subsections}
                chapter.subsections.extend(
                    SubchapterPlan(
                        section_id=section_id,
                        title=available[section_id].title,
                        level=available[section_id].level,
                    )
                    for section_id in section_ids
                    if section_id not in known
                )
                order = [item.section_id for item in by_root[parent_id].subsections]
                chapter.subsections.sort(key=lambda item: order.index(item.section_id))

        if require_every_section:
            if set(chapters_by_id) != set(by_root):
                raise ValueError("Report planner must return every template chapter")
            # Checked after relocation, so a subsection listed at the top level
            # counts as present rather than as missing from its parent.
            for section_id, chapter in chapters_by_id.items():
                expected = {item.section_id for item in by_root[section_id].subsections}
                if {item.section_id for item in chapter.subsections} != expected:
                    raise ValueError(
                        f"Report planner must keep every subsection of chapter: {section_id}"
                    )
            returned_order = list(by_root)
        elif not chapters_by_id:
            raise ValueError("A revised report plan must keep at least one chapter")

        raw_context = payload.get("global_context", {})
        if not isinstance(raw_context, dict):
            raise ValueError("Report planner returned an invalid global_context")
        try:
            global_context = ReportGlobalContext.model_validate(
                {**raw_context, "dimensions": self._coerce_dimensions(raw_context.get("dimensions"))}
            )
        except Exception as exc:
            raise ValueError("Report planner returned an invalid global_context") from exc
        model_title = str(payload.get("title") or template.title).strip()
        if not model_title:
            raise ValueError("Report planner returned an empty report title")
        return [chapters_by_id[section_id] for section_id in returned_order], global_context, model_title

    def _parse_subsections(
        self,
        raw_subsections: Any,
        template_chapter: TemplateChapter,
        *,
        require_every_section: bool,
    ) -> list[SubchapterPlan]:
        available = {item.section_id: item for item in template_chapter.subsections}
        if raw_subsections is None:
            # A model that omits the key keeps the template's own subsections.
            raw_subsections = [
                {"section_id": item.section_id, "title": item.title}
                for item in template_chapter.subsections
            ]
        if not isinstance(raw_subsections, list):
            raise ValueError(f"Subsections must be a list for chapter: {template_chapter.root.section_id}")

        planned: list[SubchapterPlan] = []
        for raw in raw_subsections:
            if not isinstance(raw, dict):
                raise ValueError("Each report planner subsection must be an object")
            section_id = str(raw.get("section_id", "")).strip()
            section = available.get(section_id)
            if section is None:
                raise ValueError(f"Report planner returned a subsection outside its chapter: {section_id}")
            if any(item.section_id == section_id for item in planned):
                raise ValueError(f"Report planner returned duplicate subsection: {section_id}")
            planned.append(
                SubchapterPlan(
                    section_id=section_id,
                    title=self._required_title(raw.get("title"), section_id),
                    level=section.level,
                )
            )
        return planned

    @staticmethod
    def _required_title(value: Any, section_id: str) -> str:
        title = str(value or "").strip()
        if not title:
            raise ValueError(f"Report planner returned an empty title for section: {section_id}")
        return title

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是报告计划规划器。请综合用户指令、报告模板的全部章节原文（模板可能是历史成稿）"
            "以及数据源元数据和样例，推断报告真正需要表达的业务指标、报告期间和全局维度。"
            "模板没有明确列出指标时，要从章节正文中的数字、表述、比较关系和数据源字段语义中归纳指标；"
            "不要把底层字段名原样当作业务指标，除非它本身就是用户可理解的指标名称。"
            "报告期间优先取自用户指令；用户没有指定时，"
            "依据 data_sources 各 sheet 的 value_enums / value_ranges 中时间列的实际取值，"
            "选出其中最新的一个完整期间"
            "（例如枚举里同时存在 2025-01~06 与 2026-01~06 时，应取 2026 年上半年），"
            "绝不能沿用模板里的历史期间——模板可能是上一期的成稿，照搬它的期间等于重做旧报告。"
            "同理，模板正文里的数字、排名和结论都属于历史期间，只能用来推断需要哪些指标，不能当作本期事实。"
            "计划阶段禁止确定具体 Sheet、表名、字段名、SQL、工具调用顺序或数据读取方式。"
            "全局维度的取值必须来自 value_enums，不要凭样例行猜测或漏列。"
            "章节层级：template.chapters 给出报告的章节树，每个 chapter 是一个顶级标题，"
            "subsections 是它下面的次级标题。指标只挂在 chapter 上，覆盖该章及其全部子节。"
            "必须只返回 JSON，不要 Markdown 或解释，格式为："
            "{\"title\": string, \"global_context\": {\"report_period\": string|null, \"dimensions\": object}, "
            "\"chapters\": [{\"section_id\": string, \"title\": string, \"metrics\": string[], "
            "\"subsections\": [{\"section_id\": string, \"title\": string}]}]}。"
            "chapters 必须覆盖 template.chapters 的每个顶级 section_id 并保持顺序，"
            "每个 chapter 的 subsections 必须覆盖它在模板里的全部子节。"
            "子节只能出现在所属章节的 subsections 里，绝不能作为顶级 chapter 出现。"
            "不要返回 level 字段，层级由模板决定。"
            "dimensions 的值必须是字符串；一个维度有多个取值时用「、」连接成一个字符串。"
        )

    @staticmethod
    def _revise_system_prompt() -> str:
        return (
            "你是报告计划修订器。用户会用自然语言对已有计划提出修改意见，"
            "例如调整报告期间、增删或重排章节、修改章节标题、增删关注指标。"
            "请在现有计划基础上做最小必要修改：用户没有提到的部分必须原样保留。"
            "chapters 只能取自 template.chapters 的顶级 section_id，subsections 只能取自该章节自己的子节；"
            "可以是子集，也可以调整顺序。用户要求删除某章节时就从 chapters 中移除它，"
            "它的子节会随之一起移除；只删某个小节时就从该章节的 subsections 中移除那一条。"
            "修订阶段同样禁止确定具体 Sheet、表名、字段名、SQL 或数据读取方式。"
            "必须只返回 JSON，不要 Markdown 或解释，格式为："
            "{\"title\": string, \"global_context\": {\"report_period\": string|null, \"dimensions\": object}, "
            "\"chapters\": [{\"section_id\": string, \"title\": string, \"metrics\": string[], "
            "\"subsections\": [{\"section_id\": string, \"title\": string}]}]}。"
            "不要返回 level 字段，层级由模板决定。"
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
        return [
            ChapterPlan(
                section_id=chapter.root.section_id,
                title=chapter.root.title,
                level=chapter.root.level,
                metrics=self._extract_metrics(
                    chapter.root.required_data,
                    chapter.root.instructions,
                    *(section.template_text for section in [chapter.root, *chapter.subsections]),
                ),
                subsections=[
                    SubchapterPlan(section_id=item.section_id, title=item.title, level=item.level)
                    for item in chapter.subsections
                ],
            )
            for chapter in group_template_chapters(template.sections)
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
    def _coerce_dimensions(value: Any) -> dict[str, str]:
        """Normalise model-authored dimensions to the ``dict[str, str]`` contract.

        Models legitimately answer a dimension with several values ("客户等级":
        ["A","B","C"]); rejecting the whole plan over that shape wastes a full
        planning round, so collapse it instead.
        """
        if not isinstance(value, dict):
            return {}
        result: dict[str, str] = {}
        for key, item in value.items():
            if isinstance(item, (list, tuple, set)):
                text = "、".join(str(entry).strip() for entry in item if str(entry).strip())
            elif isinstance(item, (str, int, float)):
                text = str(item).strip()
            else:
                continue
            name = str(key).strip()
            if name and text:
                result[name] = text
        return result

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
