from __future__ import annotations

import base64
import hashlib
import hmac
import threading
import time
from typing import Any
from urllib.parse import quote, urlencode

import requests

from backend.config import get_settings, require_env


DATA_CENTER_URL = "https://apigateway.yonyoucloud.com/open-auth/dataCenter/getGatewayAddress"
TOKEN_PATH = "/open-auth/selfAppAuth/getAccessToken"

_TOKEN_CACHE: dict[str, dict[str, Any]] = {}
_TOKEN_LOCK = threading.Lock()
_SESSION = requests.Session()


def success_code(body: dict[str, Any], expected: str = "200") -> bool:
    return str(body.get("code") or "").strip() == expected


def api_get(url: str, params: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
    response = _SESSION.get(url, params=params, timeout=timeout)
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
    response = _SESSION.post(url, params=params, json=payload or {}, timeout=timeout)
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
    if settings.yonyou_tenant_id and settings.yonyou_gateway_url == settings.yonyou_token_url:
        return get_gateway_address(settings.yonyou_tenant_id)
    return settings.yonyou_gateway_url, settings.yonyou_token_url


def _cache_key(token_url: str, app_key: str) -> str:
    return f"{token_url}|{app_key}"


def _is_cached_token_valid(entry: dict[str, Any] | None, now: float) -> bool:
    if not entry:
        return False
    token = str(entry.get("token") or "")
    return bool(token) and now < float(entry.get("expires_at") or 0)


def get_access_token(token_url: str, force_refresh: bool = False) -> str:
    app_key = require_env("YONBIP_APP_KEY")
    app_secret = require_env("YONBIP_APP_SECRET")
    now = time.time()
    key = _cache_key(token_url, app_key)

    if not force_refresh:
        with _TOKEN_LOCK:
            cached = _TOKEN_CACHE.get(key)
            if _is_cached_token_valid(cached, now):
                return str(cached.get("token"))

    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(key)
        if not force_refresh and _is_cached_token_valid(cached, now):
            return str(cached.get("token"))

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
        _TOKEN_CACHE[key] = {
            "token": token,
            "expires_at": now + max(expire_seconds - 120, 60),
        }
        return token


def _is_token_invalid_error(body: dict[str, Any]) -> bool:
    code = str(body.get("code") or "")
    message = str(body.get("message") or "").lower()
    return code in {"401", "40001", "10010"} or "token" in message


def yonyou_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    gateway_url, token_url = resolve_endpoints()
    merged = dict(params or {})
    body: dict[str, Any] = {}
    for attempt in range(2):
        access_token = get_access_token(token_url, force_refresh=attempt == 1)
        body = api_get(f"{gateway_url}{path}", {"access_token": access_token, **merged})
        if attempt == 0 and _is_token_invalid_error(body):
            continue
        return body
    return body


def yonyou_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    gateway_url, token_url = resolve_endpoints()
    body: dict[str, Any] = {}
    for attempt in range(2):
        access_token = get_access_token(token_url, force_refresh=attempt == 1)
        body = api_post(f"{gateway_url}{path}", {"access_token": access_token}, payload)
        if attempt == 0 and _is_token_invalid_error(body):
            continue
        return body
    return body
