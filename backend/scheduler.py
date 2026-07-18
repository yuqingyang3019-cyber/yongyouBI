from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from backend.db.notification_task_store import get_notification_task_store
from backend.clients.dingtalk.openapi_client import DingTalkOpenApiClient
from backend.services.notification_recipient_service import resolve_notification_recipients
from backend.services.receivable_notify_service import send_receivable_digest

logger = logging.getLogger(__name__)
_scheduler = None


def start_receivable_scheduler() -> None:
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("未安装 apscheduler，应收逾期定时通知未启动")
        return

    if _scheduler is not None:
        return

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    def _dispatch_due_tasks() -> None:
        store = get_notification_task_store()
        for task in store.claim_due():
            try:
                client = DingTalkOpenApiClient.from_env()
                if client is None:
                    raise RuntimeError("未配置钉钉应用凭证")
                user_ids, skipped = resolve_notification_recipients(task["recipients"], client)
                if not user_ids:
                    raise ValueError("当前接收范围没有有效的钉钉成员")
                result = send_receivable_digest(user_ids)
                store.record_result(task["id"], success=True)
                logger.info("应收逾期摘要任务已发送：task=%s result=%s skipped=%s", task["id"], result, skipped)
            except Exception as exc:
                store.record_result(task["id"], success=False, error=str(exc))
                logger.exception("应收逾期摘要任务发送失败：task=%s", task["id"])

    scheduler.add_job(
        _dispatch_due_tasks,
        "interval",
        minutes=1,
        id="receivable_notification_dispatcher",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("应收逾期动态通知调度器已启动")


def stop_receivable_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


@asynccontextmanager
async def app_lifespan(_app: object) -> AsyncIterator[None]:
    start_receivable_scheduler()
    try:
        yield
    finally:
        stop_receivable_scheduler()
