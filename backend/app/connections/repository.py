from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from ..core.connections import DataConnection


class ConnectionRepository(ABC):
    @abstractmethod
    async def save(self, connection: DataConnection) -> None: ...

    @abstractmethod
    async def get(self, connection_id: str) -> DataConnection: ...

    @abstractmethod
    async def list(self) -> list[DataConnection]: ...

    @abstractmethod
    async def delete(self, connection_id: str) -> None: ...


class InMemoryConnectionRepository(ConnectionRepository):
    def __init__(self) -> None:
        self._items: dict[str, DataConnection] = {}

    async def save(self, connection: DataConnection) -> None:
        self._items[connection.connection_id] = connection.model_copy(deep=True)

    async def get(self, connection_id: str) -> DataConnection:
        try:
            return self._items[connection_id].model_copy(deep=True)
        except KeyError as exc:
            raise KeyError(f"Data connection not found: {connection_id}") from exc

    async def list(self) -> list[DataConnection]:
        return [item.model_copy(deep=True) for item in self._items.values()]

    async def delete(self, connection_id: str) -> None:
        if connection_id not in self._items:
            raise KeyError(f"Data connection not found: {connection_id}")
        del self._items[connection_id]


class PersistentConnectionRepository(ConnectionRepository):
    """JSON-backed store, same approach as report sessions.

    The file holds credentials, so it is created with owner-only permissions.
    This is adequate for a single-tenant local deployment and is not a
    substitute for a secret manager in production.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._items: dict[str, DataConnection] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if isinstance(value, dict):
                        self._items[key] = DataConnection.model_validate(value)
        except (FileNotFoundError, OSError, ValueError):
            self._items = {}

    def _flush(self) -> None:
        payload = {key: value.model_dump(mode="json") for key, value in self._items.items()}
        tmp = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.path)

    async def save(self, connection: DataConnection) -> None:
        self._items[connection.connection_id] = connection.model_copy(deep=True)
        self._flush()

    async def get(self, connection_id: str) -> DataConnection:
        try:
            return self._items[connection_id].model_copy(deep=True)
        except KeyError as exc:
            raise KeyError(f"Data connection not found: {connection_id}") from exc

    async def list(self) -> list[DataConnection]:
        return [item.model_copy(deep=True) for item in self._items.values()]

    async def delete(self, connection_id: str) -> None:
        if connection_id not in self._items:
            raise KeyError(f"Data connection not found: {connection_id}")
        del self._items[connection_id]
        self._flush()
