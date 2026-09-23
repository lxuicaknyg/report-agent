from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_backend_dir = Path(__file__).resolve().parents[1]
load_dotenv(_backend_dir / ".env")


def _dir_from(name: str, fallback: Path, *, in_tree: set[str] = frozenset()) -> Path:
    """Resolve a directory setting, ignoring values that point into the repo.

    ``./data`` and friends live in the project tree, which ``uvicorn --reload``
    watches: writing there restarts the process mid-run. Older .env files still
    carry those values, so they are treated as unset rather than obeyed.
    """
    configured = os.getenv(name)
    if not configured or configured in in_tree:
        return fallback
    return Path(configured)


#: Everything this service must not lose: uploaded files, generated reports,
#: report and conversation state, saved connections. One root so a container
#: needs exactly one volume, and so clearing state cannot leave half of it
#: behind — a session that outlives its artifacts still offers a download that
#: 404s.
STATE_DIR = _dir_from(
    "STATE_DIR",
    Path(tempfile.gettempdir()) / "report-agent",
    in_tree={"./var", "var", "./state", "state"},
)

_data_dir = _dir_from("DATA_DIR", STATE_DIR / "datasets", in_tree={"./data", "data"})
_artifact_dir = _dir_from(
    "ARTIFACT_DIR", STATE_DIR / "artifacts", in_tree={"./artifacts", "artifacts"}
)
_log_dir = _dir_from("LOG_DIR", STATE_DIR / "logs", in_tree={"./logs", "logs"})


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Report Agent Backend")
    environment: str = os.getenv("ENVIRONMENT", "development")
    # Namespaced by service, not just versioned: the workspace is fronted by one
    # nginx that routes /api/<service>/v1/* to whichever container owns it, and
    # other teams mount their own tools alongside this one. A bare /api/v1 gives
    # it nothing to split on.
    api_prefix: str = os.getenv("API_PREFIX", "/api/report/v1")
    # 上传的 Excel 不要默认写入项目目录：开发环境通常使用 uvicorn --reload，
    # 写入 ./data 会触发进程重载，导致当前的内存报告 session 被清空并在轮询时返回 404。
    data_dir: Path = _data_dir
    artifact_dir: Path = _artifact_dir
    #: JSON stores for state that used to be hardcoded into the temp directory,
    #: where a container restart wiped every report, conversation and saved
    #: connection.
    session_store: Path = STATE_DIR / "sessions.json"
    conversation_store: Path = STATE_DIR / "conversations.json"
    connection_store: Path = STATE_DIR / "connections.json"
    #: Uploaded templates: the parsed models in one file, the original bytes in
    #: the directory beside it. A session only stores a template_id, so losing
    #: these makes every stored report unresumable.
    template_store: Path = STATE_DIR / "templates.json"
    template_content_dir: Path = STATE_DIR / "templates"
    log_dir: Path = _log_dir
    # DEBUG additionally dumps each metric's full research conversation, which
    # is the only way to see what the model was actually shown when a number
    # comes back wrong.
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    #: Loopback by default so a dev machine does not publish the API to its
    #: network. A container has to bind every interface to be reachable at all,
    #: so the image sets HOST=0.0.0.0.
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    database_url: str | None = os.getenv("DATABASE_URL") or None
    # 登录校验读的库（AI_DA_DB.users）。与用户自建的数据连接无关，那些是报告取数用的。
    # 刻意不给兜底值：漏配时应当明确报错，而不是静默连到某台机器的 localhost。
    auth_database_url: str = os.getenv("AUTH_DATABASE_URL") or ""
    # 签发 token 的密钥。没配就每次启动随机生成：重启后旧 token 失效，
    # 但绝不会把一个写死的默认密钥带到正式环境去。
    auth_secret: str = os.getenv("AUTH_SECRET") or ""
    auth_token_ttl_seconds: int = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", str(12 * 60 * 60)))
    # openLooKeng 走 JDBC，需要厂商的 hetu-jdbc jar。jar 是部署产物而不是用户
    # 输入：容器把宿主机目录挂到这里，服务自己找。JPype 一个进程只能启动一次
    # JVM，classpath 随之固定，所以这必须是进程级配置 —— 做成「每个连接填一个
    # 路径」是错的，第一个连接用的 jar 会对后面所有连接生效。
    jdbc_jar_dir: Path = Path(os.getenv("JDBC_JAR_DIR") or "/opt/jdbc")
    #: 指定具体的 jar。留空则在 jdbc_jar_dir 下自动查找。
    hetu_jdbc_jar: str | None = os.getenv("HETU_JDBC_JAR") or None
    #: 服务端报 "Authentication requires SSL" 时置 true。
    hetu_jdbc_ssl: str = os.getenv("HETU_JDBC_SSL", "false")
    llm_base_url: str | None = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None
    llm_api_key: str | None = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or None
    llm_model_name: str | None = os.getenv("LLM_MODEL_NAME") or os.getenv("OPENAI_MODEL") or None
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    llm_max_attempts: int = int(os.getenv("LLM_MAX_ATTEMPTS", "5"))
    llm_backoff_seconds: float = float(os.getenv("LLM_BACKOFF_SECONDS", "5"))


settings = Settings()
