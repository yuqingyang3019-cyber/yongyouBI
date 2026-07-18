from __future__ import annotations

import sys
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import load_env_file, require_env
from backend.db.receivable_store import ReceivableCacheStore
from backend.services.overdue_service import contract_overdue


load_env_file()

BENCHMARK_SQL = (
    """
    SELECT customer, SUM(outstanding) AS amount
    FROM receivable_analytics.invoice_facts
    WHERE true_status = 'true_overdue'
    GROUP BY customer ORDER BY amount DESC LIMIT 10
    """,
    """
    SELECT invoice_code, customer, due_date, outstanding
    FROM receivable_analytics.invoice_facts
    WHERE due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'
      AND true_status <> 'settled'
    ORDER BY due_date
    """,
    "SELECT * FROM receivable_analytics.customer_aging_summary ORDER BY customer, aging_bucket",
    """
    SELECT * FROM receivable_analytics.contract_receivable_summary
    WHERE outstanding > 0 ORDER BY outstanding DESC
    """,
    """
    SELECT SUM(collected_amount), SUM(outstanding)
    FROM receivable_analytics.invoice_facts
    """,
    """
    SELECT invoice_code, customer, tax_amount
    FROM receivable_analytics.invoice_facts WHERE true_status = 'unmatched'
    """,
    """
    SELECT invoice_code, customer, tax_amount
    FROM receivable_analytics.invoice_facts WHERE true_status = 'pending_audit'
    """,
    """
    SELECT contract_code, customer, true_overdue_amount
    FROM receivable_analytics.contract_receivable_summary
    WHERE true_overdue_amount > 0 ORDER BY true_overdue_amount DESC LIMIT 10
    """,
    """
    SELECT invoice_code, customer, collected_amount, outstanding
    FROM receivable_analytics.invoice_facts
    WHERE true_status = 'true_overdue' AND collection_status = 'partial'
    """,
    """
    SELECT salesman, SUM(outstanding) AS amount
    FROM receivable_analytics.invoice_facts
    WHERE true_status = 'true_overdue'
    GROUP BY salesman ORDER BY amount DESC
    """,
)


def _must_be_denied(database_url: str, statement: str) -> None:
    try:
        with psycopg.connect(database_url) as conn:
            conn.execute(statement)
    except psycopg.errors.InsufficientPrivilege:
        return
    raise RuntimeError(f"只读权限校验失败，语句意外成功：{statement}")


def main() -> None:
    store = ReceivableCacheStore(require_env("RECEIVABLE_DATABASE_URL"))
    try:
        workbench = contract_overdue(kick=False, store=store)
    finally:
        store.close()

    reader_url = require_env("SQLBOT_DATABASE_URL")
    with psycopg.connect(reader_url) as conn:
        results = [conn.execute(statement).fetchall() for statement in BENCHMARK_SQL]
        fact_count = conn.execute(
            "SELECT COUNT(*) FROM receivable_analytics.invoice_facts"
        ).fetchone()[0]
        overdue_amount = conn.execute(
            """
            SELECT COALESCE(SUM(outstanding), 0)
            FROM receivable_analytics.invoice_facts
            WHERE true_status = 'true_overdue'
            """
        ).fetchone()[0]

    expected_count = workbench["meta"]["cachedInvoiceCount"]
    expected_amount = workbench["summary"]["trueOverdue"]["amount"]
    if fact_count != expected_count:
        raise RuntimeError(f"事实数量不一致：facts={fact_count}, workbench={expected_count}")
    if round(float(overdue_amount), 2) != round(float(expected_amount), 2):
        raise RuntimeError(
            f"真实逾期金额不一致：facts={overdue_amount}, workbench={expected_amount}"
        )
    if not results[0] and expected_amount:
        raise RuntimeError("逾期 Top 客户基准问题未返回数据")

    _must_be_denied(reader_url, "SELECT * FROM receivable_raw.sale_invoices LIMIT 1")
    _must_be_denied(reader_url, "DELETE FROM receivable_analytics.invoice_facts")
    print(
        f"验证通过：事实 {fact_count} 条，真实逾期 {float(overdue_amount):.2f}，"
        f"10 个基准 SQL 均可执行，raw 与写权限均被拒绝。"
    )


if __name__ == "__main__":
    main()
