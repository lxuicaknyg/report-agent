"""openLooKeng 的 JDBC 接入。

对照 report/backend/src/common/hetu_jdbc.py —— 那份已在内网验证可连通，所以
这里锁的是「和它一致」，而不是我们自己想当然的形状。
"""

import pytest

from app.connections import hetu
from app.core.connections import DRIVER_SPECS, ConnectionDriver, DataConnection
from app.connections.service import ConnectionService


def conn(**kwargs) -> DataConnection:
    defaults = dict(
        connection_id="conn_1", name="数仓", driver=ConnectionDriver.OPENLOOKENG,
        host="10.200.63.104", port=22443, options={},
    )
    return DataConnection(**{**defaults, **kwargs})


def test_driver_class_is_the_hetu_one():
    # Presto 的类名在 hetu-jdbc 里不存在，填它只会 ClassNotFound。
    assert hetu.DRIVER_CLASS == "io.hetu.core.jdbc.OpenLooKengDriver"


def test_the_form_no_longer_asks_for_jar_path_or_driver_class():
    """jar 是部署产物，类名是固定的 —— 都不该出现在用户表单里。

    尤其 jar：JPype 一个进程只能启一次 JVM，所以「每个连接一个 jar」根本无法
    实现，界面却在让用户填。
    """
    keys = {f["key"] for f in DRIVER_SPECS[ConnectionDriver.OPENLOOKENG]["extra_fields"]}
    assert keys == {"catalog", "schema"}


def test_catalog_only_url_keeps_a_single_path_segment():
    # 内网实测可用的地址就是这种：jdbc:lk://host:port/bhive
    url = ConnectionService.jdbc_url(conn(options={"catalog": "bhive"}))
    assert url == "jdbc:lk://10.200.63.104:22443/bhive"


def test_catalog_and_schema_url():
    url = ConnectionService.jdbc_url(conn(options={"catalog": "hive", "schema": "default"}))
    assert url == "jdbc:lk://10.200.63.104:22443/hive/default"


def test_empty_schema_is_not_backfilled_with_default():
    """补 /default 会把只有 catalog 的地址连到别的地方去。"""
    url = ConnectionService.jdbc_url(conn(options={"catalog": "bhive", "schema": ""}))
    assert url.endswith("/bhive")


def test_missing_jar_directory_is_reported_as_a_deployment_problem(tmp_path):
    with pytest.raises(hetu.JdbcDriverMissing, match="不存在"):
        hetu.resolve_jar(explicit="", directory=tmp_path / "nope")


def test_empty_jar_directory_names_where_to_put_the_jar(tmp_path):
    with pytest.raises(hetu.JdbcDriverMissing, match="deploy/jdbc"):
        hetu.resolve_jar(explicit="", directory=tmp_path)


def test_jar_is_discovered_from_the_mounted_directory(tmp_path):
    """部署只需要把 jar 丢进目录，不必再对齐文件名。"""
    (tmp_path / "hetu-jdbc-1.3.0.jar").write_bytes(b"x")
    assert hetu.resolve_jar(explicit="", directory=tmp_path).name == "hetu-jdbc-1.3.0.jar"


def test_hetu_jar_wins_over_unrelated_jars(tmp_path):
    (tmp_path / "aaa-other.jar").write_bytes(b"x")
    (tmp_path / "hetu-jdbc-1.3.0.jar").write_bytes(b"x")
    assert "hetu" in hetu.resolve_jar(explicit="", directory=tmp_path).name


def test_explicit_env_jar_overrides_the_directory(tmp_path):
    jar = tmp_path / "picked.jar"
    jar.write_bytes(b"x")
    other = tmp_path / "ignored"
    other.mkdir()
    assert hetu.resolve_jar(explicit=str(jar), directory=other) == jar


def test_java_values_become_python_values():
    """JVM 以 convertStrings=False 启动，不转换的话 JSON 序列化会失败。"""
    assert hetu.to_python(None) is None
    assert hetu.to_python(3) == 3
    assert hetu.to_python("已转换") == "已转换"

    class Javaish:
        def __str__(self) -> str:
            return "java.lang.String 的内容"

    assert hetu.to_python(Javaish()) == "java.lang.String 的内容"


class FakeJavaThrowable:
    """近似 JPype 暴露出来的 Java 异常：有 getMessage/getCause。"""

    def __init__(self, message: str, cause: "FakeJavaThrowable | None" = None) -> None:
        self._message = message
        self._cause = cause

    def getMessage(self):  # noqa: N802 - 对齐 Java 命名
        return self._message

    def getCause(self):  # noqa: N802
        return self._cause


def jdbc_error(*chain: str) -> Exception:
    """构造 jaydebeapi 那种形状：DatabaseError(java_exception)。"""
    node = None
    for message in reversed(chain):
        node = FakeJavaThrowable(message, node)
    return Exception(node)


def test_the_wrapper_message_alone_is_not_the_answer():
    """"Error executing query" 什么也没说明，真正原因在 cause 里。

    之前 _explain 只取首行，于是界面上永远只有这一句 —— 排查时既不知道是认证
    失败、SSL 没开，还是 catalog 不存在。
    """
    exc = jdbc_error("Error executing query", "Authentication failed: SSL is required")
    described = hetu.describe(exc)
    assert "Error executing query" in described
    assert "SSL is required" in described


def test_a_deep_cause_chain_is_flattened_outermost_first():
    messages = hetu.unwrap_messages(
        jdbc_error("Error executing query", "connect failed", "Connection refused")
    )
    assert messages[0] == "Error executing query"
    assert "Connection refused" in messages


def test_a_long_message_is_kept_as_is():
    """原因本身够具体时不用再拼包装语。"""
    detail = "Catalog 'nosuch' does not exist, and here is a very long explanation"
    assert hetu.describe(jdbc_error(detail)).startswith("Catalog 'nosuch'")


def test_a_plain_python_exception_still_works():
    assert hetu.describe(ValueError("普通异常")) == "普通异常"


def test_an_exception_with_no_message_falls_back_to_its_type():
    assert hetu.unwrap_messages(RuntimeError()) == ["RuntimeError"]


def test_a_cyclic_cause_chain_does_not_hang():
    a = FakeJavaThrowable("外层")
    b = FakeJavaThrowable("内层", a)
    a._cause = b  # 环
    assert hetu.unwrap_messages(Exception(a))  # 不挂就算过
