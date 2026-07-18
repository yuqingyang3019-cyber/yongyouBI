from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException

from backend.auth.session import current_user
from backend.config import optional_env


router = APIRouter(
    prefix="/api/sqlbot",
    tags=["sqlbot"],
    dependencies=[Depends(current_user)],
)


@router.get("/embed-token")
def get_sqlbot_embed_token() -> dict[str, object]:
    base_url = optional_env("SQLBOT_BASE_URL", "http://localhost:8080").rstrip("/")
    app_id = optional_env("SQLBOT_APP_ID")
    app_secret = optional_env("SQLBOT_APP_SECRET")
    account = optional_env("SQLBOT_EMBED_ACCOUNT")
    embedded_id = optional_env("SQLBOT_EMBEDDED_ID")
    if not all((app_id, app_secret, account, embedded_id)):
        raise HTTPException(status_code=503, detail="SQLBot 嵌入应用尚未配置")
    try:
        numeric_id = int(embedded_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="SQLBOT_EMBEDDED_ID 必须是整数") from exc

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    token = jwt.encode(
        {
            "appId": app_id,
            "embeddedId": numeric_id,
            "account": account,
            "exp": expires_at,
        },
        app_secret,
        algorithm="HS256",
    )
    return {
        "baseUrl": base_url,
        "embeddedId": numeric_id,
        "token": token,
        "expiresAt": int(expires_at.timestamp()),
    }
