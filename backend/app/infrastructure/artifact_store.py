from __future__ import annotations

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

