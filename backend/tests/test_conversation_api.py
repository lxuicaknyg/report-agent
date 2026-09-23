"""End-to-end checks over the HTTP layer: multipart intake, background
processing, and the read-only report routes the conversation hands off to."""

import io
import time

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.api.routes import conversations as conversations_route
from app.conversations.orchestrator import ConversationOrchestrator
from app.data.catalog import DataCatalog
from app.infrastructure.artifact_store import InMemoryArtifactStore
from app.infrastructure.conversation_repositories import InMemoryConversationRepository
from app.infrastructure.report_repositories import (
    InMemoryReportSessionRepository,
    InMemoryReportTemplateRepository,
)
from app.main import create_app
from app.reporting.assembler import ReportAssembler
from app.reporting.chapter_writer import StubChapterWriter
from app.reporting.planner import ReportPlanner
from app.reporting.renderer import MarkdownReportRenderer
from app.reporting.report_generation import ReportGenerationService
from app.reporting.template_parser import ReportTemplateParser
from app.api.routes import reports as reports_route

from conftest import API, sign_in

TEMPLATE_BYTES = "# 经营分析报告\n\n## 一、经营概况\n概况正文\n\n## 二、风险情况\n风险正文".encode()


def excel_bytes() -> bytes:
    workbook = Workbook()
    workbook.active.append(["value"])
    workbook.active.append([1])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def client(monkeypatch):
    reports = ReportGenerationService(
        sessions=InMemoryReportSessionRepository(),
        templates=InMemoryReportTemplateRepository(),
        template_parser=ReportTemplateParser(),
        planner=ReportPlanner(),
        writer=StubChapterWriter(),
        assembler=ReportAssembler(),
        renderer=MarkdownReportRenderer(),
        artifact_store=InMemoryArtifactStore(),
        catalog=DataCatalog(),
    )
    orchestrator = ConversationOrchestrator(
        conversations=InMemoryConversationRepository(), reports=reports
    )
    monkeypatch.setattr(conversations_route, "get_conversation_orchestrator", lambda: orchestrator)
    monkeypatch.setattr(reports_route, "get_report_generation_service", lambda: reports)
    app = create_app()
    sign_in(app)
    with TestClient(app) as test_client:
        yield test_client


def wait_for(client, url, predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(url).json()
        if predicate(payload):
            return payload
        time.sleep(0.05)
    raise AssertionError(f"condition not met within {timeout}s: {url}")


def kinds(detail) -> list[str]:
    return [message["kind"] for message in detail["messages"]]


def test_report_is_created_revised_and_downloaded_through_messages(client):
    conversation = client.post(f"{API}/conversations", json={"title": None}).json()
    url = f"{API}/conversations/{conversation['conversation_id']}"

    accepted = client.post(
        f"{url}/messages",
        data={"text": "生成 2026 年一季度经营分析报告"},
        files={
            "template_file": ("模板.md", TEMPLATE_BYTES, "text/markdown"),
            "data_file": ("data.xlsx", excel_bytes(), "application/vnd.ms-excel"),
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["role"] == "user"
    assert [item["kind"] for item in accepted.json()["attachments"]] == ["template", "data"]

    detail = wait_for(client, url, lambda payload: "plan" in kinds(payload))
    plan_message = next(item for item in detail["messages"] if item["kind"] == "plan")
    assert plan_message["payload"]["plan"]["version"] == 1
    assert detail["report_session"]["status"] == "awaiting_confirmation"

    client.post(f"{url}/messages", json={"text": "确认，开始生成"})
    detail = wait_for(client, url, lambda payload: "report" in kinds(payload))
    assert detail["report_session"]["status"] == "completed"

    session_id = detail["report_session"]["session_id"]
    report_message = next(item for item in detail["messages"] if item["kind"] == "report")
    artifact_id = report_message["payload"]["artifacts"][0]["artifact_id"]

    download = client.get(f"{API}/reports/{session_id}/artifacts/{artifact_id}")
    assert download.status_code == 200
    assert "经营分析报告" in download.content.decode("utf-8")


def test_report_write_endpoints_are_gone(client):
    # POST /reports keeps the path (GET still lists) but no longer accepts writes.
    assert client.post(f"{API}/reports", json={"instruction": "x"}).status_code == 405
    for path in (f"{API}/reports/any/plan/confirm", f"{API}/reports/any/answers", f"{API}/reports/any/resume"):
        assert client.post(path, json={}).status_code == 404


def test_empty_message_is_rejected(client):
    conversation = client.post(f"{API}/conversations", json={"title": None}).json()
    response = client.post(
        f"{API}/conversations/{conversation['conversation_id']}/messages",
        json={"text": "   "},
    )
    assert response.status_code == 400


def test_question_resolutions_travel_as_a_message(client, monkeypatch):
    """The question card submits decisions through the one write path."""
    captured: dict = {}

    async def fake_resolve(session_id, request):
        captured["session_id"] = session_id
        captured["actions"] = [(r.question_id, r.action, r.value) for r in request.resolutions]
        raise RuntimeError("stop before regeneration")

    conversation = client.post(f"{API}/conversations", json={"title": None}).json()
    url = f"{API}/conversations/{conversation['conversation_id']}"
    response = client.post(
        f"{url}/messages",
        json={
            "text": "已处理本章 2 个待补充项",
            "resolutions": [
                {"question_id": "q1", "action": "value", "value": "76400", "note": "含贴现"},
                {"question_id": "q2", "action": "drop"},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["payload"]["resolutions"][0]["value"] == "76400"
    assert response.json()["payload"]["resolutions"][1]["action"] == "drop"
