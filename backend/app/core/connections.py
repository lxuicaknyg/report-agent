"""Data source connections: the configured databases a report can draw on.

A connection is not a dataset. A dataset is something already queryable — an
uploaded workbook, a registered table. A connection is the credentials and
address of a database a user may later point a query at, which is what the
supplement flow needs when someone answers a missing metric with SQL instead of
a typed-in number.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .models import utc_now


class ConnectionDriver(str, Enum):
    MYSQL = "mysql"
    GAUSSDB = "gaussdb"
    OPENLOOKENG = "openlookeng"


class ConnectionStatus(str, Enum):
    #: Saved but never reached. Nothing has proven the credentials work.
    UNTESTED = "untested"
    OK = "ok"
    FAILED = "failed"


#: What each driver needs, how its URL is spelled, and which dependency carries
#: it. Kept as data so the API can hand the form to the frontend instead of the
#: two sides drifting apart.
DRIVER_SPECS: dict[ConnectionDriver, dict[str, Any]] = {
    ConnectionDriver.MYSQL: {
        "label": "MySQL",
        "default_port": 3306,
        "scheme": "mysql+pymysql",
        "requires_database": True,
        "driver_package": "pymysql>=1.1.1",
        "note": "使用 PyMySQL 驱动，账号只需具备只读权限。",
    },
    ConnectionDriver.GAUSSDB: {
        # GaussDB speaks the PostgreSQL wire protocol, so psycopg drives it.
        "label": "GaussDB",
        "default_port": 8000,
        "scheme": "postgresql+psycopg",
        "requires_database": True,
        "driver_package": "psycopg[binary]>=3.2.0",
        "note": "GaussDB 兼容 PostgreSQL 协议，通过 psycopg 连接。",
    },
    ConnectionDriver.OPENLOOKENG: {
        # openLooKeng has no SQLAlchemy dialect; it is reached over JDBC, which
        # needs a JVM and the vendor jar on disk.
        "label": "openLooKeng",
        "default_port": 8090,
        "scheme": "jdbc:lk",
        "requires_database": False,
        "driver_package": "jaydebeapi>=1.2,<2.0 + jpype1>=1.6,<2.0",
        "note": "通过 JDBC 连接，需要在服务器上提供驱动 jar 并安装 JVM。",
        "extra_fields": [
            {"key": "catalog", "label": "Catalog", "required": True, "placeholder": "hive"},
            {"key": "schema", "label": "Schema", "required": False, "placeholder": "default"},
            {"key": "jdbc_jar_path", "label": "JDBC 驱动 jar 路径", "required": True,
             "placeholder": "/opt/lib/hetu-jdbc-1.9.0.jar"},
            {"key": "jdbc_driver_class", "label": "驱动类名", "required": False,
             "placeholder": "io.prestosql.jdbc.PrestoDriver"},
        ],
    },
}


class DataConnection(BaseModel):
    """A saved database connection.

    ``password`` is stored but never serialised outward — see
    :meth:`redacted`, which is what every API response goes through.
    """

    connection_id: str
    name: str
    driver: ConnectionDriver
    host: str
    port: int = Field(ge=1, le=65535)
    database: str = ""
    username: str = ""
    password: str = ""
    #: Driver-specific settings, e.g. openLooKeng's catalog and jar path.
    options: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    status: ConnectionStatus = ConnectionStatus.UNTESTED
    last_tested_at: Any = None
    last_error: str | None = None
    created_at: Any = Field(default_factory=utc_now)
    updated_at: Any = Field(default_factory=utc_now)

    def redacted(self) -> dict[str, Any]:
        """The shape the API returns: everything except the secret.

        ``has_password`` is kept so an edit form can show that one is stored
        without ever receiving it.
        """
        payload = self.model_dump(mode="json")
        payload.pop("password", None)
        payload["has_password"] = bool(self.password)
        return payload


class ConnectionInput(BaseModel):
    """Create/update payload. Every field except the name has a driver default."""

    name: str
    driver: ConnectionDriver
    host: str
    port: int | None = Field(default=None, ge=1, le=65535)
    database: str = ""
    username: str = ""
    #: Omitted on an edit means "keep the stored one"; empty string means clear.
    password: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None

    @field_validator("name", "host")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("不能为空")
        return value.strip()


class ConnectionTestResult(BaseModel):
    success: bool
    message: str
    elapsed_ms: int = 0
    server_version: str | None = None
