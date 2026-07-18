from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from backend.auth.session import (
    clear_session_cookie,
    current_user,
    require_trusted_origin,
    set_session_cookie,
)
from backend.clients.dingtalk.auth_api import exchange_auth_code, public_auth_config
from backend.config import optional_env

router = APIRouter(prefix="/api/auth", tags=["auth"])


class DingTalkLoginRequest(BaseModel):
    code: str
    corpId: str


@router.get("/config")
def get_auth_config() -> dict[str, Any]:
    return public_auth_config()


@router.get("/me")
def get_me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {"user": user}


@router.post("/dingtalk-login")
def dingtalk_login(
    payload: DingTalkLoginRequest,
    response: Response,
    request: Request,
) -> dict[str, Any]:
    require_trusted_origin(request)
    if optional_env("DINGTALK_LOGIN_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=404, detail="钉钉登录未启用")
    code = payload.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="免登码不能为空")
    try:
        user = exchange_auth_code(code, payload.corpId.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="钉钉免登失败，请联系管理员检查应用权限") from exc
    set_session_cookie(response, user)
    return {"user": user}


@router.post("/browser-login")
def browser_login(response: Response, request: Request) -> dict[str, Any]:
    require_trusted_origin(request)
    if optional_env("ALLOW_BROWSER_LOGIN", "false").lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=404, detail="浏览器登录未启用")
    user = {
        "userid": optional_env("BROWSER_LOGIN_USERID", "local-browser-user"),
        "name": optional_env("BROWSER_LOGIN_NAME", "本地用户"),
        "avatar": "",
        "title": "浏览器调试",
    }
    set_session_cookie(response, user)
    return {"user": user}


@router.post("/logout")
def logout(response: Response, request: Request) -> dict[str, bool]:
    require_trusted_origin(request)
    clear_session_cookie(response)
    return {"ok": True}
