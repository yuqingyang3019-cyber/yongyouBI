from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import load_env_file


MIGRATIONS_DIR = ROOT / "backend" / "db" / "migrations"
load_env_file()


def required(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"请先设置环境变量 {name}")
    return value


def ensure_role(conn: psycopg.Connection, role: str, password: str) -> None:
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
    if exists:
        conn.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(role),
                sql.Literal(password),
            )
        )
    else:
        conn.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role),
                sql.Literal(password),
            )
        )


def main() -> None:
    admin_url = os.getenv("POSTGRES_ADMIN_URL", "postgresql:///postgres")
    database = os.getenv("RECEIVABLE_DB_NAME", "yongyou_receivables")
    app_user = os.getenv("RECEIVABLE_DB_USER", "yongyou_app")
    reader_user = os.getenv("SQLBOT_DB_USER", "sqlbot_reader")
    app_password = required("RECEIVABLE_DB_PASSWORD")
    reader_password = required("SQLBOT_DB_PASSWORD")

    with psycopg.connect(admin_url, autocommit=True) as conn:
        ensure_role(conn, app_user, app_password)
        ensure_role(conn, reader_user, reader_password)
        for name in (database, f"{database}_test"):
            exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
            if not exists:
                conn.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(name),
                        sql.Identifier(app_user),
                    )
                )

    for name in (database, f"{database}_test"):
        target_admin_url = f"postgresql:///{name}"
        with psycopg.connect(target_admin_url, autocommit=True) as conn:
            conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(app_user)))
            for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
                conn.execute(migration.read_text(encoding="utf-8"))
            conn.execute("RESET ROLE")
            if name != database:
                continue
            conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database),
                sql.Identifier(reader_user),
            ))
            conn.execute(sql.SQL("REVOKE ALL ON SCHEMA receivable_raw FROM {}").format(
                sql.Identifier(reader_user)
            ))
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA receivable_analytics TO {}").format(
                sql.Identifier(reader_user)
            ))
            conn.execute(
                sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA receivable_analytics TO {}").format(
                    sql.Identifier(reader_user)
                )
            )
            conn.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA receivable_analytics "
                    "GRANT SELECT ON TABLES TO {}"
                ).format(sql.Identifier(app_user), sql.Identifier(reader_user))
            )

    print(f"PostgreSQL 已初始化：database={database}, app_user={app_user}, reader={reader_user}")


if __name__ == "__main__":
    main()
