from __future__ import annotations

import threading
import time
from typing import Any

import requests

from backend.config import optional_env


class DingTalkApiError(RuntimeError):
    pass


class DingTalkOpenApiClient:
    def __init__(self, app_key: str, app_secret: str) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._token = ""
        self._token_expire_at = 0.0
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> DingTalkOpenApiClient | None:
        app_key = optional_env("DINGTALK_APP_KEY")
        app_secret = optional_env("DINGTALK_APP_SECRET")
        if not app_key or not app_secret:
            return None
        return cls(app_key, app_secret)

    def _refresh_token(self) -> str:
        response = requests.post(
            "https://api.dingtalk.com/v1.0/oauth2/accessToken",
            json={"appKey": self._app_key, "appSecret": self._app_secret},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        token = str(payload.get("accessToken") or "")
        if not token:
            raise DingTalkApiError("获取 accessToken 失败")
        expire_in = int(payload.get("expireIn") or 7200)
        self._token = token
        self._token_expire_at = time.time() + max(expire_in - 120, 60)
        return token

    def access_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_expire_at:
                return self._token
            return self._refresh_token()

    def _parse_topapi_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        errcode = payload.get("errcode")
        if errcode not in (0, "0", None):
            errmsg = str(payload.get("errmsg") or payload)
            raise DingTalkApiError(f"[{errcode}] {errmsg}")
        result = payload.get("result")
        if isinstance(result, dict):
            return result
        if result is not None:
            return {"value": result}
        return payload

    def topapi_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        token = self.access_token()
        url = f"https://oapi.dingtalk.com/{path.lstrip('/')}"
        query = {"access_token": token, **(params or {})}
        response = requests.get(url, params=query, timeout=45)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload.get("department"), list):
            return payload
        return self._parse_topapi_payload(payload)

    def topapi_post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        token = self.access_token()
        url = f"https://oapi.dingtalk.com/{path.lstrip('/')}"
        response = requests.post(
            url,
            params={"access_token": token},
            json=body,
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        return self._parse_topapi_payload(payload)

    def api_post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        token = self.access_token()
        url = f"https://api.dingtalk.com/{path.lstrip('/')}"
        response = requests.post(
            url,
            headers={
                "x-acs-dingtalk-access-token": token,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise DingTalkApiError("钉钉接口返回不是 JSON 对象")
        if payload.get("success") is False:
            code = str(payload.get("code") or "")
            message = str(payload.get("message") or payload)
            raise DingTalkApiError(f"[{code}] {message}".strip())
        return payload
