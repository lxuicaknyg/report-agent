from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


_backend_dir = Path(__file__).resolve().parents[1]
load_dotenv(_backend_dir / ".env")


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Report Agent Backend")
    environment: str = os.getenv("ENVIRONMENT", "development")
    api_prefix: str = os.getenv("API_PREFIX", "/api/v1")
    data_dir: Path = Path(os.getenv("DATA_DIR", "./data"))
    artifact_dir: Path = Path(os.getenv("ARTIFACT_DIR", "./artifacts"))
    log_dir: Path = Path(os.getenv("LOG_DIR", "./logs"))
    database_url: str | None = os.getenv("DATABASE_URL") or None
    llm_base_url: str | None = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None
    llm_api_key: str | None = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or None
    llm_model_name: str | None = os.getenv("LLM_MODEL_NAME") or os.getenv("OPENAI_MODEL") or None


settings = Settings()
