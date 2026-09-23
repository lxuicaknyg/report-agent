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
        "sqlglot_dialect": "mysql",
        "note": "使用 PyMySQL 驱动，账号只需具备只读权限。",
    },
    ConnectionDriver.GAUSSDB: {
        # GaussDB speaks the PostgreSQL wire protocol, so psycopg drives it.
        "label": "GaussDB",
        "default_port": 8000,
        "scheme": "postgresql+psycopg",
        "requires_database": True,
        "driver_package": "psycopg[binary]>=3.2.0",
        "sqlglot_dialect": "postgres",
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
        # openLooKeng is Presto-derived, so Presto is the closest dialect.
        "sqlglot_dialect": "presto",
        # 驱动 jar 和驱动类名刻意不在这里：jar 由部署挂载进容器（deploy/jdbc/），
        # 类名是固定的。而且 JPype 一个进程只能启一次 JVM，classpath 随之固定，
        # 所以「每个连接填一个 jar 路径」在实现上就是假的 —— 第一个连接的 jar
        # 会对之后所有连接生效。
        "note": "通过 JDBC 连接。驱动 jar 由部署方挂载，无需在此填写。",
        "extra_fields": [
            {"key": "catalog", "label": "Catalog", "required": True, "placeholder": "hive"},
            {"key": "schema", "label": "Schema", "required": False, "placeholder": "default"},
        ],
    },
}


class DataConnection(BaseModel):
    """A saved database connection.

    ``password`` is stored but never serialised outward — see
    :meth:`redacted`, which is what every API response goes through.
    """

    connection_id: str
    #: Who saved it. A connection carries database credentials, so this is the
    #: field that keeps one analyst's warehouse login out of another's list.
    #: None on rows written before connections were attributed — treated as
    #: nobody's rather than everybody's, see ``api.deps.forbid_unless_owner``.
    owner_id: str | None = None
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


#: What a supplied query is meant to produce. A metric is either one number
#: with the dimensions it holds for, or a detail table the chapter renders as
#: rows. The user picks which; it is not inferred from the row count, because
#: a one-row detail table and a scalar are the same result set.
SupplementShape = Literal["value", "table"]


class ConnectionQueryRequest(BaseModel):
    """A read-only statement the user wants run against a saved connection."""

    query: str
    shape: SupplementShape = "value"

    @field_validator("query")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("SQL 不能为空")
        return value.strip()


class MetricExtraction(BaseModel):
    """What a query result means as an answer to one metric.

    For ``shape="value"`` the convention is positional: the last column carries
    the number, every column before it names a dimension it was measured on.
    It is what lets a supplied value say *2026-06-30 的不良贷款余额* rather than
    just *52501109.06* — the user has to select the filter they applied for it
    to be recorded.

    For ``shape="table"`` no column is special. A detail table's columns are
    all content, and forcing the positional convention onto it would invent a
    distinction the data does not have.
    """

    shape: SupplementShape = "value"
    value: str | None = None
    #: Column name → cell value, for every column left of the last one. Empty
    #: when the query returned a bare scalar, which is allowed but unlabelled.
    #: Never set for a table.
    dimensions: dict[str, str] = Field(default_factory=dict)
    #: The detail rows, for a table. Cells are rendered to text here rather
    #: than left as driver types, so the digits the chapter prints are the
    #: digits the database returned.
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, str]] = Field(default_factory=list)
    #: True when the query had more rows than a supplement may carry, so what
    #: is recorded is the first ``len(rows)`` of a longer result.
    truncated: bool = False
    #: Why this result cannot be used, if it cannot.
    error: str | None = None

    @property
    def usable(self) -> bool:
        if self.error is not None:
            return False
        return bool(self.rows) if self.shape == "table" else self.value is not None


class ConnectionQueryResult(BaseModel):
    """The outcome of running one statement, shaped for a trial run.

    Carries both the rows to show and the reading that would be recorded, so
    the preview in the question card is the same interpretation the supplement
    is later stored with, rather than a second implementation of it.
    """

    success: bool
    message: str = ""
    #: The connection's display name, so a value's provenance can name where it
    #: came from without holding on to an id the reader cannot resolve.
    connection_name: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    #: True when the statement returned more rows than were fetched, so
    #: ``row_count`` is a floor rather than the total.
    truncated: bool = False
    elapsed_ms: int = 0
    extraction: MetricExtraction | None = None


#: The derived analyses that can be generated from a working query. They cover
#: the shapes a report keeps asking for — this period against last year, or
#: against the period before it.
AnalysisType = Literal["yoy", "mom", "ranking"]


class AnalysisSqlRequest(BaseModel):
    """Turn a query that already runs into a derived-analysis query."""

    sql: str
    analysis_type: AnalysisType

    @field_validator("sql")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("SQL 不能为空")
        return value.strip()


class AnalysisSqlResult(BaseModel):
    """A generated query, offered for the user to review and try.

    Never run here: generation and execution stay separate steps so the user
    reads the SQL before anything touches the database with it.
    """

    success: bool
    message: str = ""
    analysis_type: AnalysisType | None = None
    dialect: str = ""
    generated_sql: str | None = None
