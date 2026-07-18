from __future__ import annotations

from typing import Any

from backend.clients.dingtalk.contact_api import sync_organization_users
from backend.clients.dingtalk.openapi_client import DingTalkOpenApiClient


def resolve_notification_recipients(
    recipient_rules: list[dict[str, Any]],
    client: DingTalkOpenApiClient,
) -> tuple[list[str], list[dict[str, str]]]:
    """Resolve saved people and departments against the current DingTalk directory."""
    users, _, _ = sync_organization_users(client, force_full=True)
    users_by_id = {str(item.get("userid") or ""): item for item in users if item.get("userid")}
    resolved: set[str] = set()
    skipped: list[dict[str, str]] = []

    for rule in recipient_rules:
        kind = str(rule.get("type") or "user")
        if kind == "department":
            try:
                department_id = int(rule.get("departmentId"))
            except (TypeError, ValueError):
                skipped.append({"name": str(rule.get("name") or "未知部门"), "reason": "部门配置无效"})
                continue
            members = [
                userid
                for userid, item in users_by_id.items()
                if department_id in {int(value) for value in item.get("dept_ids") or []}
            ]
            if not members:
                skipped.append({"name": str(rule.get("name") or department_id), "reason": "部门暂无有效成员"})
            resolved.update(members)
            continue

        userid = str(rule.get("userid") or "")
        if userid in users_by_id:
            resolved.add(userid)
        else:
            skipped.append({"name": str(rule.get("name") or userid), "reason": "已不在企业通讯录"})

    return sorted(resolved), skipped
