from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any
from urllib.parse import quote, urlencode

import requests

from backend.config import get_settings, require_env


DATA_CENTER_URL = "https://apigateway.yonyoucloud.com/open-auth/dataCenter/getGatewayAddress"
TOKEN_PATH = "/open-auth/selfAppAuth/getAccessToken"

_TOKEN_CACHE: dict[str, Any] = {"token": "", "expires_at": 0.0}


def success_code(body: dict[str, Any], expected: str = "200") -> bool:
    return str(body.get("code") or "").strip() == expected


def api_get(url: str, params: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError(f"接口返回不是 JSON 对象：{url}")
    return body


def api_post(
    url: str,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    response = requests.post(url, params=params, json=payload or {}, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError(f"接口返回不是 JSON 对象：{url}")
    return body


def sign_token_request(app_key: str, app_secret: str, timestamp: int) -> str:
    plain = f"appKey{app_key}timestamp{timestamp}"
    digest = hmac.new(app_secret.encode("utf-8"), plain.encode("utf-8"), hashlib.sha256).digest()
    return quote(base64.b64encode(digest).decode("ascii"), safe="")


def get_gateway_address(tenant_id: str) -> tuple[str, str]:
    body = api_get(DATA_CENTER_URL, {"tenantId": tenant_id})
    if not success_code(body, "00000"):
        raise RuntimeError(f"获取用友数据中心域名失败：{body.get('message') or body}")
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    gateway_url = str(data.get("gatewayUrl") or "").rstrip("/")
    token_url = str(data.get("tokenUrl") or "").rstrip("/")
    if not gateway_url or not token_url:
        raise RuntimeError("用友数据中心域名返回缺少 gatewayUrl 或 tokenUrl")
    return gateway_url, token_url


def resolve_endpoints() -> tuple[str, str]:
    settings = get_settings()
    if settings.yonyou_tenant_id and not settings.yonyou_gateway_url:
        return get_gateway_address(settings.yonyou_tenant_id)
    return settings.yonyou_gateway_url, settings.yonyou_token_url


def get_access_token(token_url: str) -> str:
    now = time.time()
    cached_token = str(_TOKEN_CACHE.get("token") or "")
    if cached_token and now < float(_TOKEN_CACHE.get("expires_at") or 0):
        return cached_token

    app_key = require_env("YONBIP_APP_KEY")
    app_secret = require_env("YONBIP_APP_SECRET")
    timestamp = int(now * 1000)
    signature = sign_token_request(app_key, app_secret, timestamp)
    query = urlencode({"appKey": app_key, "timestamp": timestamp})
    body = api_get(f"{token_url}{TOKEN_PATH}?{query}&signature={signature}")
    if not success_code(body, "00000"):
        raise RuntimeError(f"获取用友 access_token 失败：{body.get('message') or body}")

    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    token = str(data.get("access_token") or "")
    if not token:
        raise RuntimeError("获取用友 access_token 成功但返回为空")

    expire_seconds = int(data.get("expire") or 7200)
    _TOKEN_CACHE.update({"token": token, "expires_at": now + max(expire_seconds - 60, 60)})
    return token


def yonyou_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    gateway_url, token_url = resolve_endpoints()
    access_token = get_access_token(token_url)
    merged_params = {"access_token": access_token, **(params or {})}
    return api_get(f"{gateway_url}{path}", merged_params)


def yonyou_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    gateway_url, token_url = resolve_endpoints()
    access_token = get_access_token(token_url)
    return api_post(f"{gateway_url}{path}", {"access_token": access_token}, payload)
