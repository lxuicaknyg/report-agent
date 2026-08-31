from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: Path) -> None:
    """Configure application logging once, with a rotating file sink."""
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if any(getattr(handler, "name", None) == "report_agent_file" for handler in root.handlers):
        return
    root.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_dir / "report-agent.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.name = "report_agent_file"
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    root.addHandler(handler)
