from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from ..core.models import Evidence, RequestContext, User
from ..core.ports import LlmService
from ..core.reports import (
    ChapterDraft,
    ChapterWriterInput,
    ChapterWriterResult,
    ReportGenerationSession,
    UserQuestion,
)
from ..core.tooling import ToolContext, ToolRegistry, ToolResult
from .chapter_writer import ChapterWriter

logger = logging.getLogger(__name__)


class ChapterWriterAgent(ChapterWriter):
    """Generate one report chapter with a bounded read-only ReAct loop.

    The agent has two phases: it first lets the model request multiple reads,
    feeding successful observations and recoverable errors back into the loop;
    then it performs one tool-free composition call using the template and all
    successfully read rows.
    """

    _read_tool_names = {"read_dataset", "query_dataset"}

    def __init__(
        self,
        llm: LlmService,
        tools: ToolRegistry,
        max_iterations: int = 8,
        max_retries_per_error: int = 2,
        max_rows_per_read: int = 100,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        self.llm = llm
        self.tools = tools
        self.max_iterations = max_iterations
        self.max_retries_per_error = max_retries_per_error
        self.max_rows_per_read = max_rows_per_read

    async def write(
        self,
        input: ChapterWriterInput,
        session: ReportGenerationSession,
    ) -> ChapterWriterResult:
        logger.info("chapter_agent_started session_id=%s section_id=%s", session.session_id, input.section.section_id)
        research = await self._research_loop(input, session)
        if research["status"] != "ready_for_writing":
            return ChapterWriterResult(
                status=research["status"],
                questions=research.get("questions", []),
                error=research.get("error"),
            )
        return await self._compose_chapter(
            input,
            session,
            research["data"],
            research["evidence"],
        )

    async def _research_loop(
        self,
        input: ChapterWriterInput,
        session: ReportGenerationSession,
    ) -> dict[str, Any]:
        context = ToolContext(
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
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._research_system_prompt()},
            {"role": "user", "content": self._json_text(self._research_request(input))},
        ]
        tool_schemas = [
            schema for schema in self.tools.schemas(context) if schema["name"] in self._read_tool_names
        ]
        collected_data: list[dict[str, Any]] = []
        collected_evidence: list[Evidence] = []
        error_counts: dict[str, int] = {}

        for _ in range(self.max_iterations):
            response = await self.llm.complete(messages, tool_schemas)
            tool_calls = response.get("tool_calls") or []
            if not tool_calls:
                decision = self._parse_json(response.get("content", ""))
                status = decision.get("status") if isinstance(decision, dict) else None
                if status == "waiting_user":
                    return {"status": "waiting_user", "questions": self._questions(decision.get("questions", []))}
                if status == "failed":
                    return {"status": "failed", "error": decision.get("error") or "Research failed"}
                return {
                    "status": "ready_for_writing",
                    "data": collected_data,
                    "evidence": collected_evidence,
                }

            for call in tool_calls:
                name = call.get("name")
                arguments = self._arguments(call.get("arguments", {}))
                result = await self._execute_read_tool(name, arguments, input, context)
                call_id = call.get("id") or f"call_{uuid4().hex}"
                messages.append(
                    {
                        "role": "assistant",
                        "content": response.get("content") or None,
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": self._json_text(arguments),
                                },
                            }
                        ],
                    }
                )
                if result.success:
                    payload = self._tool_data_payload(result)
                    collected_data.append({"read_id": f"read_{uuid4().hex}", **payload})
                    collected_evidence.extend(
                        evidence for evidence in result.evidence if isinstance(evidence, Evidence)
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": self._json_text({"success": True, "data": payload}),
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
                if not self._retryable(result) or error_counts[error_key] > self.max_retries_per_error:
                    if self._retryable(result):
                        return {
                            "status": "waiting_user",
                            "questions": [self._research_question(result)],
                        }
                    return {"status": "failed", "error": result.error or result.result_for_llm}
                messages.append(
                    {
                        "role": "user",
                        "content": "读取失败。请根据工具错误修正参数，或返回 waiting_user，不要猜测不存在的数据。",
                    }
                )

        if collected_data:
            return {"status": "ready_for_writing", "data": collected_data, "evidence": collected_evidence}
        return {
            "status": "waiting_user",
            "questions": [
                UserQuestion(
                    question_id=f"question_{uuid4().hex}",
                    chapter_id=input.section.section_id,
                    content="无法在限定次数内确定需要读取的数据，请补充读取范围或字段。",
                    reason="数据读取循环达到最大次数",
                )
            ],
        }

    async def _compose_chapter(
        self,
        input: ChapterWriterInput,
        session: ReportGenerationSession,
        data: list[dict[str, Any]],
        evidence: list[Evidence],
    ) -> ChapterWriterResult:
        request = {
            "chapter": input.section.model_dump(),
            "report_outline": input.report_outline,
            "user_instruction": input.user_instruction,
            "previous_answers": input.previous_answers,
            "collected_data": data,
        }
        messages = [
            {"role": "system", "content": self._composition_system_prompt()},
            {"role": "user", "content": self._json_text(request)},
        ]
        response = await self.llm.complete(messages, [])
        logger.info("chapter_composition_llm_completed session_id=%s section_id=%s", session.session_id, input.section.section_id)
        payload = self._parse_json(response.get("content", ""))
        if payload.get("status") == "waiting_user":
            return ChapterWriterResult(
                status="waiting_user",
                questions=self._questions(payload.get("questions", [])),
            )
        if payload.get("status") == "failed":
            return ChapterWriterResult(status="failed", error=payload.get("error") or "Chapter composition failed")

        content = str(payload.get("content") or response.get("content", "")).strip()
        draft = ChapterDraft(
            chapter_id=input.section.section_id,
            section_id=input.section.section_id,
            title=input.section.title,
            content=content,
            tables=self._list_value(payload.get("tables")),
            charts=self._list_value(payload.get("charts")),
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
        expected_tool = "read_dataset" if source.source_type in {"excel", "csv"} else "query_dataset"
        if name != expected_tool:
            return ToolResult(
                success=False,
                result_for_llm=f"Dataset {dataset_id} is {source.source_type}; use {expected_tool}",
                error="wrong_tool_for_source",
            )
        arguments = dict(arguments)
        if "limit" in arguments:
            arguments["limit"] = min(int(arguments["limit"]), self.max_rows_per_read)
        else:
            arguments["limit"] = self.max_rows_per_read
        return await self.tools.execute(name, context, arguments)

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
            elif isinstance(value, dict) and value.get("content"):
                result.append(UserQuestion.model_validate(value))
        return result

    @staticmethod
    def _list_value(value: Any) -> list[Any]:
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _research_question(result: ToolResult) -> UserQuestion:
        return UserQuestion(
            question_id=f"question_{uuid4().hex}",
            content="请确认本章节需要读取的数据范围或字段。",
            reason=result.result_for_llm,
        )

    @staticmethod
    def _research_system_prompt() -> str:
        return (
            "你是报告章节取数智能体。只能执行只读数据读取，不做聚合或复杂计算。"
            "Excel/CSV 使用 read_dataset，SQL 使用 query_dataset。可以多次读取。"
            "工具报错时根据错误修正参数；无法确定时返回 waiting_user。"
            "数据足够后返回 JSON：{\"status\":\"ready_for_writing\"}。"
        )

    @staticmethod
    def _composition_system_prompt() -> str:
        return (
            "你是报告章节写作智能体。请严格参考 chapter.template_text 和 template_blocks 的结构，"
            "只使用 collected_data 中真实存在的数据，不编造事实，不调用工具，不做复杂计算。"
            "返回 JSON：status、content、tables、charts、assumptions、questions。"
        )

    @staticmethod
    def _research_request(input: ChapterWriterInput) -> dict[str, Any]:
        return {
            "chapter": input.section.model_dump(),
            "report_outline": input.report_outline,
            "data_sources": [source.model_dump() for source in input.data_sources],
            "user_instruction": input.user_instruction,
            "previous_answers": input.previous_answers,
        }
