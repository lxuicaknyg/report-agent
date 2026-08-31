from __future__ import annotations

from fastapi import FastAPI

from .api.routes import analysis_router, datasets_router, health_router, reports_router
from .config import settings
from .infrastructure.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging(settings.log_dir)
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.include_router(health_router)
    app.include_router(datasets_router, prefix=settings.api_prefix)
    app.include_router(analysis_router, prefix=settings.api_prefix)
    app.include_router(reports_router, prefix=settings.api_prefix)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
