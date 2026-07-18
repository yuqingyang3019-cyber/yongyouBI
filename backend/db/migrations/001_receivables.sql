CREATE SCHEMA IF NOT EXISTS receivable_raw;
CREATE SCHEMA IF NOT EXISTS receivable_analytics;

CREATE TABLE IF NOT EXISTS receivable_raw.sync_meta (
    month_key TEXT PRIMARY KEY,
    last_synced_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    last_error TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS receivable_raw.sale_invoices (
    invoice_id TEXT PRIMARY KEY,
    month_key TEXT NOT NULL,
    list_ts TEXT NOT NULL DEFAULT '',
    payload_json JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sale_invoices_month
    ON receivable_raw.sale_invoices(month_key);

CREATE TABLE IF NOT EXISTS receivable_raw.sale_contracts (
    contract_id TEXT PRIMARY KEY,
    month_key TEXT NOT NULL,
    list_ts TEXT NOT NULL DEFAULT '',
    payload_json JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sale_contracts_month
    ON receivable_raw.sale_contracts(month_key);

CREATE TABLE IF NOT EXISTS receivable_raw.collections (
    collection_id TEXT PRIMARY KEY,
    month_key TEXT NOT NULL,
    list_ts TEXT NOT NULL DEFAULT '',
    payload_json JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_collections_month
    ON receivable_raw.collections(month_key);

CREATE TABLE IF NOT EXISTS receivable_analytics.invoice_facts (
    invoice_id TEXT PRIMARY KEY,
    invoice_code TEXT NOT NULL DEFAULT '',
    contract_code TEXT NOT NULL DEFAULT '',
    customer TEXT NOT NULL DEFAULT '',
    salesman TEXT NOT NULL DEFAULT '',
    tax_amount NUMERIC(18, 2) NOT NULL DEFAULT 0,
    collected_amount NUMERIC(18, 2) NOT NULL DEFAULT 0,
    outstanding NUMERIC(18, 2) NOT NULL DEFAULT 0,
    collection_status TEXT NOT NULL,
    match_quality TEXT NOT NULL,
    audit_time TIMESTAMPTZ,
    payment_term_days INTEGER NOT NULL DEFAULT 0,
    due_date DATE,
    days_until_due INTEGER NOT NULL DEFAULT 0,
    calendar_status TEXT NOT NULL,
    true_status TEXT NOT NULL,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_invoice_facts_true_status
    ON receivable_analytics.invoice_facts(true_status);
CREATE INDEX IF NOT EXISTS idx_invoice_facts_customer
    ON receivable_analytics.invoice_facts(customer);
CREATE INDEX IF NOT EXISTS idx_invoice_facts_due_date
    ON receivable_analytics.invoice_facts(due_date);

COMMENT ON TABLE receivable_analytics.invoice_facts IS '发票级应收事实，金额口径与应收逾期工作台一致';
COMMENT ON COLUMN receivable_analytics.invoice_facts.tax_amount IS '发票含税应收金额';
COMMENT ON COLUMN receivable_analytics.invoice_facts.collected_amount IS '已匹配收款金额';
COMMENT ON COLUMN receivable_analytics.invoice_facts.outstanding IS '未收金额';
COMMENT ON COLUMN receivable_analytics.invoice_facts.true_status IS '真实应收状态：true_overdue、upcoming、normal、settled、pending_audit、unmatched';

CREATE OR REPLACE VIEW receivable_analytics.contract_receivable_summary AS
SELECT
    contract_code,
    MAX(customer) AS customer,
    SUM(tax_amount)::NUMERIC(18, 2) AS receivable_amount,
    SUM(collected_amount)::NUMERIC(18, 2) AS collected_amount,
    SUM(outstanding)::NUMERIC(18, 2) AS outstanding,
    SUM(outstanding) FILTER (WHERE true_status = 'true_overdue')::NUMERIC(18, 2) AS true_overdue_amount,
    COUNT(*)::INTEGER AS invoice_count,
    COUNT(*) FILTER (WHERE true_status = 'true_overdue')::INTEGER AS true_overdue_count
FROM receivable_analytics.invoice_facts
WHERE contract_code <> ''
GROUP BY contract_code;

COMMENT ON VIEW receivable_analytics.contract_receivable_summary IS '合同级应收、已收、未收与真实逾期汇总';

CREATE OR REPLACE VIEW receivable_analytics.customer_aging_summary AS
SELECT
    customer,
    CASE
        WHEN true_status <> 'true_overdue' THEN '未逾期'
        WHEN -days_until_due BETWEEN 1 AND 7 THEN '逾期1-7天'
        WHEN -days_until_due BETWEEN 8 AND 30 THEN '逾期8-30天'
        WHEN -days_until_due BETWEEN 31 AND 90 THEN '逾期31-90天'
        ELSE '逾期90天以上'
    END AS aging_bucket,
    COUNT(*)::INTEGER AS invoice_count,
    SUM(outstanding)::NUMERIC(18, 2) AS outstanding
FROM receivable_analytics.invoice_facts
WHERE true_status NOT IN ('settled', 'pending_audit', 'unmatched')
GROUP BY customer, aging_bucket;

COMMENT ON VIEW receivable_analytics.customer_aging_summary IS '客户维度账龄与未收金额汇总';
