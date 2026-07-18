from __future__ import annotations

import json
import time
from typing import Any

from backend.clients.dingtalk.openapi_client import DingTalkOpenApiClient
from backend.config import optional_env

_DEFAULT_ROBOT_CODE = "dingsifjezvqedsoanhf"
_BATCH_SIZE = 20
_SEND_INTERVAL_SEC = 0.15


def robot_code_from_env() -> str:
    return optional_env("DINGTALK_ROBOT_CODE", _DEFAULT_ROBOT_CODE)


def send_robot_markdown(
    client: DingTalkOpenApiClient,
    *,
    robot_code: str,
    user_ids: list[str],
    title: str,
    text: str,
) -> dict[str, Any]:
    if not robot_code:
        raise ValueError("未配置 DINGTALK_ROBOT_CODE")
    if not user_ids:
        raise ValueError("接收人不能为空")
    if len(user_ids) > _BATCH_SIZE:
        raise ValueError(f"单批接收人不能超过 {_BATCH_SIZE} 人")
    return client.api_post(
        "v1.0/robot/oToMessages/batchSend",
        {
            "robotCode": robot_code,
            "userIds": user_ids,
            "msgKey": "sampleMarkdown",
            "msgParam": json.dumps({"title": title, "text": text}, ensure_ascii=False),
        },
    )


def send_robot_markdown_to_users(
    client: DingTalkOpenApiClient,
    *,
    user_ids: list[str],
    title: str,
    text: str,
    robot_code: str | None = None,
) -> dict[str, Any]:
    code = robot_code or robot_code_from_env()
    sent = 0
    for offset in range(0, len(user_ids), _BATCH_SIZE):
        batch = user_ids[offset : offset + _BATCH_SIZE]
        send_robot_markdown(
            client,
            robot_code=code,
            user_ids=batch,
            title=title,
            text=text,
        )
        sent += len(batch)
    return {"sent": sent, "total": len(user_ids)}


def send_robot_markdown_to_user(
    client: DingTalkOpenApiClient,
    *,
    userid: str,
    title: str,
    text: str,
    robot_code: str | None = None,
) -> dict[str, Any]:
    code = robot_code or robot_code_from_env()
    return send_robot_markdown(
        client,
        robot_code=code,
        user_ids=[userid],
        title=title,
        text=text,
    )


def send_robot_markdown_messages(
    client: DingTalkOpenApiClient,
    *,
    userid: str,
    messages: list[tuple[str, str]],
    robot_code: str | None = None,
) -> dict[str, Any]:
    code = robot_code or robot_code_from_env()
    sent = 0
    failed: list[dict[str, str]] = []
    for index, (title, text) in enumerate(messages, start=1):
        try:
            send_robot_markdown_to_user(
                client,
                userid=userid,
                title=title,
                text=text,
                robot_code=code,
            )
            sent += 1
        except Exception as exc:
            failed.append({"index": str(index), "title": title, "error": str(exc)})
        if index < len(messages):
            time.sleep(_SEND_INTERVAL_SEC)
    return {"sent": sent, "failed": failed, "total": len(messages)}
