from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_backend_dir = Path(__file__).resolve().parents[1]
load_dotenv(_backend_dir / ".env")
_default_data_dir = Path(tempfile.gettempdir()) / "report-agent-data"
_configured_data_dir = os.getenv("DATA_DIR")
# 兼容旧 .env 中的 DATA_DIR=./data：该目录位于项目树内，会被 --reload 监听。
_data_dir = (
    _default_data_dir
    if not _configured_data_dir or _configured_data_dir in {"./data", "data"}
    else Path(_configured_data_dir)
)


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Report Agent Backend")
    environment: str = os.getenv("ENVIRONMENT", "development")
    api_prefix: str = os.getenv("API_PREFIX", "/api/v1")
    # 上传的 Excel 不要默认写入项目目录：开发环境通常使用 uvicorn --reload，
    # 写入 ./data 会触发进程重载，导致当前的内存报告 session 被清空并在轮询时返回 404。
    data_dir: Path = _data_dir
    artifact_dir: Path = Path(os.getenv("ARTIFACT_DIR", "./artifacts"))
    log_dir: Path = Path(os.getenv("LOG_DIR", "./logs"))
    # DEBUG additionally dumps each metric's full research conversation, which
    # is the only way to see what the model was actually shown when a number
    # comes back wrong.
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    database_url: str | None = os.getenv("DATABASE_URL") or None
    llm_base_url: str | None = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None
    llm_api_key: str | None = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or None
    llm_model_name: str | None = os.getenv("LLM_MODEL_NAME") or os.getenv("OPENAI_MODEL") or None
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    llm_max_attempts: int = int(os.getenv("LLM_MAX_ATTEMPTS", "5"))
    llm_backoff_seconds: float = float(os.getenv("LLM_BACKOFF_SECONDS", "5"))


settings = Settings()
