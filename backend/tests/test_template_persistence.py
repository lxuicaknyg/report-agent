"""Uploaded templates must outlive the process that parsed them.

A report session stores only its ``template_id``. While templates lived in
memory, that id became a dangling reference on every restart: resuming a report
re-read its template and died with a KeyError. Containers restart on every
redeploy, so this was the difference between a stored report being resumable
and being scrap.
"""

import asyncio
import tempfile
from pathlib import Path

from app.core.reports import ReportTemplate
from app.infrastructure.report_repositories import PersistentReportTemplateRepository
from app.reporting.session import StoredReportTemplate


def paths() -> tuple[Path, Path]:
    root = Path(tempfile.mkdtemp())
    return root / "templates.json", root / "templates"


def stored(template_id: str = "template_abc123", owner: str | None = "7") -> StoredReportTemplate:
    return StoredReportTemplate(
        template=ReportTemplate(
            template_id=template_id,
            filename="经营分析模板.md",
            title="经营分析报告",
            owner_id=owner,
        ),
        # Bytes, not text: templates are often .docx, and the store must not
        # assume it can decode what it holds.
        content="# 经营分析报告\n\n## 一、经营概况\n".encode(),
    )


def test_a_template_survives_a_restart():
    async def run():
        path, content_dir = paths()
        await PersistentReportTemplateRepository(path, content_dir).save(stored())

        # A different instance, as a restarted process would build.
        reopened = PersistentReportTemplateRepository(path, content_dir)
        recovered = await reopened.get("template_abc123")
        assert recovered.template.title == "经营分析报告"
        assert recovered.template.filename == "经营分析模板.md"
        assert recovered.content.decode() == "# 经营分析报告\n\n## 一、经营概况\n"

    asyncio.run(run())


def test_ownership_survives_a_restart():
    """Otherwise every template comes back ownerless and its uploader loses it."""

    async def run():
        path, content_dir = paths()
        await PersistentReportTemplateRepository(path, content_dir).save(stored(owner="7"))
        reopened = PersistentReportTemplateRepository(path, content_dir)
        assert (await reopened.get("template_abc123")).template.owner_id == "7"

    asyncio.run(run())


def test_binary_content_round_trips():
    async def run():
        path, content_dir = paths()
        blob = bytes(range(256))
        repo = PersistentReportTemplateRepository(path, content_dir)
        await repo.save(
            StoredReportTemplate(
                template=ReportTemplate(template_id="template_bin", filename="t.docx", title="t"),
                content=blob,
            )
        )
        assert (await PersistentReportTemplateRepository(path, content_dir).get("template_bin")).content == blob

    asyncio.run(run())


def test_a_missing_template_is_a_keyerror():
    async def run():
        path, content_dir = paths()
        repo = PersistentReportTemplateRepository(path, content_dir)
        try:
            await repo.get("template_nope")
        except KeyError:
            return
        raise AssertionError("expected KeyError for an unknown template")

    asyncio.run(run())


def test_one_damaged_template_does_not_hide_the_others():
    """Listing is how the UI finds anything; it must degrade, not collapse."""

    async def run():
        path, content_dir = paths()
        repo = PersistentReportTemplateRepository(path, content_dir)
        await repo.save(stored("template_good"))
        await repo.save(stored("template_damaged"))
        # Metadata still recorded, bytes gone from under it.
        (content_dir / "template_damaged.bin").unlink()

        listed = await PersistentReportTemplateRepository(path, content_dir).list()
        assert [item.template.template_id for item in listed] == ["template_good"]

    asyncio.run(run())
