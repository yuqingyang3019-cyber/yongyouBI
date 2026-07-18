from __future__ import annotations

from fastapi import FastAPI

from backend.api.auth import router as auth_router
from backend.api.notifications import router as notifications_router
from backend.api.receivables import router as receivables_router
from backend.api.sqlbot import router as sqlbot_router
from backend.app_factory import create_app as create_fastapi_app


def create_app() -> FastAPI:
    return create_fastapi_app(
        title="应收逾期管理",
        routers=[auth_router, receivables_router, notifications_router, sqlbot_router],
    )


app = create_app()
