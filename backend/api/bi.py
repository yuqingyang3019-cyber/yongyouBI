from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.services.bi_service import execution_summary


router = APIRouter(prefix="/api/bi", tags=["bi"])


@router.get("/execution-summary")
def get_execution_summary(
    month: str | None = Query(default=None, description="统计月份，格式 YYYY-MM，不传则默认当月"),
    docTypes: str | None = Query(default=None, description="逗号分隔的单据类型"),
) -> dict:
    doc_types = [item.strip() for item in docTypes.split(",") if item.strip()] if docTypes else None
    try:
        return execution_summary(month=month, doc_types=doc_types)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
