from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "yongyou-receivables"

BACKEND_FILES = (
    "backend/__init__.py",
    "backend/app_factory.py",
    "backend/config.py",
    "backend/date_ranges.py",
    "backend/main.py",
    "backend/scheduler.py",
    "backend/value_utils.py",
    "backend/auth/__init__.py",
    "backend/auth/session.py",
    "backend/api/__init__.py",
    "backend/api/auth.py",
    "backend/api/notifications.py",
    "backend/api/receivables.py",
    "backend/api/sqlbot.py",
    "backend/clients/__init__.py",
    "backend/clients/dingtalk/auth_api.py",
    "backend/clients/dingtalk/contact_api.py",
    "backend/clients/dingtalk/message_api.py",
    "backend/clients/dingtalk/openapi_client.py",
    "backend/clients/yonyou/__init__.py",
    "backend/clients/yonyou/client.py",
    "backend/clients/yonyou/finance.py",
    "backend/clients/yonyou/pagination.py",
    "backend/clients/yonyou/sales.py",
    "backend/db/__init__.py",
    "backend/db/contact_cache_store.py",
    "backend/db/migrations/001_receivables.sql",
    "backend/db/migrations/002_analytics_semantics.sql",
    "backend/db/notification_task_store.py",
    "backend/db/receivable_store.py",
    "backend/services/__init__.py",
    "backend/services/collection_sync_service.py",
    "backend/services/overdue_service.py",
    "backend/services/receivable_match_service.py",
    "backend/services/receivable_notify_service.py",
    "backend/services/receivable_sync_service.py",
    "infra/sqlbot/compose.yml",
    "infra/sqlbot/README.md",
    "scripts/configure_local_postgres_env.py",
    "scripts/configure_sqlbot.py",
    "scripts/migrate_receivables_sqlite.py",
    "scripts/setup_local_postgres.py",
    "scripts/verify_postgres_sqlbot.py",
    "Makefile",
    "README.md",
)

FORBIDDEN_PARTS = ("payroll", "ontology", "bi_service", "Dashboard")


def _copy(relative_path: str, destination: Path) -> None:
    source = ROOT / relative_path
    target = destination / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main() -> None:
    subprocess.run(["npm", "run", "build:product"], cwd=ROOT / "frontend", check=True)
    OUTPUT.parent.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(dir=OUTPUT.parent) as temp_dir:
        stage = Path(temp_dir) / OUTPUT.name
        for relative_path in BACKEND_FILES:
            _copy(relative_path, stage)
        _copy("backend/requirements.txt", stage)
        shutil.copy2(ROOT / ".env.product.example", stage / ".env.example")
        shutil.copytree(ROOT / "frontend" / "dist", stage / "frontend" / "dist")

        found = [
            str(path.relative_to(stage))
            for path in stage.rglob("*")
            if any(part.lower() in str(path.relative_to(stage)).lower() for part in FORBIDDEN_PARTS)
        ]
        if found:
            raise RuntimeError(f"交付物包含实验功能：{', '.join(found)}")

        if OUTPUT.exists():
            shutil.rmtree(OUTPUT)
        shutil.copytree(stage, OUTPUT)

    archive = shutil.make_archive(str(OUTPUT), "zip", root_dir=OUTPUT)
    print(f"交付包已生成：{archive}")


if __name__ == "__main__":
    main()
