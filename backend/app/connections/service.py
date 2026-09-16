"""Create, test and manage database connections."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from urllib.parse import quote_plus
from uuid import uuid4

from ..core.connections import (
    DRIVER_SPECS,
    ConnectionDriver,
    ConnectionInput,
    ConnectionStatus,
    ConnectionTestResult,
    DataConnection,
)
from ..core.models import utc_now
from .repository import ConnectionRepository

logger = logging.getLogger(__name__)


class ConnectionService:
    def __init__(self, repository: ConnectionRepository, test_timeout: float = 10.0) -> None:
        self.repository = repository
        self.test_timeout = test_timeout

    # ── catalogue ─────────────────────────────────────────────────────────

    @staticmethod
    def drivers() -> list[dict[str, Any]]:
        """The supported drivers and the fields each one needs.

        Served to the frontend so the connection form is generated from the
        same definition the backend validates against.
        """
        return [
            {"driver": driver.value, **{k: v for k, v in spec.items()}}
            for driver, spec in DRIVER_SPECS.items()
        ]

    # ── CRUD ──────────────────────────────────────────────────────────────

    async def list(self) -> list[DataConnection]:
        items = await self.repository.list()
        return sorted(items, key=lambda item: item.created_at or "", reverse=True)

    async def get(self, connection_id: str) -> DataConnection:
        return await self.repository.get(connection_id)

    async def create(self, payload: ConnectionInput) -> DataConnection:
        spec = DRIVER_SPECS[payload.driver]
        self._validate(payload, spec)
        connection = DataConnection(
            connection_id=f"conn_{uuid4().hex[:12]}",
            name=payload.name,
            driver=payload.driver,
            host=payload.host,
            port=payload.port or spec["default_port"],
            database=payload.database,
            username=payload.username,
            password=payload.password or "",
            options=payload.options,
            description=payload.description,
        )
        await self.repository.save(connection)
        logger.info(
            "connection_created connection_id=%s driver=%s host=%s",
            connection.connection_id, connection.driver.value, connection.host,
        )
        return connection

    async def update(self, connection_id: str, payload: ConnectionInput) -> DataConnection:
        existing = await self.repository.get(connection_id)
        spec = DRIVER_SPECS[payload.driver]
        self._validate(payload, spec)
        # A form that never received the stored password must not wipe it by
        # sending back the blank it was rendered with.
        password = existing.password if payload.password is None else payload.password
        updated = existing.model_copy(
            update={
                "name": payload.name,
                "driver": payload.driver,
                "host": payload.host,
                "port": payload.port or spec["default_port"],
                "database": payload.database,
                "username": payload.username,
                "password": password,
                "options": payload.options,
                "description": payload.description,
                # Anything about where or who we connect as invalidates the
                # previous verdict.
                "status": ConnectionStatus.UNTESTED,
                "last_error": None,
                "updated_at": utc_now(),
            }
        )
        await self.repository.save(updated)
        logger.info("connection_updated connection_id=%s", connection_id)
        return updated

    async def delete(self, connection_id: str) -> None:
        await self.repository.delete(connection_id)
        logger.info("connection_deleted connection_id=%s", connection_id)

    # ── connectivity ──────────────────────────────────────────────────────

    async def test(self, connection_id: str) -> ConnectionTestResult:
        """Open the connection and run the cheapest possible statement."""
        connection = await self.repository.get(connection_id)
        started = time.monotonic()
        try:
            version = await asyncio.wait_for(
                asyncio.to_thread(self._probe, connection), timeout=self.test_timeout
            )
            result = ConnectionTestResult(
                success=True,
                message="连接成功",
                elapsed_ms=int((time.monotonic() - started) * 1000),
                server_version=version,
            )
            connection.status = ConnectionStatus.OK
            connection.last_error = None
        except asyncio.TimeoutError:
            result = ConnectionTestResult(
                success=False,
                message=f"连接超时（>{self.test_timeout:.0f}s），请检查网络或防火墙",
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            connection.status = ConnectionStatus.FAILED
            connection.last_error = result.message
        except Exception as exc:
            result = ConnectionTestResult(
                success=False,
                message=self._explain(exc),
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            connection.status = ConnectionStatus.FAILED
            connection.last_error = result.message
        connection.last_tested_at = utc_now()
        await self.repository.save(connection)
        logger.info(
            "connection_tested connection_id=%s success=%s elapsed_ms=%d message=%s",
            connection_id, result.success, result.elapsed_ms, result.message,
        )
        return result

    def _probe(self, connection: DataConnection) -> str | None:
        """Blocking connectivity check, run on a worker thread."""
        if connection.driver is ConnectionDriver.OPENLOOKENG:
            return self._probe_jdbc(connection)
        from sqlalchemy import create_engine, text

        engine = create_engine(
            self.sqlalchemy_url(connection),
            future=True,
            pool_pre_ping=True,
            connect_args={"connect_timeout": int(self.test_timeout)},
        )
        try:
            with engine.connect() as handle:
                statement = (
                    "SELECT VERSION()"
                    if connection.driver is ConnectionDriver.MYSQL
                    else "SELECT version()"
                )
                return str(handle.execute(text(statement)).scalar())
        finally:
            engine.dispose()

    def _probe_jdbc(self, connection: DataConnection) -> str | None:
        import jaydebeapi  # imported here so a missing JVM only breaks this driver

        options = connection.options or {}
        jar = options.get("jdbc_jar_path")
        if not jar:
            raise ValueError("openLooKeng 需要配置 JDBC 驱动 jar 路径")
        driver_class = options.get("jdbc_driver_class") or "io.prestosql.jdbc.PrestoDriver"
        handle = jaydebeapi.connect(
            driver_class,
            self.jdbc_url(connection),
            [connection.username or "", connection.password or ""],
            jar,
        )
        try:
            cursor = handle.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return None
        finally:
            handle.close()

    # ── URLs ──────────────────────────────────────────────────────────────

    @staticmethod
    def sqlalchemy_url(connection: DataConnection) -> str:
        spec = DRIVER_SPECS[connection.driver]
        user = quote_plus(connection.username or "")
        secret = quote_plus(connection.password or "")
        credentials = f"{user}:{secret}@" if user else ""
        return (
            f"{spec['scheme']}://{credentials}{connection.host}:{connection.port}/{connection.database}"
        )

    @staticmethod
    def jdbc_url(connection: DataConnection) -> str:
        options = connection.options or {}
        catalog = options.get("catalog") or "hive"
        schema = options.get("schema") or "default"
        return f"jdbc:lk://{connection.host}:{connection.port}/{catalog}/{schema}"

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _validate(payload: ConnectionInput, spec: dict[str, Any]) -> None:
        if spec.get("requires_database") and not payload.database.strip():
            raise ValueError(f"{spec['label']} 需要填写数据库名")
        for field in spec.get("extra_fields", []):
            if field.get("required") and not str(payload.options.get(field["key"], "")).strip():
                raise ValueError(f"{spec['label']} 需要填写「{field['label']}」")

    @staticmethod
    def _explain(exc: Exception) -> str:
        """Turn a driver stack trace into something a user can act on."""
        text = str(exc)
        if isinstance(exc, ModuleNotFoundError):
            return f"缺少驱动依赖：{exc.name}，请先在后端安装对应的包"
        lowered = text.lower()
        if "access denied" in lowered or "password authentication failed" in lowered:
            return "账号或密码不正确"
        if "unknown database" in lowered or "does not exist" in lowered:
            return "数据库不存在"
        if "can't connect" in lowered or "connection refused" in lowered or "could not connect" in lowered:
            return "无法连接到主机，请检查地址、端口和网络"
        if "timed out" in lowered or "timeout" in lowered:
            return "连接超时，请检查网络或防火墙"
        # Driver errors are long and wrap the original; the first line carries
        # the cause and the rest is noise in a toast.
        first_line = text.strip().splitlines()[0] if text.strip() else exc.__class__.__name__
        return first_line[:300]
