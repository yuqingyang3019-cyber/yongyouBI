from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import load_env_file, optional_env, require_env


load_env_file()
BASE_URL = optional_env("SQLBOT_ADMIN_BASE_URL", optional_env("SQLBOT_BASE_URL", "http://localhost:8080")).rstrip("/")
DEFAULT_PASSWORD = "SQLBot@123456"
AES_KEY_HEX = "53514c426f7431323334353637383930"


def _unwrap(response: requests.Response) -> Any:
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def _login_encrypt(value: str) -> str:
    container_name = optional_env("SQLBOT_CONTAINER_NAME", "yongyou-sqlbot")
    script = (
        "import asyncio, os\n"
        "from common.utils.crypto import sqlbot_encrypt\n"
        "print(asyncio.run(sqlbot_encrypt(os.environ['SQLBOT_VALUE'])))\n"
    )
    output = subprocess.check_output(
        [
            "docker",
            "exec",
            "-e",
            f"SQLBOT_VALUE={value}",
            container_name,
            "sh",
            "-lc",
            "cd /opt/sqlbot/app && .venv/bin/python - <<'PY'\n" + script + "PY",
        ],
        text=True,
    )
    values = [line for line in output.splitlines() if re.fullmatch(r"[A-Za-z0-9+/=]{100,}", line)]
    if not values:
        raise RuntimeError("无法生成 SQLBot 登录加密值")
    return values[-1]


def _login(password: str) -> str:
    return _unwrap(
        requests.post(
            f"{BASE_URL}/api/v1/login/access-token",
            data={
                "username": _login_encrypt("admin"),
                "password": _login_encrypt(password),
            },
            timeout=20,
        )
    )["access_token"]


