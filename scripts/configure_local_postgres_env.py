from __future__ import annotations

import secrets
import re
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def read_env() -> tuple[list[str], dict[str, str]]:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    values: dict[str, str] = {}
    for line in lines:
        text = line.strip()
        if text and not text.startswith("#") and "=" in text:
            key, value = text.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return lines, values


def main() -> None:
    lines, values = read_env()
    app_password = values.get("RECEIVABLE_DB_PASSWORD") or secrets.token_urlsafe(24)
    reader_password = values.get("SQLBOT_DB_PASSWORD") or secrets.token_urlsafe(24)
    current_admin_password = values.get("SQLBOT_ADMIN_PASSWORD", "")
    valid_admin_password = re.fullmatch(
        r"(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*]).{8,20}",
        current_admin_password,
    )
    sqlbot_admin_password = current_admin_password if valid_admin_password else (
        "Sb!9" + secrets.token_hex(6)
    )
    app_user = values.get("RECEIVABLE_DB_USER") or "yongyou_app"
    reader_user = values.get("SQLBOT_DB_USER") or "sqlbot_reader"
    database = values.get("RECEIVABLE_DB_NAME") or "yongyou_receivables"
    updates = {
        "RECEIVABLE_DB_NAME": database,
        "RECEIVABLE_DB_USER": app_user,
        "RECEIVABLE_DB_PASSWORD": app_password,
        "SQLBOT_DB_USER": reader_user,
        "SQLBOT_DB_PASSWORD": reader_password,
        "RECEIVABLE_DATABASE_URL": (
            f"postgresql://{app_user}:{quote(app_password)}@127.0.0.1:5432/{database}"
        ),
        "RECEIVABLE_TEST_DATABASE_URL": (
            f"postgresql://{app_user}:{quote(app_password)}@127.0.0.1:5432/{database}_test"
        ),
        "SQLBOT_DATABASE_URL": (
            f"postgresql://{reader_user}:{quote(reader_password)}@127.0.0.1:5432/{database}"
        ),
        "SQLBOT_ADMIN_PASSWORD": sqlbot_admin_password,
    }

    replaced: set[str] = set()
    output: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in updates:
            output.append(f"{key}={updates[key]}")
            replaced.add(key)
        else:
            output.append(line)
    missing = [(key, value) for key, value in updates.items() if key not in replaced]
    if missing:
        if output and output[-1]:
            output.append("")
        output.append("# 本地应收 PostgreSQL")
        for key, value in missing:
            output.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(output) + "\n", encoding="utf-8")
    print("本地 PostgreSQL 连接配置已写入 .env（密码未输出）")


if __name__ == "__main__":
    main()
