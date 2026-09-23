"""Create, test and manage database connections."""

from __future__ import annotations

import asyncio
import datetime as dt
import decimal
import logging
import re
import time
from typing import Any
from urllib.parse import quote_plus
from uuid import uuid4

from ..core.connections import (
    DRIVER_SPECS,
    AnalysisSqlResult,
    AnalysisType,
    ConnectionDriver,
    ConnectionInput,
    ConnectionQueryResult,
    ConnectionStatus,
    ConnectionTestResult,
    DataConnection,
    MetricExtraction,
    SupplementShape,
)
from ..core.models import utc_now
from . import hetu
from .repository import ConnectionRepository

logger = logging.getLogger(__name__)

#: Statements that may not appear in a user-written query. Only checked inside
#: a CTE: PostgreSQL (and so GaussDB) lets ``WITH t AS (DELETE ... RETURNING *)
#: SELECT * FROM t`` write from what reads as a SELECT, which the leading-token
#: check alone would wave through.
_WRITE_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "truncate",
    "create", "grant", "revoke", "merge", "replace", "call",
)


class ConnectionService:
    def __init__(
        self,
        repository: ConnectionRepository,
        test_timeout: float = 10.0,
        query_timeout: float = 30.0,
        max_rows: int = 200,
        max_supplement_rows: int = 100,
        analysis_tool: Any = None,
    ) -> None:
        self.repository = repository
        self.test_timeout = test_timeout
        self.query_timeout = query_timeout
        #: Cap on rows pulled back from a user query. A supplement needs one
        #: row; the rest are fetched only so a wrong query can be shown to be
        #: wrong instead of silently yielding its first row.
        self.max_rows = max_rows
        #: Cap on rows a detail-table supplement may carry into the chapter
        #: prompt. Beyond this the rows stop earning their tokens, so they are
        #: cut and the cut is reported rather than hidden.
        self.max_supplement_rows = max_supplement_rows
        #: Generates year-on-year / period-on-period SQL from a working query.
        #: Optional: without it the supplement flow still works, it just cannot
        #: offer the derived analyses.
        self.analysis_tool = analysis_tool

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

    async def list(self, owner_id: str | None = None) -> list[DataConnection]:
        """Saved connections, filtered to one owner when given.

        The default stays unfiltered for the report flow, which resolves a
        connection on behalf of a session that was already authorised.
        """
        items = await self.repository.list()
        if owner_id is not None:
            items = [item for item in items if item.owner_id == owner_id]
        return sorted(items, key=lambda item: item.created_at or "", reverse=True)

    async def get(self, connection_id: str) -> DataConnection:
        return await self.repository.get(connection_id)

    async def create(self, payload: ConnectionInput, *, owner_id: str | None = None) -> DataConnection:
        spec = DRIVER_SPECS[payload.driver]
        self._validate(payload, spec)
        connection = DataConnection(
            connection_id=f"conn_{uuid4().hex[:12]}",
            owner_id=owner_id,
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
        handle = hetu.connect(
            connection.host,
            connection.port,
            self._jdbc_path(connection),
            connection.username or "",
            connection.password or "",
        )
        try:
            cursor = handle.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return None
        finally:
            handle.close()

    # ── ad-hoc queries ────────────────────────────────────────────────────

    async def query(
        self,
        connection_id: str,
        sql: str,
        shape: SupplementShape = "value",
    ) -> ConnectionQueryResult:
        """Run one read-only statement and read a metric value out of it.

        Never raises on a rejected or failed statement: a user writing SQL in a
        question card needs the reason shown beside their query, the same way a
        refused login is shown beside the connection form.
        """
        connection = await self.repository.get(connection_id)
        started = time.monotonic()
        try:
            statement = self._assert_read_only(sql)
            columns, rows, truncated = await asyncio.wait_for(
                asyncio.to_thread(self._run, connection, statement),
                timeout=self.query_timeout,
            )
        except asyncio.TimeoutError:
            return ConnectionQueryResult(
                success=False,
                connection_name=connection.name,
                message=f"查询超时（>{self.query_timeout:.0f}s），请缩小取数范围",
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
        except ValueError as exc:
            return ConnectionQueryResult(
                success=False,
                connection_name=connection.name,
                message=str(exc),
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:
            logger.warning("connection_query_failed connection_id=%s error=%s", connection_id, exc)
            return ConnectionQueryResult(
                success=False,
                connection_name=connection.name,
                message=self._explain(exc),
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
        extraction = self.extract(columns, rows, truncated, shape, self.max_supplement_rows)
        logger.info(
            "connection_query connection_id=%s shape=%s rows=%d usable=%s sql=%s",
            connection_id, shape, len(rows), extraction.usable, sql[:200],
        )
        return ConnectionQueryResult(
            success=True,
            connection_name=connection.name,
            message="取数成功" if extraction.usable else (extraction.error or ""),
            columns=columns,
            rows=[
                {column: self._jsonable(value) for column, value in row.items()}
                for row in rows
            ],
            row_count=len(rows),
            truncated=truncated,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            extraction=extraction,
        )

    @staticmethod
    def extract(
        columns: list[str],
        rows: list[dict[str, Any]],
        truncated: bool = False,
        shape: SupplementShape = "value",
        max_rows: int = 100,
    ) -> MetricExtraction:
        """Read an answer to one metric out of a result set.

        ``shape="value"`` takes the last column as the number and the ones
        before it as the dimensions it holds for, and refuses anything but a
        single row: picking the first of several would quietly answer a
        different question than the one that was asked.

        ``shape="table"`` keeps every column and row as content. Rows past
        ``max_rows`` are dropped and the cut is flagged — a chapter prompt
        carrying a thousand rows stops paying for itself long before that.
        """
        if not columns:
            return MetricExtraction(shape=shape, error="查询没有返回任何列")
        if not rows:
            return MetricExtraction(shape=shape, error="查询没有返回任何行，请检查过滤条件")

        if shape == "table":
            kept = rows[:max_rows]
            return MetricExtraction(
                shape="table",
                columns=list(columns),
                rows=[
                    {column: ConnectionService._render(row.get(column)) for column in columns}
                    for row in kept
                ],
                truncated=truncated or len(rows) > max_rows,
            )

        if truncated or len(rows) > 1:
            count = f"{len(rows)}+" if truncated else str(len(rows))
            return MetricExtraction(
                error=(
                    f"查询返回 {count} 行，而这一项要的是一个数值。请补充过滤条件或用聚合函数"
                    f"收敛到一行；如果这一项本来就该是一份明细清单，用下面的"
                    f"「按明细清单补充」把它整张表记进报告"
                )
            )
        row = rows[0]
        raw = row.get(columns[-1])
        if raw is None:
            return MetricExtraction(error=f"取数结果为空值（列「{columns[-1]}」为 NULL）")
        dimensions = {
            column: ConnectionService._render(row.get(column))
            for column in columns[:-1]
            if row.get(column) is not None
        }
        return MetricExtraction(value=ConnectionService._render(raw), dimensions=dimensions)

    def _run(self, connection: DataConnection, sql: str) -> tuple[list[str], list[dict[str, Any]], bool]:
        """Blocking query, run on a worker thread.

        Cells keep the types the driver produced — a ``Decimal`` balance must
        still be a ``Decimal`` when the value is read out of it. One row over
        the cap is fetched so a too-broad query reports as truncated instead of
        silently losing rows.
        """
        if connection.driver is ConnectionDriver.OPENLOOKENG:
            columns, records = self._run_jdbc(connection, sql)
        else:
            columns, records = self._run_sqlalchemy(connection, sql)
        truncated = len(records) > self.max_rows
        rows = [
            dict(zip(columns, record))
            for record in records[: self.max_rows]
        ]
        return columns, rows, truncated

    def _run_sqlalchemy(
        self, connection: DataConnection, sql: str
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        from sqlalchemy import create_engine, text

        engine = create_engine(
            self.sqlalchemy_url(connection),
            future=True,
            pool_pre_ping=True,
            connect_args={"connect_timeout": int(self.query_timeout)},
        )
        try:
            with engine.connect() as handle:
                cursor = handle.execute(text(sql))
                columns = [str(name) for name in cursor.keys()]
                records = [tuple(record) for record in cursor.fetchmany(self.max_rows + 1)]
            return columns, records
        finally:
            engine.dispose()

    def _run_jdbc(
        self, connection: DataConnection, sql: str
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        handle = hetu.connect(
            connection.host,
            connection.port,
            self._jdbc_path(connection),
            connection.username or "",
            connection.password or "",
        )
        try:
            cursor = handle.cursor()
            cursor.execute(sql)
            # JVM 以 convertStrings=False 启动，列名和取值回来都是 Java 对象，
            # 不转换的话后面 JSON 序列化会炸。
            columns = [str(item[0]) for item in (cursor.description or [])]
            records = [
                tuple(hetu.to_python(value) for value in record)
                for record in cursor.fetchmany(self.max_rows + 1)
            ]
            return columns, records
        finally:
            handle.close()

    @staticmethod
    def _skeleton(sql: str) -> str:
        """The statement with comments removed and string literals blanked.

        Checks run on this; the database still receives the original. Comments
        matter because generated analysis SQL is commented by design, and
        reading its first token literally rejected every such query as "not a
        SELECT". Literals matter because a semicolon inside one is not a second
        statement.
        """
        out: list[str] = []
        quote: str | None = None
        index, length = 0, len(sql)
        while index < length:
            char = sql[index]
            if quote:
                if char == "\\" and quote != "`":
                    index += 2  # escaped character inside a literal
                    continue
                if char == quote:
                    quote = None
                    out.append(char)
                index += 1
                continue
            if char in "'\"`":
                quote = char
                out.append(char)
                index += 1
                continue
            if sql.startswith("--", index) or sql.startswith("#", index):
                end = sql.find("\n", index)
                index = length if end == -1 else end
                out.append(" ")
                continue
            if sql.startswith("/*", index):
                end = sql.find("*/", index + 2)
                index = length if end == -1 else end + 2
                out.append(" ")
                continue
            out.append(char)
            index += 1
        return "".join(out).strip()

    @staticmethod
    def _assert_read_only(sql: str) -> str:
        """Reject anything that is not a single reading statement.

        This is a guard rail, not the boundary: the account a connection uses
        should be read-only, which is what actually makes a mistake here
        harmless. It catches the two shapes a typed-in query goes wrong in —
        a second statement smuggled in after a semicolon, and a CTE that
        writes.
        """
        statement = sql.strip().rstrip(";").strip()
        if not statement:
            raise ValueError("SQL 不能为空")
        bare = ConnectionService._skeleton(statement).rstrip(";").strip()
        if not bare:
            raise ValueError("SQL 不能为空")
        if ";" in bare:
            raise ValueError("一次只能执行一条语句，请去掉多余的分号")
        leading = bare.split(None, 1)[0].lower()
        if leading not in {"select", "with"}:
            raise ValueError("只允许执行 SELECT / WITH 查询")
        if leading == "with":
            for keyword in _WRITE_KEYWORDS:
                if re.search(rf"\b{keyword}\b", bare, re.IGNORECASE):
                    raise ValueError(f"WITH 子句中不允许出现 {keyword.upper()}")
        return statement

    @staticmethod
    def _render(value: Any) -> str:
        """A cell as the report should print it.

        Decimals keep the scale the database returned them with: a balance
        stored as 2049900.25 must not reach the chapter as 2049900.2500000002
        because it passed through a float on the way.
        """
        if isinstance(value, bool):
            return "是" if value else "否"
        if isinstance(value, decimal.Decimal):
            return format(value, "f")
        if isinstance(value, (dt.datetime, dt.date, dt.time)):
            return value.isoformat()
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        return str(value)

    @staticmethod
    def _jsonable(value: Any) -> Any:
        """Cells as the preview table sends them.

        Decimals become their exact text rather than a float: the preview has
        to show the same digits the supplement would be recorded with, and a
        balance routed through a float stops being able to promise that.
        """
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        return ConnectionService._render(value)

    # ── derived analyses ──────────────────────────────────────────────────

    async def analysis_sql(
        self,
        connection_id: str,
        sql: str,
        analysis_type: AnalysisType,
    ) -> AnalysisSqlResult:
        """Rewrite a working query into a year-on-year / period-on-period one.

        The result is returned, not executed: the user reads the generated SQL
        and runs it themselves, so a wrong rewrite is something they see rather
        than something that silently lands in the report.

        The dialect comes from the connection, so the SQL is written in the
        syntax of the database it will be run against.
        """
        connection = await self.repository.get(connection_id)
        dialect = DRIVER_SPECS[connection.driver].get("sqlglot_dialect", "postgres")
        if self.analysis_tool is None:
            return AnalysisSqlResult(
                success=False, message="当前部署未启用 SQL 分析生成", dialect=dialect
            )
        # Reject what the query endpoint would reject, before spending a model
        # call on it: a statement that cannot be run is not worth rewriting.
        try:
            statement = self._assert_read_only(sql)
        except ValueError as exc:
            return AnalysisSqlResult(success=False, message=str(exc), dialect=dialect)

        from ..core.models import RequestContext
        from ..core.tooling import ToolContext

        started = time.monotonic()
        result = await self.analysis_tool.execute(
            ToolContext(request=RequestContext()),
            {"sql": statement, "analysis_type": analysis_type, "dialect": dialect},
        )
        elapsed = int((time.monotonic() - started) * 1000)
        generated = (result.data or {}).get("generated_sql") if result.success else None
        logger.info(
            "analysis_sql connection_id=%s type=%s dialect=%s success=%s elapsed_ms=%d",
            connection_id, analysis_type, dialect, bool(generated), elapsed,
        )
        if not generated:
            return AnalysisSqlResult(
                success=False,
                message=result.result_for_llm or "生成失败，请稍后重试",
                analysis_type=analysis_type,
                dialect=dialect,
            )
        return AnalysisSqlResult(
            success=True,
            message="已生成，请先试跑确认结果",
            analysis_type=analysis_type,
            dialect=dialect,
            generated_sql=generated,
        )

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
    def _jdbc_path(connection: DataConnection) -> str:
        """JDBC 地址里 host:port 之后的那一段。

        schema 留空就只给 catalog，不补 ``/default`` —— 内网实测可用的地址里
        就有只带 catalog 的（``jdbc:lk://host:port/bhive``），补上反而连错库。
        """
        options = connection.options or {}
        catalog = str(options.get("catalog") or "").strip().strip("/")
        schema = str(options.get("schema") or "").strip().strip("/")
        return f"{catalog}/{schema}" if catalog and schema else catalog

    @staticmethod
    def jdbc_url(connection: DataConnection) -> str:
        """完整 JDBC 地址。留作展示与排查用。"""
        return hetu.build_url(
            connection.host, connection.port, ConnectionService._jdbc_path(connection)
        )

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _validate(payload: ConnectionInput, spec: dict[str, Any]) -> None:
        if spec.get("requires_database") and not payload.database.strip():
            raise ValueError(f"{spec['label']} 需要填写数据库名")
        for field in spec.get("extra_fields", []):
            if field.get("required") and not str(payload.options.get(field["key"], "")).strip():
                raise ValueError(f"{spec['label']} 需要填写「{field['label']}」")

    @staticmethod
    def _first_quoted(text: str) -> str | None:
        """The object name a driver error quotes, e.g. ``db.orders``.

        Single quotes and backticks are tried before double quotes because
        MySQL wraps its whole message in double quotes — reading those first
        returns the word "Table" instead of the table.
        """
        for pattern in (r"'([^']+)'", r"`([^`]+)`", r'"([^"]+)"'):
            for candidate in re.findall(pattern, text):
                name = candidate.strip()
                if name and " " not in name:
                    return name
        return None

    @staticmethod
    def _explain(exc: Exception) -> str:
        """Turn a driver stack trace into something a user can act on."""
        text = str(exc)
        if isinstance(exc, ModuleNotFoundError):
            return f"缺少驱动依赖：{exc.name}，请先在后端安装对应的包"
        # 驱动 jar 没挂载是部署没配好，不是数据库连不上。分开说，否则用户会去
        # 查网络和账号，而要改的是容器的挂载。
        if isinstance(exc, hetu.JdbcDriverMissing):
            return text
        # 关键字要在整条 cause 链上找，不能只看最外层那句包装语 —— 否则
        # "Error executing query" 会让下面每个分支都匹配不上。
        lowered = " ".join(hetu.unwrap_messages(exc)).lower()
        # JDK 17 的模块系统挡住 hetu-jdbc 的反射时报这个。属于镜像问题，不是
        # 用户填错了什么。
        if "inaccessibleobject" in lowered or "add-opens" in lowered:
            return "JDBC 驱动被 JVM 模块系统拒绝，请联系维护者检查后端镜像"
        if "classnotfound" in lowered or "no suitable driver" in lowered:
            return "JDBC 驱动加载失败，请确认 deploy/jdbc/ 下的 jar 是 hetu-jdbc 驱动"
        if "authentication requires ssl" in lowered:
            return "服务端要求 SSL，请让维护者把 HETU_JDBC_SSL 设为 true"
        if "access denied" in lowered or "password authentication failed" in lowered:
            return "账号或密码不正确"
        if "unknown database" in lowered or "does not exist" in lowered:
            return "数据库不存在"
        if "can't connect" in lowered or "connection refused" in lowered or "could not connect" in lowered:
            return "无法连接到主机，请检查地址、端口和网络"
        if "timed out" in lowered or "timeout" in lowered:
            return "连接超时，请检查网络或防火墙"
        # Query-time mistakes. The driver wraps them in a stack of its own, and
        # a user editing SQL needs the one line that says what to change.
        if "doesn't exist" in lowered or "undefined table" in lowered:
            return f"表不存在：{ConnectionService._first_quoted(text) or '请检查表名和库名'}"
        if "unknown column" in lowered or "undefined column" in lowered:
            return f"字段不存在：{ConnectionService._first_quoted(text) or '请检查字段名'}"
        if "syntax error" in lowered or "you have an error in your sql syntax" in lowered:
            return "SQL 语法有误，请检查后重试"
        if "command denied" in lowered or "permission denied" in lowered:
            return "当前账号没有访问该表的权限"
        # JDBC 驱动把真实原因包在 cause 链里，最外层只有一句 "Error executing
        # query" —— 单看它无法判断是认证失败、SSL 没开，还是 catalog 不存在。
        # 所以这里摊平 cause 链，而不是取首行。
        detailed = hetu.describe(exc)
        if detailed and detailed.lower() != text.strip().lower():
            return detailed
        # Driver errors are long and wrap the original; the first line carries
        # the cause and the rest is noise in a toast.
        first_line = text.strip().splitlines()[0] if text.strip() else exc.__class__.__name__
        return first_line[:300]
