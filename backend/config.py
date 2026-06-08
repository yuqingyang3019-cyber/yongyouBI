from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_YONBIP_GATEWAY_URL = "https://c3.yonyoucloud.com/iuap-api-gateway"
DEFAULT_YONBIP_TOKEN_URL = "https://c3.yonyoucloud.com/iuap-api-gateway"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_env_file(path: Path = PROJECT_ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()


def optional_env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def require_env(name: str) -> str:
    value = optional_env(name)
    if not value:
        raise RuntimeError(f"缺少配置：{name}")
    return value


@dataclass(frozen=True)
class Settings:
    yonyou_gateway_url: str
    yonyou_token_url: str
    yonyou_tenant_id: str
    request_page_size: int
    request_max_pages: int
    allowed_origins: list[str]


def _as_int(name: str, default: int) -> int:
    value = optional_env(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"配置必须是整数：{name}") from exc


def get_settings() -> Settings:
    origins = optional_env("ALLOWED_ORIGINS", "http://localhost:5173")
    return Settings(
        yonyou_gateway_url=optional_env("YONBIP_GATEWAY_URL", DEFAULT_YONBIP_GATEWAY_URL).rstrip("/"),
        yonyou_token_url=optional_env("YONBIP_TOKEN_URL", DEFAULT_YONBIP_TOKEN_URL).rstrip("/"),
        yonyou_tenant_id=optional_env("YONBIP_TENANT_ID"),
        request_page_size=_as_int("YONBIP_PAGE_SIZE", 200),
        request_max_pages=_as_int("YONBIP_MAX_PAGES", 50),
        allowed_origins=[origin.strip() for origin in origins.split(",") if origin.strip()],
    )
