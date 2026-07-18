from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.scheduler import app_lifespan


def create_app(*, title: str, routers: Iterable[APIRouter]) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=title, version="0.1.0", lifespan=app_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in routers:
        app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
