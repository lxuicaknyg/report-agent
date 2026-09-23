"""Generated reports must outlive the process that wrote them.

Sessions are persisted and they record which artifacts they produced. While
artifacts lived in memory, that record became a lie on every restart: the
conversation still showed a download button and the download returned 404.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from app.infrastructure.artifact_store import FileSystemArtifactStore


def store() -> FileSystemArtifactStore:
    return FileSystemArtifactStore(Path(tempfile.mkdtemp()) / "artifacts")


def test_an_artifact_survives_a_restart():
    async def run():
        root = Path(tempfile.mkdtemp()) / "artifacts"
        uri = await FileSystemArtifactStore(root).put(
            "report_1.md", "# 报告\n正文。".encode(), "text/markdown"
        )
        # A different instance, as a restarted process would build.
        reopened = FileSystemArtifactStore(root)
        assert (await reopened.get(uri)).decode() == "# 报告\n正文。"

    asyncio.run(run())


def test_two_reports_with_the_same_name_do_not_collide():
    async def run():
        keep = store()
        first = await keep.put("report.md", b"first", "text/markdown")
        second = await keep.put("report.md", b"second", "text/markdown")
        assert first != second
        assert await keep.get(first) == b"first"
        assert await keep.get(second) == b"second"

    asyncio.run(run())


def test_a_report_written_before_artifacts_were_persisted_says_so():
    """Those sessions recorded a memory:// uri whose bytes died with the
    process. The download must fail with something a caller can explain."""

    async def run():
        with pytest.raises(KeyError, match="no longer available"):
            await store().get("memory://deadbeef/report.md")

    asyncio.run(run())


def test_a_uri_pointing_outside_the_store_is_refused():
    async def run():
        with pytest.raises(KeyError):
            await store().get("file:///etc/passwd")

    asyncio.run(run())


def test_a_missing_file_is_reported_as_missing():
    async def run():
        keep = store()
        uri = await keep.put("gone.md", b"x", "text/markdown")
        Path(uri[len("file://"):]).unlink()
        with pytest.raises(KeyError, match="not found"):
            await keep.get(uri)

    asyncio.run(run())


def test_the_stored_path_keeps_a_readable_tail():
    async def run():
        uri = await store().put("报告 2026/上半年.md", b"x", "text/markdown")
        # Whatever the report was called, the path is one the filesystem accepts.
        name = Path(uri[len("file://"):]).name
        assert "/" not in name and name.endswith(".md")

    asyncio.run(run())
