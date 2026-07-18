from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.auth.session import current_user, require_trusted_origin
from backend.clients.dingtalk.contact_api import list_organization_users
from backend.clients.dingtalk.openapi_client import DingTalkOpenApiClient
from backend.db.contact_cache_store import get_contact_cache_store
from backend.db.notification_task_store import get_notification_task_store, next_run_at
from backend.services.notification_recipient_service import resolve_notification_recipients
from backend.services.receivable_notify_service import send_receivable_digest

router = APIRouter(
    prefix="/api/notifications",
    tags=["notifications"],
    dependencies=[Depends(current_user)],
)


class ScheduleInput(BaseModel):
    kind: Literal["minutes", "hours", "daily", "weekly"]
    interval: int = Field(default=1, ge=1, le=1440)
    hour: int = Field(default=9, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    weekday: int = Field(default=0, ge=0, le=6)


class CreateTaskInput(BaseModel):
    recipientUserids: list[str] = Field(default_factory=list, max_length=20)
    recipientDepartmentIds: list[int] = Field(default_factory=list, max_length=20)
    schedule: ScheduleInput


class EnabledInput(BaseModel):
    enabled: bool


def _client() -> DingTalkOpenApiClient:
    client = DingTalkOpenApiClient.from_env()
    if client is None:
        raise HTTPException(status_code=500, detail="未配置钉钉应用凭证")
    return client


def _safe_user(user: dict[str, Any]) -> dict[str, str]:
    return {
        "userid": str(user.get("userid") or ""),
        "name": str(user.get("name") or ""),
        "department": str(user.get("dept_name") or ""),
        "title": str(user.get("title") or ""),
    }


@router.get("/contacts")
def search_contacts(
    q: str = Query(default="", max_length=50),
    _user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    keyword = q.strip().lower()
    users = list_organization_users(_client())
    matches = [
        _safe_user(item)
        for item in users
        if not keyword
        or keyword in str(item.get("name") or "").lower()
        or keyword in str(item.get("dept_name") or "").lower()
    ]
    return {"items": matches[:50]}


@router.get("/departments")
def search_departments(
    q: str = Query(default="", max_length=50),
    _user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    list_organization_users(_client())
    keyword = q.strip().lower()
    items = [
        {"departmentId": dept_id, "name": name}
        for dept_id, name in get_contact_cache_store().get_dept_map().items()
        if not keyword or keyword in name.lower()
    ]
    return {"items": items[:50]}


@router.get("/tasks")
def list_tasks(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {"items": get_notification_task_store().list_for_user(str(user["userid"]))}


@router.post("/tasks")
def create_task(
    payload: CreateTaskInput,
    request: Request,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    require_trusted_origin(request)
    schedule = payload.schedule.model_dump()
    next_run_at(schedule)
    requested = list(dict.fromkeys(item.strip() for item in payload.recipientUserids if item.strip()))
    department_ids = list(dict.fromkeys(payload.recipientDepartmentIds))
    if not requested and not department_ids:
        raise HTTPException(status_code=400, detail="请选择至少一位接收人或一个部门")
    users = list_organization_users(_client())
    available = {
        str(item.get("userid") or ""): _safe_user(item)
        for item in users
        if item.get("userid")
    }
    if len(requested) != len(payload.recipientUserids) or any(item not in available for item in requested):
        raise HTTPException(status_code=400, detail="接收人无效或已不在企业通讯录")
    recipients = [{**available[item], "type": "user"} for item in requested]
    departments = get_contact_cache_store().get_dept_map()
    missing_departments = [item for item in department_ids if item not in departments]
    if missing_departments:
        raise HTTPException(status_code=400, detail="接收部门无效或已不存在")
    recipients.extend(
        {"type": "department", "departmentId": item, "name": departments[item], "userid": ""}
        for item in department_ids
    )
    store = get_notification_task_store()
    task = store.create(user, recipients, schedule)
    try:
        user_ids, skipped = resolve_notification_recipients(recipients, _client())
        if not user_ids:
            raise ValueError("当前接收范围没有有效的钉钉成员")
        result = send_receivable_digest(user_ids)
        store.record_result(task["id"], success=True)
        immediate = {"success": True, "skipped": skipped, **result}
    except Exception as exc:
        store.record_result(task["id"], success=False, error=str(exc))
        immediate = {"success": False, "error": "任务已创建，但首次发送失败"}
    return {"task": store.get(task["id"], str(user["userid"])), "immediate": immediate}


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: str,
    payload: EnabledInput,
    request: Request,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    require_trusted_origin(request)
    try:
        task = get_notification_task_store().set_enabled(task_id, str(user["userid"]), payload.enabled)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc
    return {"task": task}


@router.delete("/tasks/{task_id}")
def delete_task(
    task_id: str,
    request: Request,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, bool]:
    require_trusted_origin(request)
    try:
        get_notification_task_store().delete(task_id, str(user["userid"]))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="任务不存在") from exc
    return {"ok": True}
