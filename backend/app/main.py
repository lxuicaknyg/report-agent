from __future__ import annotations

from fastapi import FastAPI

from .api.routes import (
    auth_router,
    connections_router,
    conversations_router,
    datasets_router,
    health_router,
    reports_router,
    supplements_router,
)
from .config import settings
from .dependencies import get_auth_service
from .infrastructure.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging(settings.log_dir, settings.log_level)
    # Build the auth service now rather than on the first request that needs it.
    # It is lru_cached, so this only moves the work earlier — but a missing
    # AUTH_SECRET in production raises here, which makes the container exit at
    # startup instead of coming up healthy and then failing every request with a
    # 500. A deployment that is wrong should look wrong immediately.
    get_auth_service()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.include_router(health_router)
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(datasets_router, prefix=settings.api_prefix)
    app.include_router(reports_router, prefix=settings.api_prefix)
    app.include_router(conversations_router, prefix=settings.api_prefix)
    app.include_router(connections_router, prefix=settings.api_prefix)
    app.include_router(supplements_router, prefix=settings.api_prefix)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
