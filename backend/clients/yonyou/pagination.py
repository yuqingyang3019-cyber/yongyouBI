from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from backend.clients.yonyou.client import success_code, yonyou_post
from backend.config import get_settings


@dataclass
class PageResult:
    records: list[dict[str, Any]]
    record_count: int
    page_count: int
    fetched_pages: int
    truncated: bool


def fetch_pages(path: str, payload_factory: Callable[[int, int], dict[str, Any]]) -> PageResult:
    settings = get_settings()
    all_records: list[dict[str, Any]] = []
    record_count = 0
    page_count = 1
    fetched_pages = 0

    for page_index in range(1, settings.request_max_pages + 1):
        body = yonyou_post(path, payload_factory(page_index, settings.request_page_size))
        if not success_code(body, "200"):
            raise RuntimeError(f"用友接口调用失败：{path}，{body.get('message') or body}")
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        record_list = data.get("recordList") if isinstance(data.get("recordList"), list) else []
        records = [item for item in record_list if isinstance(item, dict)]
        record_count = int(data.get("recordCount") or len(records))
        page_count = int(data.get("pageCount") or 1)
        all_records.extend(records)
        fetched_pages = page_index
        if page_index >= page_count or not records:
            break
        if record_count > 0 and len(all_records) >= record_count:
            break

    return PageResult(
        records=all_records,
        record_count=record_count,
        page_count=page_count,
        fetched_pages=fetched_pages,
        truncated=page_count > fetched_pages,
    )
