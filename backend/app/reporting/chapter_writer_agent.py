from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from ..core.models import Evidence, RequestContext, User
from ..core.ports import LlmService
from ..core.reports import (
    MetricFinding,
    ChapterDraft,
    ChapterWriterInput,
    ChapterWriterResult,
    ReportGenerationSession,
    UserQuestion,
)
from ..core.tooling import ToolContext, ToolRegistry, ToolResult
from .chapter_writer import ChapterWriter

from ..infrastructure.logging import preview, work_context

logger = logging.getLogger(__name__)


class ChapterWriterAgent(ChapterWriter):
    """Generate one report chapter with a bounded read-only ReAct loop.

    The agent has two phases: it first lets the model request multiple reads,
    feeding successful observations and recoverable errors back into the loop;
    then it performs one tool-free composition call using the template and all
    successfully read rows.
    """

    #: Research fills in aggregations; it does not write queries and it does
    #: not do arithmetic. ``aggregate_dataset`` computes every number, and
    #: ``read_dataset`` exists only for the rows a template table lists
    #: verbatim. Free-form SQL is deliberately absent: it put the calculation
    #: back in the model's hands, just in another language.
    _read_tool_names = {"aggregate_dataset", "read_dataset"}

    def __init__(
        self,
        llm: LlmService,
        tools: ToolRegistry,
        max_iterations: int = 8,
        max_attempts_per_metric: int = 6,
        max_retries_per_error: int = 2,
        max_rows_per_read: int = 100,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        if max_attempts_per_metric < 1:
            raise ValueError("max_attempts_per_metric must be positive")
        self.llm = llm
        self.tools = tools
        self.max_iterations = max_iterations
        self.max_attempts_per_metric = max_attempts_per_metric
        self.max_retries_per_error = max_retries_per_error
        self.max_rows_per_read = max_rows_per_read

    async def write(
        self,
        input: ChapterWriterInput,
        session: ReportGenerationSession,
        checkpoint: Callable[[], Awaitable[None]] | None = None,
    ) -> ChapterWriterResult:
        logger.info("chapter_agent_started session_id=%s section_id=%s", session.session_id, input.section.section_id)
        research = await self._research_loop(input, session, checkpoint)
        if research["status"] != "ready_for_writing":
            return ChapterWriterResult(
                status=research["status"],
                questions=research.get("questions", []),
                error=research.get("error"),
            )
        if checkpoint is not None:
            await checkpoint()
        return await self._compose_chapter(
            input,
            session,
            research["findings"],
            research["evidence"],
        )

    async def _research_loop(
        self,
        input: ChapterWriterInput,
        session: ReportGenerationSession,
        checkpoint: Callable[[], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """Fetch data one metric at a time.

        Each metric gets its own bounded attempt budget and its own verdict, so
        a chapter with many metrics is not squeezed into a single shared budget,
        and a metric that cannot be located is reported by name instead of
        dragging the whole chapter down with it.
        """
        context = self._tool_context(input, session)
        tool_schemas = [
            schema for schema in self.tools.schemas(context) if schema["name"] in self._read_tool_names
        ]
        cache: dict[str, dict[str, Any]] = {}
        findings: list[MetricFinding] = []
        evidence: list[Evidence] = []
        unresolved: list[tuple[str, str]] = []

        targets = [metric for metric in input.metrics if metric not in set(input.dropped_metrics)]
        if not targets and self._table_headers(input):
            # A chapter can carry a table without carrying a named metric; the
            # table still needs this period's rows.
            targets = [f"{input.section.title}表格所需数据"]
        if not targets:
            # Narrative chapters carry no metrics and need no data of their own.
            return {"status": "ready_for_writing", "findings": [], "evidence": []}

        for index, metric in enumerate(targets, start=1):
            if checkpoint is not None:
                await checkpoint()
            logger.info(
                "metric_research_started session_id=%s section_id=%s metric=%s (%d/%d)",
                session.session_id, input.section.section_id, metric, index, len(targets),
            )
            # Tag the model calls this metric makes. Without it a log of two
            # reports generating at once is an unattributable interleave, and
            # there is no way to tell which metric a retry storm belongs to.
            with work_context(session=session.session_id, section=input.section.section_id, metric=metric):
                outcome = await self._research_metric(
                    metric, input, session, context, tool_schemas, cache
                )
            if outcome["status"] == "failed":
                return outcome
            if outcome["status"] == "resolved":
                findings.append(
                    MetricFinding(
                        metric=metric,
                        value=outcome["value"],
                        basis=outcome.get("basis"),
                        reads=outcome["reads"],
                    )
                )
                evidence.extend(outcome["evidence"])
                # The settled value is what the chapter will actually print, so
                # it belongs in the log in full — counting resolved metrics said
                # nothing about whether any of them was right.
                logger.info(
                    "metric_resolved session_id=%s section_id=%s metric=%s value=%s basis=%s reads=%d",
                    session.session_id,
                    input.section.section_id,
                    metric,
                    preview(outcome["value"], limit=600),
                    preview(outcome.get("basis"), limit=300),
                    len(outcome["reads"]),
                )
            else:
                reason = outcome.get("reason") or "未能在数据源中定位该指标"
                unresolved.append((metric, reason))
                logger.info(
                    "metric_unresolved session_id=%s section_id=%s metric=%s reason=%s",
                    session.session_id, input.section.section_id, metric, preview(reason, limit=300),
                )

        logger.info(
            "chapter_research_done session_id=%s section_id=%s resolved=%d unresolved=%s reads=%d",
            session.session_id,
            input.section.section_id,
            len(findings),
            [metric for metric, _ in unresolved] or "-",
            len(cache),
        )
        if unresolved:
            return {
                "status": "waiting_user",
                # One question per metric: a single question naming every metric
                # at once cannot be acted on.
                "questions": [
                    UserQuestion(
                        question_id=f"question_{uuid4().hex}",
                        chapter_id=input.section.section_id,
                        metric=metric,
                        expected="dataset",
                        content=reason,
                    )
                    for metric, reason in unresolved
                ],
                "findings": findings,
                "evidence": evidence,
            }
        return {"status": "ready_for_writing", "findings": findings, "evidence": evidence}

    async def _research_metric(
        self,
        metric: str,
        input: ChapterWriterInput,
        session: ReportGenerationSession,
        context: ToolContext,
        tool_schemas: list[dict[str, Any]],
        cache: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._metric_system_prompt()},
            {"role": "user", "content": self._json_text(self._metric_request(metric, input))},
        ]
        reads: list[dict[str, Any]] = []
        evidence: list[Evidence] = []
        error_counts: dict[str, int] = {}
        challenged = False
        nudges = 0

        for turn in range(1, self.max_attempts_per_metric + 1):
            response = await self.llm.complete(messages, tool_schemas)
            self._log_turn(session, input, metric, turn, messages, response)
            tool_calls = response.get("tool_calls") or []
            if not tool_calls:
                decision = self._parse_json(response.get("content", ""))
                status = decision.get("status") if isinstance(decision, dict) else None
                if status == "failed":
                    return {"status": "failed", "error": decision.get("error") or "Research failed"}
                if status == "unresolved":
                    # A metric declared missing after successful reads is
                    # challenged once with what was actually read, because the
                    # model has been observed calling data missing while holding it.
                    if reads and not challenged:
                        challenged = True
                        logger.info(
                            "metric_unresolved_challenged session_id=%s metric=%s reads=%d",
                            session.session_id, metric, len(reads),
                        )
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "你已经成功读到了上述数据。请再确认一次：这些数据里真的无法得到"
                                    f"「{metric}」吗？如果可以（哪怕需要按行筛选或简单相加），"
                                    '返回 {"status":"resolved"}；确实不行再返回 unresolved 并说明原因。'
                                ),
                            }
                        )
                        continue
                    return {"status": "unresolved", "reason": str(decision.get("reason") or "")}
                if status == "resolved":
                    value = str(decision.get("value") or "").strip()
                    if value:
                        return {
                            "status": "resolved",
                            "value": value,
                            "basis": str(decision.get("basis") or "").strip() or None,
                            "reads": reads,
                            "evidence": evidence,
                        }
                # The model routinely works the calculation out in prose and
                # never emits the JSON; the answer is right there, so keep
                # asking for it in the remaining budget instead of discarding it.
                if reads:
                    nudges += 1
                    messages.append({"role": "user", "content": self._value_nudge(metric)})
                    continue
                return {
                    "status": "unresolved",
                    "reason": f"未能为「{metric}」确定取值",
                }

            for call in tool_calls:
                name = call.get("name")
                arguments = self._arguments(call.get("arguments", {}))
                cache_key = self._cache_key(name, arguments)
                cached = cache.get(cache_key)
                if cached is not None:
                    result_payload, success, detail = cached["payload"], True, "cache"
                else:
                    result = await self._execute_read_tool(name, arguments, input, context)
                    success = result.success
                    result_payload = self._tool_data_payload(result) if success else None
                    detail = preview(result.data if success else result.error, limit=300)
                    if success:
                        cache[cache_key] = {"payload": result_payload}
                        evidence.extend(
                            item for item in result.evidence if isinstance(item, Evidence)
                        )
                logger.info(
                    "chapter_tool_call session_id=%s section_id=%s metric=%s tool=%s success=%s args=%s result=%s",
                    session.session_id,
                    input.section.section_id,
                    metric,
                    name,
                    success,
                    preview(arguments, limit=200),
                    detail,
                )
                call_id = call.get("id") or f"call_{uuid4().hex}"
                messages.append(
                    {
                        "role": "assistant",
                        "content": response.get("content") or None,
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {"name": name, "arguments": self._json_text(arguments)},
                            }
                        ],
                    }
                )
                if success:
                    read = {"read_id": f"read_{uuid4().hex}", **result_payload}
                    reads.append(read)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": self._json_text({"success": True, "data": result_payload}),
                        }
                    )
                    continue

                error_key = result.error or "tool_error"
                error_counts[error_key] = error_counts.get(error_key, 0) + 1
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": self._json_text(self._tool_error_payload(result)),
                    }
                )
                if not self._retryable(result):
                    return {"status": "failed", "error": result.error or result.result_for_llm}
                if error_counts[error_key] > self.max_retries_per_error:
                    return {
                        "status": "unresolved",
                        "reason": f"读取「{metric}」时反复失败：{result.result_for_llm}",
                    }
                messages.append(
                    {
                        "role": "user",
                        "content": "读取失败。请根据工具错误修正参数，不要猜测不存在的数据。",
                    }
                )

        return {
            "status": "unresolved",
            "reason": (
                f"在 {self.max_attempts_per_metric} 次尝试内未能确定「{metric}」的取值"
                if reads
                else f"在 {self.max_attempts_per_metric} 次尝试内未能定位「{metric}」所需的数据"
            ),
        }

    @staticmethod
    def _value_nudge(metric: str) -> str:
        return (
            f"请现在给出「{metric}」的取值。本条回复只允许输出一个 JSON 对象，"
            "不要输出计算过程、说明或 Markdown：\n"
            '{"status":"resolved","value":"<含单位的确定取值，需要分项时一并写在这里>",'
            '"basis":"<取自哪张表、如何得到>"}\n'
            "如果确实无法得到，才输出 "
            '{"status":"unresolved","reason":"<原因>"}。'
        )

    def _tool_context(
        self,
        input: ChapterWriterInput,
        session: ReportGenerationSession,
    ) -> ToolContext:
        return ToolContext(
            request=RequestContext(
                user=User(id=session.user_id),
                conversation_id=session.session_id,
                metadata={"dataset_ids": [source.dataset_id for source in input.data_sources]},
            ),
            metadata={
                "allowed_dataset_ids": [source.dataset_id for source in input.data_sources],
                "source_types": {source.dataset_id: source.source_type for source in input.data_sources},
            },
        )

    @staticmethod
    def _cache_key(name: str | None, arguments: dict[str, Any]) -> str:
        return json.dumps([name, arguments], ensure_ascii=False, sort_keys=True, default=str)


    async def _compose_chapter(
        self,
        input: ChapterWriterInput,
        session: ReportGenerationSession,
        findings: list[MetricFinding],
        evidence: list[Evidence],
    ) -> ChapterWriterResult:
        request = self._composition_request(input, findings)
        messages = [
            {"role": "system", "content": self._composition_system_prompt()},
            {"role": "user", "content": self._json_text(request)},
        ]
        # Writing a whole chapter is the slowest call in the run and the one
        # gateways time out on; streaming keeps the connection alive.
        response = await self.llm.complete_streaming(messages, [])
        logger.info("chapter_composition_llm_completed session_id=%s section_id=%s", session.session_id, input.section.section_id)
        payload = self._parse_json(response.get("content", ""))
        # Questions are the signal, not the status field: a model that hedges in
        # the prose while reporting "completed" would otherwise have its request
        # for data silently dropped.
        questions = self._questions(payload.get("questions", []))
        if questions or payload.get("status") == "waiting_user":
            # A chapter that parks with nothing to ask would stall the run in
            # silence, so fall back to asking for the metrics it was planned to
            # cover, using the model's own explanation as the reason.
            if not questions:
                logger.warning(
                    "chapter_parked_without_questions session_id=%s section_id=%s",
                    session.session_id, input.section.section_id,
                )
                questions = [self._fallback_question(input, str(payload.get("content") or ""))]
            return ChapterWriterResult(status="waiting_user", questions=questions)
        if payload.get("status") == "failed":
            return ChapterWriterResult(status="failed", error=payload.get("error") or "Chapter composition failed")

        content = self._strip_own_heading(
            str(payload.get("content") or response.get("content", "")).strip(),
            input.section.title,
        )
        draft = ChapterDraft(
            chapter_id=input.section.section_id,
            section_id=input.section.section_id,
            title=input.section.title,
            content=content,
            evidence=evidence,
            assumptions=self._string_list(payload.get("assumptions")),
        )
        return ChapterWriterResult(status="completed", draft=draft)

    async def _execute_read_tool(
        self,
        name: str | None,
        arguments: dict[str, Any],
        input: ChapterWriterInput,
        context: ToolContext,
    ) -> ToolResult:
        if name not in self._read_tool_names:
            return ToolResult(success=False, result_for_llm=f"Unsupported read tool: {name}", error="unsupported_tool")
        dataset_id = arguments.get("dataset_id")
        source = next((item for item in input.data_sources if item.dataset_id == dataset_id), None)
        if source is None:
            return ToolResult(success=False, result_for_llm=f"Dataset is not allowed: {dataset_id}", error="dataset_not_allowed")
        arguments = dict(arguments)
        if "limit" in arguments:
            arguments["limit"] = min(int(arguments["limit"]), self.max_rows_per_read)
        else:
            arguments["limit"] = self.max_rows_per_read
        return await self.tools.execute(name, context, arguments)

    @staticmethod
    def _log_turn(
        session: ReportGenerationSession,
        input: ChapterWriterInput,
        metric: str,
        turn: int,
        messages: list[dict[str, Any]],
        response: dict[str, Any],
    ) -> None:
        """Dump one metric turn in full, at DEBUG.

        A metric that came back wrong can only be diagnosed by reading what the
        model was actually shown, and the INFO lines carry one truncated
        message out of a conversation that may be ten long. This is off by
        default because it is verbatim prompt text: turn it on with
        ``LOG_LEVEL=DEBUG`` when a metric misbehaves.
        """
        if not logger.isEnabledFor(logging.DEBUG):
            return
        rendered = [
            {
                "role": message.get("role"),
                "content": preview(message.get("content"), limit=2000),
                **({"tool_calls": message["tool_calls"]} if message.get("tool_calls") else {}),
            }
            for message in messages
        ]
        logger.debug(
            "metric_turn session_id=%s section_id=%s metric=%s turn=%d messages=%s reply=%s",
            session.session_id,
            input.section.section_id,
            metric,
            turn,
            preview(rendered, limit=8000),
            preview(
                {
                    "content": response.get("content"),
                    "tool_calls": response.get("tool_calls"),
                },
                limit=2000,
            ),
        )

    @staticmethod
    def _tool_data_payload(result: ToolResult) -> dict[str, Any]:
        data = result.data
        if hasattr(data, "model_dump"):
            value = data.model_dump(mode="json")
        elif isinstance(data, list):
            value = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in data]
        else:
            value = data
        return value if isinstance(value, dict) else {"value": value, "summary": result.result_for_llm}

    @staticmethod
    def _tool_error_payload(result: ToolResult) -> dict[str, Any]:
        return {
            "success": False,
            "error_code": result.error or "tool_error",
            "message": result.result_for_llm,
            "details": result.metadata,
        }

    @staticmethod
    def _retryable(result: ToolResult) -> bool:
        return result.error not in {"access_denied", "dataset_not_allowed", "unsupported_tool"}

    @staticmethod
    def _arguments(arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                value = json.loads(arguments)
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def _parse_json(content: Any) -> dict[str, Any]:
        if not isinstance(content, str):
            return {}
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            text = text.rsplit("```", 1)[0].strip()
        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _json_text(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _questions(values: Any) -> list[UserQuestion]:
        if not isinstance(values, list):
            values = [values] if isinstance(values, dict) else []
        result: list[UserQuestion] = []
        for value in values:
            if isinstance(value, UserQuestion):
                result.append(value)
                continue
            if not isinstance(value, dict) or not value.get("content"):
                continue
            # The model is not asked to invent ids, and a missing one must not
            # fail the whole report.
            payload = {"question_id": f"question_{uuid4().hex}", **value}
            try:
                result.append(UserQuestion.model_validate(payload))
            except ValidationError as exc:
                logger.warning("chapter_question_discarded payload=%s error=%s", preview(value), exc)
        return result

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _fallback_question(input: ChapterWriterInput, reason: str) -> UserQuestion:
        summary = " ".join(reason.split())
        return UserQuestion(
            question_id=f"question_{uuid4().hex}",
            chapter_id=input.section.section_id,
            metric="、".join(input.metrics) or input.section.title,
            expected="dataset",
            content=(summary[:200] or f"「{input.section.title}」缺少可用数据，请补充后继续。"),
        )

    @staticmethod
    def _research_question(result: ToolResult) -> UserQuestion:
        return UserQuestion(
            question_id=f"question_{uuid4().hex}",
            content="请确认本章节需要读取的数据范围或字段。",
            reason=result.result_for_llm,
        )

    @staticmethod
    def _metric_system_prompt() -> str:
        return (
            "你是报告章节取数智能体。本轮只为 metric 这一个指标取数，不要为其他指标取数。\n"
            "你不做任何算术。所有求和、计数、去重、平均、最大最小都通过 aggregate_dataset "
            "交给数据源计算：你只负责填表——选哪张 sheet、按哪些列筛选、按哪些列分组、"
            "对哪一列用哪个函数。不要把多行数字读回来自己相加，也不要自己推算比例或增减。\n"
            "1) 先看 data_sources 的 sheets/columns，以及各 sheet 的 value_enums（列的全部取值）、"
            "value_ranges（取值范围），据此确定 filters，不要凭样例行猜测；\n"
            "2) 挑粒度最贴近该指标的那张 sheet：已有汇总表、台账表或月度表能直接算出该指标就用它；"
            "需要按客户去重时用 count_distinct，数据源会替你去重；\n"
            "3) global_context.report_period 是已经确定的报告期间，直接写进 filters 即可"
            "（月份/日期可以写成 '2026-01' 这样的文本，用 between 取区间）；"
            "不要为核实数据是否覆盖该期间而反复试探——那会耗尽本指标的取数预算；"
            "若数据确实覆盖不到该期间，直接返回 unresolved 并说明，不要自行改口径；\n"
            "4) 报告计划里的指标是业务口径，不是字段名，需要你从字段语义映射过去；\n"
            "5) 需要分项时用 group_by 一次取回，不要一个分项调一次；\n"
            "6) read_dataset 只用于模板表格需要逐行照抄的明细，任何汇总数字都不许由它得出；\n"
            "7) 工具报错时根据错误信息修正参数重试；\n"
            "8) 拿到结果后返回："
            "{\"status\":\"resolved\",\"value\":\"<含单位的确定取值>\",\"basis\":\"<取自哪张表、怎么聚合的>\"}。"
            "value 里的每一个数字都必须原样抄自工具返回，不得四舍五入成另一个数、不得自行折算单位；"
            "该条回复必须只包含这个 JSON 对象，不要输出计算过程——只写在文字里的结果会被丢弃；"
            "需要多个分项时把它们一并写进 value（例如「华东 63,172,480 元；华南 37,061,440 元」）。"
            "确实无法从任何数据源得到该指标，才返回 {\"status\":\"unresolved\",\"reason\":\"...\"}——"
            "用户没有补充的指标会被直接从报告里去掉，所以这不是失败，不要为了凑一个数而自己估算。"
        )

    @staticmethod
    def _table_headers(input: ChapterWriterInput) -> list[Any]:
        return [
            block.get("header")
            for section in [input.section, *input.subsections]
            for block in section.template_blocks
            if block.get("type") == "table"
        ]

    @classmethod
    def _metric_request(cls, metric: str, input: ChapterWriterInput) -> dict[str, Any]:
        table_headers = cls._table_headers(input)
        # Field order is the cache key's prefix: everything shared by the
        # chapter's metrics comes first and the metric itself comes last, so
        # repeated calls can hit the provider's prompt cache instead of being
        # billed as fresh input each time.
        return {
            "data_sources": [source.model_dump() for source in input.data_sources],
            "chapter_title": input.section.title,
            "table_headers": table_headers,
            "global_context": input.global_context.model_dump(),
            "user_instruction": input.user_instruction,
            "supplements": [item.model_dump(exclude_none=True) for item in input.supplements],
            "metric": metric,
        }

    @staticmethod
    def _research_system_prompt() -> str:
        return (
            "你是报告章节取数智能体。取数通过 aggregate_dataset 完成：选 sheet、填 filters、"
            "填 group_by、对某列选 sum/count/count_distinct/avg/min/max，由数据源计算，你自己不做算术。"
            "read_dataset 只用于需要逐行照抄的明细，不用它得出汇总数字。"
            "报告计划中的指标和全局维度是业务目标，不是底层字段名；必须先查看元数据再定位数据。"
            "章节模板里如果有表格，要取到足以填满该表每一列的数据。"
            "supplements 是用户已经补充的数据，视同已读到的真实数据，不要再为它取数；"
            "dropped_metrics 中的指标已被用户移除，不要为它们取数。"
            "工具报错时根据错误修正参数；无法确定时返回 waiting_user。"
            "数据足够后返回 JSON：{\"status\":\"ready_for_writing\"}。"
        )

    @staticmethod
    def _composition_system_prompt() -> str:
        return (
            "你是报告章节写作智能体。chapter.blocks 与 subsections[].blocks 来自一份历史报告，"
            "只提供章节结构、行文风格和表格的列；其中出现的任何数字、比例、排名和结论都属于历史期间，"
            "不得引用、不得沿用，也不得作为本期结论的依据。"
            "本期的每一个数字和每一个判断都必须来自 findings 与 supplements。"
            "围绕 metrics、report_period 和 dimensions 组织内容，不编造事实，不调用工具，不做复杂计算。\n"
            "1) content 中不要输出本章节自己的标题，外层会统一添加；\n"
            "2) 每个子节必须原样输出它的 heading 字段作为标题行，顺序与 subsections 一致；"
            "子节之间的过渡和章级总述由你组织，不要为空子节硬凑内容；\n"
            "3) type 为 table 的块只给出列名（header）：请按这些列、用本期数据生成整张表，"
            "模板表里的历史行不会给你，凡是表内的数字都必须整行替换为本期数据，"
            "行数由本期数据决定（example_row_count 仅供参考），"
            "并把表格以 Markdown 形式直接写在 content 里对应位置——放进 content 之外的字段会丢失；\n"
            "4) findings 是取数阶段已经算定的取值：正文和表格中的每一个数字都必须直接引用 "
            "findings.value 或 supplements.value，不得重新计算、不得改写成另一个数，"
            "更不得让正文与表格对同一个量给出不同的值；需要派生的比例或差额也必须由这些既定值算出并前后一致；\n"
            "5) supplements 是用户补充的取值，note 是其口径，同样直接使用；\n"
            "6) dropped_metrics 中的指标已被用户移除：正文中不得出现相关表述，"
            "也不要说明它为什么缺失，当作报告从未要求过这个指标；\n"
            "7) metrics 为空时本章不承载数据指标（前言、说明、数据来源这类叙述性章节），"
            "依据 blocks 改写成正式表述即可，不要因为缺数据而提问；\n"
            "8) 某个 metrics 在 findings 和 supplements 中都没有时，不要估算也不要一句“暂无法判断”带过，"
            "用 questions 抛出：question 需带 metric（缺的指标名）和 expected"
            "（value 表示一个数值，dataset 表示需要另一份数据），content 说明为什么需要它。"
            "只要抛出了 questions，status 就必须是 waiting_user，"
            "不要一边在正文写“待补充后再计算”一边把 status 标成 completed；"
            "findings 里已经给出的指标不得再声称缺失。\n"
            "assumptions 只写与数据口径、单位、时间范围、缺失或去重相关的说明，面向报告读者，"
            "不要复述本提示词，也不要提及 blocks、findings 等内部字段。\n"
            "返回 JSON：status、content、assumptions、questions。"
        )

    @classmethod
    def _composition_request(
        cls,
        input: ChapterWriterInput,
        findings: list[MetricFinding],
    ) -> dict[str, Any]:
        """Only what writing needs.

        The section models carry parser bookkeeping (ids, order, metadata) and
        say the same thing twice — every table appears both as Markdown inside
        template_text and as a structured block. Sending both doubles the
        template and gives the model two versions to reconcile.
        """
        return {
            "chapter": {
                "title": input.section.title,
                "blocks": cls._writable_blocks(input.section),
            },
            "subsections": [
                {
                    "title": section.title,
                    "heading": cls._subsection_heading(input, section),
                    "blocks": cls._writable_blocks(section),
                }
                for section in input.subsections
            ],
            "report_period": input.global_context.report_period,
            "dimensions": input.global_context.dimensions,
            "metrics": input.metrics,
            "report_outline": input.report_outline,
            "user_instruction": input.user_instruction,
            # Settled values, not raw rows: writing narrates them and must not
            # arrive at a different number for the same quantity.
            "findings": [
                {"metric": item.metric, "value": item.value, "basis": item.basis}
                for item in findings
            ],
            "supplements": [item.model_dump(exclude_none=True) for item in input.supplements],
            "dropped_metrics": input.dropped_metrics,
        }

    @staticmethod
    def _writable_blocks(section: ReportTemplateSection) -> list[dict[str, Any]]:
        """The template's shape, with its historical figures taken out.

        A table's old rows are last period's answers. Leaving them in gives the
        model something to copy and forces the prompt to argue against it; the
        column names are the part worth keeping.
        """
        blocks: list[dict[str, Any]] = []
        for block in section.template_blocks:
            if block.get("type") == "table":
                blocks.append(
                    {
                        "type": "table",
                        "header": block.get("header", []),
                        "example_row_count": len(block.get("rows") or []),
                    }
                )
            elif block.get("type") == "paragraph":
                blocks.append({"type": "paragraph", "text": block.get("text", "")})
        return blocks

    @staticmethod
    def _subsection_heading(input: ChapterWriterInput, section: ReportTemplateSection) -> str:
        depth = max(1, section.level - input.section.level)
        return f"{'#' * (2 + depth)} {section.title}"

    @staticmethod
    def _subsection_requests(input: ChapterWriterInput) -> list[dict[str, Any]]:
        """Each subsection plus the exact markdown heading line to emit for it.

        The chapter itself renders as an H2, so a subsection sits one level
        deeper than its distance from the chapter root.
        """
        root_level = input.section.level
        result: list[dict[str, Any]] = []
        for section in input.subsections:
            depth = max(1, section.level - root_level)
            result.append({**section.model_dump(), "heading": f"{'#' * (2 + depth)} {section.title}"})
        return result

    @staticmethod
    def _strip_own_heading(content: str, title: str) -> str:
        """Drop a chapter heading the model emitted anyway; the renderer adds it."""
        lines = content.split("\n")
        if not lines:
            return content
        first = lines[0].strip()
        if first.startswith("#") and first.lstrip("#").strip() == title.strip():
            return "\n".join(lines[1:]).strip()
        return content

    @staticmethod
    def _research_request(input: ChapterWriterInput) -> dict[str, Any]:
        return {
            "chapter": input.section.model_dump(),
            "subsections": [section.model_dump() for section in input.subsections],
            "chapter_plan": input.chapter_plan.model_dump() if input.chapter_plan else None,
            "global_context": input.global_context.model_dump(),
            "metrics": input.metrics,
            "report_outline": input.report_outline,
            "data_sources": [source.model_dump() for source in input.data_sources],
            "user_instruction": input.user_instruction,
            "supplements": [item.model_dump() for item in input.supplements],
            "dropped_metrics": input.dropped_metrics,
        }
