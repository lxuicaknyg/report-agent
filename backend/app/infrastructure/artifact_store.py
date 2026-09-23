from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from ..core.ports import ArtifactStore


class InMemoryArtifactStore(ArtifactStore):
    def __init__(self) -> None:
        self._artifacts: dict[str, bytes] = {}

    async def put(self, name: str, content: bytes, content_type: str) -> str:
        uri = f"memory://{uuid4().hex}/{name}"
        self._artifacts[uri] = bytes(content)
        return uri

    async def get(self, uri: str) -> bytes:
        try:
            return bytes(self._artifacts[uri])
        except KeyError as exc:
            raise KeyError(f"Artifact not found: {uri}") from exc


class FileSystemArtifactStore(ArtifactStore):
    """Keep generated reports on disk so they outlive the process.

    Sessions are persisted, and they record which artifacts they produced. An
    in-memory store made that record a lie the moment the backend restarted:
    the conversation still offered a download button, and the download 404'd.
    """

    #: Only the parts of a stored name that can be handed back to the
    #: filesystem. The real filename lives on the artifact record; this is a
    #: readable tail for the path, not an identity.
    _SAFE = re.compile(r"[^A-Za-z0-9._-]")

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str, name: str) -> Path:
        return self.root / f"{key}_{self._SAFE.sub('_', name)[-80:]}"

    async def put(self, name: str, content: bytes, content_type: str) -> str:
        key = uuid4().hex
        path = self._path(key, name)
        # Written whole then moved, so a reader never sees a half-written file.
        tmp = path.with_suffix(f"{path.suffix}.tmp")
        tmp.write_bytes(content)
        tmp.replace(path)
        return f"file://{path}"

    async def get(self, uri: str) -> bytes:
        if not uri.startswith("file://"):
            # Reports generated before artifacts were persisted recorded a
            # memory:// uri whose bytes died with that process.
            raise KeyError(f"Artifact is no longer available: {uri}")
        path = Path(uri[len("file://"):])
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise KeyError(f"Artifact not found: {uri}") from exc
        # A uri comes off a stored session, but a path that escapes the store
        # is not one this store wrote.
        if not resolved.is_relative_to(self.root.resolve()):
            raise KeyError(f"Artifact is outside the store: {uri}")
        return resolved.read_bytes()
