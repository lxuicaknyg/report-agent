"""openLooKeng 的 JDBC 连接层（JPype 内嵌 JVM + jaydebeapi + hetu-jdbc）。

复刻 ``report/backend/src/common/hetu_jdbc.py`` —— 那份实现已在内网环境验证可
连通，所以驱动类名、JVM 参数、连接属性都一字不改地照搬，而不是照着文档猜。

三件事是这个模块存在的理由，之前都做错了：

1. **驱动类名是 ``io.hetu.core.jdbc.OpenLooKengDriver``**，不是 Presto 那个。
   openLooKeng 从 Presto 分叉后换了包名，填 Presto 的类名会 ClassNotFound。

2. **JDK 17 需要 ``--add-opens``**。hetu-jdbc 反射访问 java.base 内部，模块系统
   默认拒绝，表现为连接时抛 InaccessibleObjectException。

3. **JVM 是进程级单例**。JPype 一个进程只能启动一次 JVM，classpath 随之固定 ——
   所以 jar 路径必须是部署配置，不能是「每个连接填一个」。后者看着能用，实际
   上第一个连接的 jar 会对之后所有连接生效，而界面还在让用户填。
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from ..config import settings

logger = logging.getLogger(__name__)

#: hetu-jdbc 里的驱动类。写死而不做成选项：填错只会 ClassNotFound，让用户猜这个
#: 字符串没有任何意义。
DRIVER_CLASS = "io.hetu.core.jdbc.OpenLooKengDriver"

_jvm_lock = threading.Lock()
_jvm_started = False


class JdbcDriverMissing(RuntimeError):
    """没有可用的驱动 jar，或缺 jpype/jaydebeapi。

    单独一类，好让上层把它说成部署没配好，而不是「数据库连不上」—— 那会让人
    去查网络和账号，而问题在于容器没挂载 jar。
    """


def resolve_jar(explicit: str | None = None, directory: Path | None = None) -> Path:
    """找出要挂到 classpath 上的 jar。

    优先 ``HETU_JDBC_JAR``；否则在挂载目录里找。自动查找是为了让部署只需要
    「把 jar 放进 deploy/jdbc/」，不必再去对齐一个文件名。

    两个参数默认取配置，显式传入是给测试用的 —— Settings 是 frozen dataclass，
    改不了属性，所以取值放在调用处而不是函数体里。
    """
    explicit = explicit if explicit is not None else settings.hetu_jdbc_jar
    directory = directory if directory is not None else settings.jdbc_jar_dir
    if explicit:
        jar = Path(explicit)
        if not jar.is_file():
            raise JdbcDriverMissing(f"HETU_JDBC_JAR 指向的文件不存在：{jar}")
        return jar

    if not directory.is_dir():
        raise JdbcDriverMissing(
            f"JDBC 驱动目录不存在：{directory}。"
            "请把 hetu-jdbc 的 jar 放进 deploy/jdbc/，容器会挂载到这里。"
        )
    jars = sorted(directory.glob("*.jar"))
    if not jars:
        raise JdbcDriverMissing(
            f"{directory} 下没有 jar 文件。请把 hetu-jdbc 的 jar 放进 deploy/jdbc/。"
        )
    # 目录里可能还有别的 jar，hetu 的优先。
    preferred = [item for item in jars if "hetu" in item.name.lower()]
    chosen = (preferred or jars)[0]
    if len(preferred or jars) > 1:
        logger.warning(
            "jdbc_jar_ambiguous dir=%s candidates=%s chosen=%s",
            directory, [item.name for item in jars], chosen.name,
        )
    return chosen


def _start_jvm() -> None:
    """启动内嵌 JVM，只启一次。参数与内网验证过的那套一致。"""
    global _jvm_started
    if _jvm_started:
        return
    try:
        import jpype
    except ImportError as exc:  # pragma: no cover - 依赖缺失时才会走到
        raise JdbcDriverMissing(
            "缺少 jpype1 / jaydebeapi，无法通过 JDBC 连接 openLooKeng"
        ) from exc

    with _jvm_lock:
        if _jvm_started:
            return
        if not jpype.isJVMStarted():
            jar = resolve_jar()
            jpype.startJVM(
                f"-Djava.class.path={jar}",
                # 够用就好：这个 JVM 只跑一个 JDBC 驱动，不是计算节点。
                "-Xmx256m",
                "-Xms64m",
                # JDK 17 的模块系统默认挡住 hetu-jdbc 的反射访问。
                "--add-opens=java.base/java.util=ALL-UNNAMED",
                "--add-opens=java.base/java.lang=ALL-UNNAMED",
                "--add-opens=java.base/java.lang.reflect=ALL-UNNAMED",
                "--add-opens=java.base/java.io=ALL-UNNAMED",
                "--add-opens=java.base/java.sql=ALL-UNNAMED",
                convertStrings=False,
            )
            logger.info("jvm_started jar=%s", jar)
        _jvm_started = True


def build_url(host: str, port: Any, path: str) -> str:
    """拼 ``jdbc:lk://HOST:PORT/PATH``。

    ``path`` 原样取用户填的值，可以是单段 catalog（``bhive``）也可以是
    ``catalog/schema``（``hive/default``）。**不擅自补 schema** —— 内网实测的
    地址就有只带 catalog 的，补上 ``/default`` 会连错。
    """
    cleaned = str(path or "").strip().strip("/")
    return f"jdbc:lk://{host}:{port}/{cleaned}" if cleaned else f"jdbc:lk://{host}:{port}"


def connect(host: str, port: Any, path: str, user: str, password: str) -> Any:
    """建一条连接，调用方负责 close。"""
    _start_jvm()
    import jaydebeapi

    # 属性用 dict 而不是 [user, password] 列表：SSL 这一项只能这么传，而服务端
    # 开了鉴权时不给它就会被拒。
    props = {
        "user": user or "",
        "password": password or "",
        "SSL": str(settings.hetu_jdbc_ssl).strip().lower() or "false",
    }
    return jaydebeapi.connect(DRIVER_CLASS, build_url(host, port, path), props, str(resolve_jar()))


def to_python(value: Any) -> Any:
    """把 JDBC 返回的值转成 Python 原生类型。

    JVM 以 ``convertStrings=False`` 启动，于是字符串回来是 ``java.lang.String``，
    直接塞进 JSON 响应会序列化失败。
    """
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def unwrap_messages(exc: BaseException, limit: int = 6) -> list[str]:
    """把 JDBC 异常的 cause 链摊平成消息列表，最外层在前。

    hetu/presto 的驱动把真正的失败包在 ``SQLException("Error executing query",
    cause)`` 里，而 ``str(exc)`` 只给得到最外面那句话 —— 对排查毫无用处，
    「Error executing query」既不说是认证失败、SSL 没开，还是 catalog 不存在。

    jaydebeapi 重新抛出时把 Java 异常对象放进 ``args``，那个对象带
    ``getCause()`` / ``getMessage()``，所以链是能走的。写得防御一点：没有
    JPype 的环境（比如单元测试）里也不能炸。
    """
    messages: list[str] = []
    seen: set[int] = set()

    def push(text: object) -> None:
        line = str(text or "").strip()
        # ``Exception(java_throwable)`` 的 str 是那个对象的 repr，形如
        # "<jpype._jexception... object at 0x...>" —— 是噪音，不是消息。
        if line.startswith("<") and " object at 0x" in line:
            return
        if line and line not in messages:
            messages.append(line)

    def walk(node: object, depth: int) -> None:
        if node is None or depth > limit or id(node) in seen:
            return
        seen.add(id(node))

        getter = getattr(node, "getMessage", None)
        if callable(getter):
            try:
                push(getter())
            except Exception:  # pragma: no cover - JPype 边界
                pass
        elif isinstance(node, BaseException):
            # jaydebeapi 把 Java 异常塞进 args 再重抛，这时外层 Python 异常
            # 自己没有消息 —— 取它的 str 只会得到对象 repr，所以让给内层。
            wraps_java = any(
                callable(getattr(arg, "getMessage", None))
                for arg in (getattr(node, "args", ()) or ())
            )
            if not wraps_java:
                push(node)

        # Java 侧的 cause
        cause_getter = getattr(node, "getCause", None)
        if callable(cause_getter):
            try:
                walk(cause_getter(), depth + 1)
            except Exception:  # pragma: no cover - JPype 边界
                pass
        # Python 侧的 cause，以及 jaydebeapi 塞进 args 的 Java 异常
        for candidate in (
            getattr(node, "__cause__", None),
            getattr(node, "__context__", None),
            *(getattr(node, "args", ()) or ()),
        ):
            if candidate is not None and not isinstance(candidate, (str, bytes, int, float)):
                walk(candidate, depth + 1)

    walk(exc, 0)
    if not messages:
        messages.append(exc.__class__.__name__)
    return messages


def describe(exc: BaseException) -> str:
    """一行可读的失败原因。

    外层那句包装语（"Error executing query"）单独出现时什么也没说明，所以
    链上有更具体的消息时就把它拼在后面。
    """
    messages = unwrap_messages(exc)
    head, *rest = messages
    if len(head) < 40 and rest:
        # 短包装语 + 真实原因，例如
        # "Error executing query：Authentication failed: Basic authentication..."
        return f"{head}：{rest[0]}"[:400]
    return head[:400]
