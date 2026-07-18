from __future__ import annotations

from typing import Any

from backend.clients.dingtalk.openapi_client import DingTalkOpenApiClient
from backend.config import optional_env


def public_auth_config() -> dict[str, Any]:
    corp_id = optional_env("DINGTALK_CORP_ID")
    client_id = optional_env("DINGTALK_APP_KEY")
    return {
        "configured": bool(corp_id and client_id and optional_env("DINGTALK_APP_SECRET")),
        "corpId": corp_id,
        "clientId": client_id,
        "dingtalkLoginEnabled": optional_env("DINGTALK_LOGIN_ENABLED", "true").lower()
        in {"1", "true", "yes"},
        "browserLoginEnabled": optional_env("ALLOW_BROWSER_LOGIN", "false").lower()
        in {"1", "true", "yes"},
    }


def exchange_auth_code(code: str, corp_id: str) -> dict[str, Any]:
    configured_corp_id = optional_env("DINGTALK_CORP_ID")
    if not configured_corp_id or corp_id != configured_corp_id:
        raise ValueError("corpId 与服务端配置不一致")
    client = DingTalkOpenApiClient.from_env()
    if client is None:
        raise RuntimeError("未配置 DINGTALK_APP_KEY / DINGTALK_APP_SECRET")
    login = client.topapi_post("topapi/v2/user/getuserinfo", {"code": code})
    userid = str(login.get("userid") or login.get("userId") or "")
    if not userid:
        raise RuntimeError("钉钉免登接口未返回 userid")
    detail = client.topapi_post("topapi/v2/user/get", {"userid": userid})
    return {
        "userid": userid,
        "name": str(detail.get("name") or login.get("name") or userid),
        "avatar": str(detail.get("avatar") or ""),
        "title": str(detail.get("title") or ""),
    }
