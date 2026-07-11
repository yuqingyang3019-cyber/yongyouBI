from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.services.bi_service import execution_summary
from backend.services.overdue_service import contract_overdue
from backend.services.sync_service import get_sync_status, kick_sync


router = APIRouter(prefix="/api/bi", tags=["bi"])


@router.get("/execution-summary")
def get_execution_summary(
    month: Optional[str] = Query(default=None, description="统计月份，格式 YYYY-MM，不传则默认当月"),
    docTypes: Optional[str] = Query(default=None, description="逗号分隔的单据类型"),
    persons: Optional[str] = Query(default=None, description="逗号分隔的执行人过滤条件"),
    personMatchMode: str = Query(default="contains", description="执行人匹配模式：contains 或 exact"),
    topN: int = Query(default=10, ge=1, le=100, description="TopN 执行人数量"),
    refresh: bool = Query(default=False, description="是否强制刷新并跳过缓存"),
) -> dict:
    doc_types = [item.strip() for item in docTypes.split(",") if item.strip()] if docTypes else None
    person_filters = [item.strip() for item in persons.split(",") if item.strip()] if persons else None
    try:
        return execution_summary(
            month=month,
            doc_types=doc_types,
            persons=person_filters,
            person_match_mode=personMatchMode,
            top_n=topN,
            refresh=refresh,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
        return get_sync_status(month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/contract-overdue/sync")
def post_contract_overdue_sync(
    month: Optional[str] = Query(default=None, description="已废弃，忽略"),
) -> dict:
    try:
        return kick_sync(month, force=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