def _aes_encrypt(value: dict[str, Any]) -> str:
    result = subprocess.run(
        [
            "openssl",
            "enc",
            "-aes-128-ecb",
            "-K",
            AES_KEY_HEX,
            "-nosalt",
            "-base64",
            "-A",
        ],
        input=json.dumps(value, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("ascii")


def _save_env(updates: dict[str, str]) -> None:
    env_file = ROOT / ".env"
    lines = env_file.read_text(encoding="utf-8").splitlines()
    replaced: set[str] = set()
    output: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in updates:
            output.append(f"{key}={updates[key]}")
            replaced.add(key)
        else:
            output.append(line)
    if any(key not in replaced for key in updates):
        output.append("")
        output.append("# SQLBot 页面嵌入")
        output.extend(f"{key}={value}" for key, value in updates.items() if key not in replaced)
    env_file.write_text("\n".join(output) + "\n", encoding="utf-8")


def main() -> None:
    configured_password = require_env("SQLBOT_ADMIN_PASSWORD")
    password_used = configured_password
    try:
        token = _login(configured_password)
    except requests.HTTPError:
        password_used = DEFAULT_PASSWORD
        token = _login(DEFAULT_PASSWORD)

    headers = {"X-SQLBOT-TOKEN": f"Bearer {token}"}

    if password_used == DEFAULT_PASSWORD:
        _unwrap(
            requests.put(
                f"{BASE_URL}/api/v1/user/pwd",
                json={"pwd": DEFAULT_PASSWORD, "new_pwd": configured_password},
                headers=headers,
                timeout=20,
            )
        )

    datasource_name = "应收分析只读库"
    datasources = _unwrap(
        requests.get(f"{BASE_URL}/api/v1/datasource/list", headers=headers, timeout=20)
    )
    datasource = next((item for item in datasources if item.get("name") == datasource_name), None)
    if not datasource:
        configuration = _aes_encrypt(
            {
                "host": optional_env("SQLBOT_DB_HOST", "host.docker.internal"),
                "port": 5432,
                "username": optional_env("SQLBOT_DB_USER", "sqlbot_reader"),
                "password": require_env("SQLBOT_DB_PASSWORD"),
                "database": optional_env("RECEIVABLE_DB_NAME", "yongyou_receivables"),
                "extraJdbc": "",
                "dbSchema": "receivable_analytics",
                "filename": "",
                "sheets": [],
                "mode": "service_name",
                "timeout": 30,
                "lowVersion": False,
                "ssl": False,
            }
        )
        base_payload = {
            "name": datasource_name,
            "description": "与应收工作台同口径的只读发票、合同和客户账龄事实",
            "type": "pg",
            "configuration": configuration,
            "recommended_config": 1,
        }
        connected = _unwrap(
            requests.post(
                f"{BASE_URL}/api/v1/datasource/check",
                json=base_payload,
                headers=headers,
                timeout=30,
            )
        )
        if not connected:
            raise RuntimeError("SQLBot 无法连接应收 PostgreSQL")
        tables = _unwrap(
            requests.post(
                f"{BASE_URL}/api/v1/datasource/getTablesByConf",
                json=base_payload,
                headers=headers,
                timeout=30,
            )
        )
        allowed = {
            "invoice_facts",
            "contract_receivable_summary",
            "customer_aging_summary",
        }
        base_payload["tables"] = [
            {
                "table_name": table["tableName"],
                "table_comment": table.get("tableComment") or "",
                "checked": True,
            }
            for table in tables
            if table["tableName"] in allowed
        ]
        datasource = _unwrap(
            requests.post(
                f"{BASE_URL}/api/v1/datasource/add",
                json=base_payload,
                headers=headers,
                timeout=60,
            )
        )
    datasource_id = int(datasource["id"])

    recommended_questions = [
        "当前真实逾期金额最高的 10 个客户是谁？",
        "未来 7 天有哪些发票到期？",
        "各客户的逾期账龄金额是多少？",
        "哪些合同尚有未收金额？",
        "当前已收金额和未收金额分别是多少？",
        "哪些发票尚未匹配到销售合同？",
        "哪些发票缺少审核时间？",
        "真实逾期金额最高的 10 份合同是什么？",
        "哪些发票已部分回款但仍然逾期？",
        "每位销售负责人名下的真实逾期金额是多少？",
    ]
    now = datetime.now().isoformat()
    _unwrap(
        requests.post(
            f"{BASE_URL}/api/v1/recommended_problem/save_recommended_problem",
            json={
                "datasource_id": datasource_id,
                "recommended_config": 1,
                "problemInfo": [
                    {
                        "id": 0,
                        "datasource_id": datasource_id,
                        "question": question,
                        "remark": "",
                        "sort": index,
                        "create_time": now,
                        "create_by": 1,
                    }
                    for index, question in enumerate(recommended_questions, start=1)
                ],
            },
            headers=headers,
            timeout=30,
        )
    )

    training_examples = [
        (
            recommended_questions[0],
            "SELECT customer, SUM(outstanding) AS overdue_amount "
            "FROM invoice_facts WHERE true_status = 'true_overdue' "
            "GROUP BY customer ORDER BY overdue_amount DESC LIMIT 10",
        ),
        (
            recommended_questions[1],
            "SELECT invoice_code, customer, due_date, outstanding "
            "FROM invoice_facts WHERE due_date BETWEEN CURRENT_DATE "
            "AND CURRENT_DATE + INTERVAL '7 days' AND true_status <> 'settled' "
            "ORDER BY due_date",
        ),
        (
            recommended_questions[2],
            "SELECT customer, aging_bucket, outstanding "
            "FROM customer_aging_summary ORDER BY customer, aging_bucket",
        ),
        (
            recommended_questions[3],
            "SELECT contract_code, customer, outstanding "
            "FROM contract_receivable_summary WHERE outstanding > 0 "
            "ORDER BY outstanding DESC",
        ),
        (
            recommended_questions[4],
            "SELECT SUM(collected_amount) AS collected_amount, "
            "SUM(outstanding) AS outstanding FROM invoice_facts",
        ),
        (
            recommended_questions[5],
            "SELECT invoice_code, customer, tax_amount FROM invoice_facts "
            "WHERE true_status = 'unmatched' ORDER BY tax_amount DESC",
        ),
        (
            recommended_questions[6],
            "SELECT invoice_code, customer, tax_amount FROM invoice_facts "
            "WHERE true_status = 'pending_audit' ORDER BY invoice_code",
        ),
        (
            recommended_questions[7],
            "SELECT contract_code, customer, true_overdue_amount "
            "FROM contract_receivable_summary WHERE true_overdue_amount > 0 "
            "ORDER BY true_overdue_amount DESC LIMIT 10",
        ),
        (
            recommended_questions[8],
            "SELECT invoice_code, customer, collected_amount, outstanding "
            "FROM invoice_facts WHERE true_status = 'true_overdue' "
            "AND collection_status = 'partial' ORDER BY outstanding DESC",
        ),
        (
            recommended_questions[9],
            "SELECT salesman, SUM(outstanding) AS overdue_amount "
            "FROM invoice_facts WHERE true_status = 'true_overdue' "
            "GROUP BY salesman ORDER BY overdue_amount DESC",
        ),
    ]
    existing_training = _unwrap(
        requests.get(
            f"{BASE_URL}/api/v1/system/data-training/page/1/100",
            headers=headers,
            timeout=30,
        )
    )
    existing_questions = {
        item.get("question")
        for item in existing_training.get("data", existing_training.get("items", []))
    }
    for question, statement in training_examples:
        if question in existing_questions:
            continue
        _unwrap(
            requests.put(
                f"{BASE_URL}/api/v1/system/data-training",
                json={
                    "datasource": datasource_id,
                    "datasource_name": datasource_name,
                    "question": question,
                    "description": statement,
                    "enabled": True,
                },
                headers=headers,
                timeout=30,
            )
        )

    account = optional_env("SQLBOT_EMBED_ACCOUNT", "receivables-internal")
    users = _unwrap(
        requests.get(
            f"{BASE_URL}/api/v1/user/pager/1/100",
            headers=headers,
            timeout=20,
        )
    )
    if not any(item.get("account") == account for item in users.get("items", [])):
        _unwrap(
            requests.post(
                f"{BASE_URL}/api/v1/user",
                json={
                    "account": account,
                    "oid": 1,
                    "oid_list": [1],
                    "name": "应收智能问数",
                    "email": "receivables-internal@localhost.local",
                    "status": 1,
                    "origin": 0,
                    "system_variables": [],
                },
                headers=headers,
                timeout=20,
            )
        )

    applications = _unwrap(
        requests.get(
            f"{BASE_URL}/api/v1/system/embedded/1/100",
            params={"keyword": "应收智能问数"},
            headers=headers,
            timeout=20,
        )
    )
    application = next(
        (item for item in applications.get("items", []) if item.get("name") == "应收智能问数"),
        None,
    )
    if not application:
        application = _unwrap(
            requests.post(
                f"{BASE_URL}/api/v1/system/embedded",
                json={
                    "name": "应收智能问数",
                    "domain": optional_env(
                        "SQLBOT_EMBED_ALLOWED_ORIGINS",
                        "http://localhost:5173,http://127.0.0.1:5173",
                    ),
                    "type": 4,
                    "description": "应收交付版页面嵌入应用",
                    "configuration": json.dumps(
                        {"datasource_id": datasource_id},
                        ensure_ascii=False,
                    ),
                    "oid": 1,
                },
                headers=headers,
                timeout=20,
            )
        )

    _save_env(
        {
            "SQLBOT_BASE_URL": optional_env("SQLBOT_EMBED_BASE_URL", BASE_URL),
            "SQLBOT_EMBEDDED_ID": str(application["id"]),
            "SQLBOT_APP_ID": str(application["app_id"]),
            "SQLBOT_APP_SECRET": str(application["app_secret"]),
            "SQLBOT_EMBED_ACCOUNT": account,
        }
    )
    print(
        "SQLBot 已完成：管理员密码更新、只读数据源、内部账号与嵌入应用配置；"
        "百炼 API Key 仍需在 SQLBot 管理端填写。"
    )


if __name__ == "__main__":
    main()
