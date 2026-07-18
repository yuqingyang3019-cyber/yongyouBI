from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException, Request, Response

from backend.config import optional_env

SESSION_COOKIE = "yongyou_bi_session"
SESSION_TYPE = "dingtalk_user"


def _ttl_seconds() -> int:
    try:
        return max(300, int(optional_env("SESSION_TTL_SECONDS", "604800")))
    except ValueError:
        return 604800


def _secret() -> str:
    return optional_env("APP_SESSION_SECRET")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def sign_session(user: dict[str, Any], *, now: float | None = None) -> str:
    secret = _secret()
    if not secret:
        raise RuntimeError("未配置 APP_SESSION_SECRET")
    issued_at = now if now is not None else time.time()
    payload = {
        "typ": SESSION_TYPE,
        "exp": issued_at + _ttl_seconds(),
        "userid": str(user.get("userid") or ""),
        "name": str(user.get("name") or user.get("userid") or ""),
        "avatar": str(user.get("avatar") or ""),
        "title": str(user.get("title") or ""),
    }
    body = _encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())
    signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def verify_session(token: str, *, now: float | None = None) -> dict[str, Any] | None:
    secret = _secret()
    if not secret or "." not in token:
        return None
    body, signature = token.rsplit(".", 1)
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_decode(body))
        expires_at = float(payload.get("exp") or 0)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    current = now if now is not None else time.time()
    if payload.get("typ") != SESSION_TYPE or not payload.get("userid") or current > expires_at:
        return None
    return payload


def set_session_cookie(response: Response, user: dict[str, Any]) -> None:
    domain = optional_env("COOKIE_DOMAIN") or None
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(user),
        max_age=_ttl_seconds(),
        path="/",
        domain=domain,
        httponly=True,
        secure=optional_env("COOKIE_SECURE", "false").lower() in {"1", "true", "yes"},
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    domain = optional_env("COOKIE_DOMAIN") or None
    response.delete_cookie(SESSION_COOKIE, path="/", domain=domain, samesite="lax")


def current_user(request: Request) -> dict[str, Any]:
    if not _secret():
        raise HTTPException(status_code=500, detail="未配置 APP_SESSION_SECRET")
    user = verify_session(request.cookies.get(SESSION_COOKIE, ""))
    if not user:
        raise HTTPException(status_code=401, detail="登录已失效，请重新进入钉钉应用")
    return user


def require_trusted_origin(request: Request) -> None:
    origin = (request.headers.get("origin") or "").rstrip("/")
    if not origin:
        return
    configured = {
        item.strip().rstrip("/")
        for item in optional_env("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if item.strip()
    }
    request_origin = f"{request.url.scheme}://{request.url.netloc}".rstrip("/")
    if origin != request_origin and origin not in configured:
        raise HTTPException(status_code=403, detail="请求来源不受信任")
