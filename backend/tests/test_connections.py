"""Data source connections: what gets stored, what gets returned, what breaks."""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from app.connections.repository import PersistentConnectionRepository
from app.connections.service import ConnectionService
from app.core.connections import (
    ConnectionDriver,
    ConnectionInput,
    ConnectionStatus,
    DataConnection,
)


def build_service() -> ConnectionService:
    path = Path(tempfile.mkdtemp()) / "connections.json"
    return ConnectionService(PersistentConnectionRepository(path))


def mysql_input(**overrides) -> ConnectionInput:
    payload = {
        "name": "风控库",
        "driver": ConnectionDriver.MYSQL,
        "host": "10.0.0.9",
        "database": "risk",
        "username": "reader",
        "password": "s3cret",
    }
    payload.update(overrides)
    return ConnectionInput(**payload)


def test_a_saved_connection_never_returns_its_password():
    """The list and detail responses are the only thing the browser sees, and a
    credential that reaches the browser has left the server for good."""

    async def run():
        service = build_service()
        created = await service.create(mysql_input())
        payload = created.redacted()
        assert "password" not in payload
        # The form still needs to know one is stored, without receiving it.
        assert payload["has_password"] is True
        assert payload["username"] == "reader"
        assert json.dumps(payload, ensure_ascii=False).find("s3cret") == -1

    asyncio.run(run())


def test_each_driver_supplies_its_own_default_port():
    async def run():
        service = build_service()
        ports = {}
        for driver, host in (
            (ConnectionDriver.MYSQL, "mysql.internal"),
            (ConnectionDriver.GAUSSDB, "gauss.internal"),
            (ConnectionDriver.OPENLOOKENG, "lk.internal"),
        ):
            options = (
                {"catalog": "hive", "jdbc_jar_path": "/opt/lib/hetu-jdbc.jar"}
                if driver is ConnectionDriver.OPENLOOKENG
                else {}
            )
            created = await service.create(
                mysql_input(driver=driver, host=host, database="db", options=options, port=None)
            )
            ports[driver] = created.port
        assert ports[ConnectionDriver.MYSQL] == 3306
        assert ports[ConnectionDriver.GAUSSDB] == 8000
        assert ports[ConnectionDriver.OPENLOOKENG] == 8090

    asyncio.run(run())


def test_urls_escape_credentials():
    """A password with @ or / in it silently rewrote the host half of the URL."""
    connection = DataConnection(
        connection_id="conn_1", name="n", driver=ConnectionDriver.MYSQL,
        host="db.internal", port=3306, database="risk",
        username="read@er", password="p@ss/word",
    )
    url = ConnectionService.sqlalchemy_url(connection)
    assert url == "mysql+pymysql://read%40er:p%40ss%2Fword@db.internal:3306/risk"

    gauss = connection.model_copy(update={"driver": ConnectionDriver.GAUSSDB, "port": 8000})
    assert ConnectionService.sqlalchemy_url(gauss).startswith("postgresql+psycopg://")


def test_openlookeng_needs_its_jdbc_jar():
    async def run():
        service = build_service()
        with pytest.raises(ValueError, match="jar"):
            await service.create(
                mysql_input(driver=ConnectionDriver.OPENLOOKENG, options={"catalog": "hive"})
            )

    asyncio.run(run())


def test_editing_without_resending_the_password_keeps_it():
    """The edit form is rendered without the secret, so a save that omits it
    means "unchanged" — treating it as "clear" locked the user out."""

    async def run():
        service = build_service()
        created = await service.create(mysql_input())
        updated = await service.update(
            created.connection_id, mysql_input(name="风控库（只读）", password=None)
        )
        stored = await service.repository.get(updated.connection_id)
        assert stored.password == "s3cret"
        assert stored.name == "风控库（只读）"

    asyncio.run(run())


def test_moving_a_connection_invalidates_its_last_verdict():
    async def run():
        service = build_service()
        created = await service.create(mysql_input())
        created.status = ConnectionStatus.OK
        await service.repository.save(created)

        updated = await service.update(created.connection_id, mysql_input(host="10.0.0.10"))
        # It was proven against a different server; that proof does not carry.
        assert updated.status is ConnectionStatus.UNTESTED

    asyncio.run(run())


def test_a_failed_test_is_recorded_not_raised():
    """An unreachable host is a result the form shows, not a 500."""

    async def run():
        service = build_service()
        service.test_timeout = 2.0
        created = await service.create(
            mysql_input(host="127.0.0.1", port=1, database="risk")
        )
        result = await service.test(created.connection_id)
        assert result.success is False
        assert result.message
        stored = await service.repository.get(created.connection_id)
        assert stored.status is ConnectionStatus.FAILED
        assert stored.last_tested_at is not None

    asyncio.run(run())


def test_driver_catalogue_is_served_for_the_form():
    drivers = {item["driver"]: item for item in ConnectionService.drivers()}
    assert set(drivers) == {"mysql", "gaussdb", "openlookeng"}
    assert drivers["gaussdb"]["driver_package"].startswith("psycopg")
    assert drivers["mysql"]["driver_package"].startswith("pymysql")
    # openLooKeng's extra fields drive the generated form.
    keys = {field["key"] for field in drivers["openlookeng"]["extra_fields"]}
    assert {"catalog", "jdbc_jar_path"} <= keys


def test_connections_survive_a_restart():
    async def run():
        path = Path(tempfile.mkdtemp()) / "connections.json"
        service = ConnectionService(PersistentConnectionRepository(path))
        created = await service.create(mysql_input())

        reopened = ConnectionService(PersistentConnectionRepository(path))
        restored = await reopened.get(created.connection_id)
        assert restored.name == "风控库"
        assert restored.password == "s3cret"
        # The credential file is not world-readable.
        assert path.stat().st_mode & 0o077 == 0

    asyncio.run(run())
