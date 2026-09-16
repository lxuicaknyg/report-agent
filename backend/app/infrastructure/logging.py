from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(log_dir: Path, level: str = "INFO") -> None:
    """Configure application logging once: a rotating file sink plus the console.

    The console handler matters during development — report generation is a
    long, mostly invisible pipeline, and being able to watch it in the terminal
    that runs uvicorn is the difference between debuggable and opaque.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if any(getattr(handler, "name", None) == "report_agent_file" for handler in root.handlers):
        return
    root.setLevel(getattr(logging, level, logging.INFO))
    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        log_dir / "report-agent.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.name = "report_agent_file"
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.name = "report_agent_console"
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # The HTTP clients chatter at INFO on every model call; the LLM adapter
    # already logs what those calls did, with content.
    for name in ("httpx", "httpx2", "httpcore", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)


def preview(value: object, limit: int = 400) -> str:
    """Render content as one capped line so logs can carry it without flooding."""
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…(+{len(text) - limit} chars)"


#: Who the current model call belongs to. The LLM adapter logs every request
#: and response, but it has no idea which chapter or metric it is serving, and
#: two reports generating at once interleave their lines beyond recovery. The
#: agent sets this around the work; the adapter reads it back.
_work_context: ContextVar[str] = ContextVar("work_context", default="")


@contextmanager
def work_context(**fields: object):
    """Tag every log line emitted inside this block."""
    parts = [f"{key}={value}" for key, value in fields.items() if value not in (None, "")]
    token = _work_context.set(" ".join(parts))
    try:
        yield
    finally:
        _work_context.reset(token)


def work_tag() -> str:
    """The current tag, ready to append to a log message (empty when unset)."""
    value = _work_context.get()
    return f" {value}" if value else ""
