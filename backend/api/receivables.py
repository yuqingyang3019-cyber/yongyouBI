from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.auth.session import current_user, require_trusted_origin
from backend.services.collection_sync_service import get_collection_sync_status, kick_collection_sync
from backend.services.overdue_service import contract_overdue
from backend.services.receivable_sync_service import get_receivable_sync_status, kick_receivable_sync


router = APIRouter(
    prefix="/api/bi",
    tags=["receivables"],
    dependencies=[Depends(current_user)],
)


@router.get("/contract-overdue")
def get_contract_overdue(
    month: Optional[str] = Query(default=None, description="已废弃，忽略"),
    status: Optional[str] = Query(
        default="overdue,upcoming,normal",
        description="逗号分隔状态：overdue / upcoming / normal",
    ),
    sync: bool = Query(default=True, description="是否在返回本地数据同时触发后台增量同步"),
) -> dict:
    statuses = [item.strip() for item in (status or "").split(",") if item.strip()]
    try:
        return contract_overdue(month=month, statuses=statuses or None, kick=sync)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/contract-overdue/sync-status")
def get_contract_overdue_sync_status(
    month: Optional[str] = Query(default=None, description="已废弃，忽略"),
) -> dict:
    try:
        receivable = get_receivable_sync_status(month)
        collection = get_collection_sync_status(month)
        updated_at = max(receivable.get("updatedAt") or "", collection.get("updatedAt") or "")
        return {
            **receivable,
            "updatedAt": updated_at,
            "collectionSync": collection,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/contract-overdue/sync")
def post_contract_overdue_sync(
    request: Request,
    month: Optional[str] = Query(default=None, description="已废弃，忽略"),
) -> dict:
    require_trusted_origin(request)
    try:
        kick_receivable_sync(month, force=True)
        return kick_collection_sync(month, force=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
