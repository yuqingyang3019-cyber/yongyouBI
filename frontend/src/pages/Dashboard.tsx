import { useEffect, useMemo, useState } from "react";

import { ExecutionChart } from "../components/ExecutionChart";
import { KpiCard } from "../components/KpiCard";
import { fetchExecutionSummary } from "../services/api";
import type { ExecutionSummary } from "../types";

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0
  }).format(value);
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

function formatGeneratedAt(value: number | string): string {
  if (typeof value === "number") {
    const dt = new Date(value * 1000);
    if (!Number.isNaN(dt.getTime())) {
      return dt.toLocaleString("zh-CN");
    }
  }
  return String(value);
}

export function Dashboard() {
  const [month, setMonth] = useState(currentMonth());
  const [selectedDocTypes, setSelectedDocTypes] = useState<string[]>([]);
  const [selectedPersons, setSelectedPersons] = useState<string[]>([]);
  const [personInput, setPersonInput] = useState("");
  const [personMatchMode, setPersonMatchMode] = useState<"contains" | "exact">("contains");
  const [summary, setSummary] = useState<ExecutionSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  function loadData(forceRefresh = false) {
    setLoading(true);
    setError("");
    fetchExecutionSummary(month, selectedDocTypes, selectedPersons, personMatchMode, 10, forceRefresh)
      .then((data) => setSummary(data))
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : "数据加载失败"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    setError("");
    fetchExecutionSummary(month, selectedDocTypes, selectedPersons, personMatchMode, 10, false)
      .then((data) => {
        if (!ignore) {
          setSummary(data);
        }
      })
      .catch((exc: unknown) => {
        if (!ignore) {
          setError(exc instanceof Error ? exc.message : "数据加载失败");
        }
      })
      .finally(() => {
        if (!ignore) {
          setLoading(false);
        }
      });
    return () => {
      ignore = true;
    };
    // 首次加载一次，后续由按钮触发
  }, []);

  const topPeople = useMemo(() => summary?.byPersonTopN ?? [], [summary]);
  const topSuppliers = useMemo(() => summary?.bySupplierTopN ?? [], [summary]);
  const topOrgs = useMemo(() => summary?.byOrgTopN ?? [], [summary]);
  const lifecycle = useMemo(() => summary?.lifecycle ?? [], [summary]);
  const docErrors = useMemo(() => (summary?.byDocumentType ?? []).filter((item) => item.error), [summary]);
  const selectedOrAllTypes = selectedDocTypes.length
    ? selectedDocTypes
    : (summary?.availableDocumentTypes ?? []).map((item) => item.type);

  const stackedSeries = useMemo(() => {
    if (!summary) {
      return [];
    }
    return selectedOrAllTypes.map((type) => {
      const option = summary.availableDocumentTypes.find((item) => item.type === type);
      return {
        name: option?.label ?? type,
        values: topPeople.map((person) => {
          const hit = summary.matrix.find((item) => item.person === person.person && item.type === type);
          return hit?.amount ?? 0;
        })
      };
    });
  }, [selectedOrAllTypes, summary, topPeople]);

  function toggleDocType(type: string) {
    if (!summary) {
      return;
    }
    const allTypes = summary.availableDocumentTypes.map((item) => item.type);
    const base = selectedDocTypes.length ? selectedDocTypes : allTypes;
    const next = base.includes(type) ? base.filter((item) => item !== type) : [...base, type];
    setSelectedDocTypes(next.length === allTypes.length ? [] : next);
  }

  function togglePerson(person: string) {
    const base = selectedPersons;
    const next = base.includes(person) ? base.filter((item) => item !== person) : [...base, person];
    setSelectedPersons(next);
  }

  function applyPersonInput() {
    const values = personInput
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (values.length === 0) {
      return;
    }
    setSelectedPersons((prev) => Array.from(new Set([...prev, ...values])));
    setPersonInput("");
  }

  return (
    <main className="dashboard">
      <header className="hero">
        <div>
          <p className="eyebrow">YonBIP BI</p>
          <h1>采购经营驾驶舱</h1>
          <p>从公司、组长、个人三个角度观察采购合同、订单、到货、发票和付款申请。</p>
        </div>
        <label className="month-picker">
          统计月份
          <input type="month" value={month} onChange={(event) => setMonth(event.target.value)} />
          {summary?.meta ? (
            <small>{summary.meta.fromCache ? "缓存结果" : "实时结果"} · {formatGeneratedAt(summary.meta.generatedAt)}</small>
          ) : null}
        </label>
      </header>

      {summary ? (
        <section className="filter-card">
          <span>单据类型</span>
          <div className="chips">
            {summary.availableDocumentTypes.map((item) => (
              <label className="chip" key={item.type}>
                <input
                  checked={selectedDocTypes.length === 0 || selectedDocTypes.includes(item.type)}
                  type="checkbox"
                  onChange={() => toggleDocType(item.type)}
                />
                {item.label}
              </label>
            ))}
          </div>
          <span>执行人</span>
          <div className="chips">
            {(summary.availablePeople ?? []).slice(0, 12).map((person) => (
              <label className="chip" key={person}>
                <input checked={selectedPersons.includes(person)} type="checkbox" onChange={() => togglePerson(person)} />
                {person}
              </label>
            ))}
          </div>
          <label className="person-input">
            <input
              placeholder="输入执行人，逗号分隔"
              value={personInput}
              onChange={(event) => setPersonInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  applyPersonInput();
                }
              }}
            />
            <button onClick={applyPersonInput} type="button">
              添加
            </button>
          </label>
          <label className="match-mode">
            匹配
            <select value={personMatchMode} onChange={(event) => setPersonMatchMode(event.target.value as "contains" | "exact")}>
              <option value="contains">模糊</option>
              <option value="exact">精确</option>
            </select>
          </label>
          {selectedPersons.length > 0 ? (
            <button className="link-button" onClick={() => setSelectedPersons([])} type="button">
              清空执行人筛选
            </button>
          ) : null}
          <button className="link-button" disabled={loading} onClick={() => loadData(false)} type="button">
            查询
          </button>
          <button className="link-button" disabled={loading} onClick={() => loadData(true)} type="button">
            刷新
          </button>
        </section>
      ) : null}

      {error ? <div className="alert error">{error}</div> : null}
      {docErrors.map((item) => (
        <div className="alert warning" key={item.type}>
          {item.label} 加载失败：{item.error}
        </div>
      ))}

      <section className="kpi-grid">
        <KpiCard label="链路单据数" value={formatNumber(summary?.totals.count ?? 0)} hint={loading ? "加载中" : "五类单据去重后计数"} />
        <KpiCard label="链路金额" value={formatMoney(summary?.totals.amount ?? 0)} hint="合同、订单、到货、发票、付款申请合计" />
        <KpiCard label="供应商数" value={formatNumber(summary?.bySupplier.length ?? 0)} hint="按供应商名称归集" />
        <KpiCard label="执行人数量" value={formatNumber(summary?.byPerson.length ?? 0)} hint="组长视角的人员覆盖" />
        <KpiCard
          label="到货覆盖订单"
          value={formatPercent(summary?.coverage.arrivalVsOrderAmount ?? 0)}
          hint="到货金额 / 订单金额"
        />
        <KpiCard
          label="发票覆盖订单"
          value={formatPercent(summary?.coverage.invoiceVsOrderAmount ?? 0)}
          hint="发票金额 / 订单金额"
        />
        <KpiCard
          label="付款申请覆盖"
          value={formatPercent(summary?.coverage.paymentApplyVsOrderAmount ?? 0)}
          hint="付款申请金额 / 订单金额"
        />
        <KpiCard
          label="数据待补齐"
          value={formatNumber((summary?.totals.missingPersonCount ?? 0) + (summary?.totals.missingSupplierCount ?? 0))}
          hint="执行人或供应商缺失"
        />
      </section>

      <section className="insight-grid">
        <div className="insight-panel wide">
          <div className="panel-heading">
            <span>公司视角</span>
            <strong>采购链路金额流向</strong>
          </div>
          <div className="lifecycle-row">
            {lifecycle.map((item) => (
              <article className="lifecycle-card" key={item.type}>
                <small>{item.label}</small>
                <strong>{formatMoney(item.amount)}</strong>
                <span>{formatNumber(item.count)} 单</span>
              </article>
            ))}
          </div>
        </div>
        <div className="insight-panel">
          <div className="panel-heading">
            <span>采购组长视角</span>
            <strong>重点供应商</strong>
          </div>
          <ol className="rank-list">
            {topSuppliers.slice(0, 6).map((item) => (
              <li key={item.supplier}>
                <span>{item.supplier}</span>
                <strong>{formatMoney(item.amount)}</strong>
              </li>
            ))}
          </ol>
        </div>
        <div className="insight-panel">
          <div className="panel-heading">
            <span>组织视角</span>
            <strong>组织金额分布</strong>
          </div>
          <ol className="rank-list">
            {topOrgs.slice(0, 6).map((item) => (
              <li key={item.org}>
                <span>{item.org}</span>
                <strong>{formatMoney(item.amount)}</strong>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="chart-grid">
        <ExecutionChart
          categories={topPeople.map((item) => item.person)}
          kind="horizontalBar"
          series={[{ name: "执行金额", values: topPeople.map((item) => item.amount) }]}
          title="按执行人统计金额 Top 10"
        />
        <ExecutionChart
          categories={topPeople.map((item) => item.person)}
          series={[{ name: "执行数量", values: topPeople.map((item) => item.count) }]}
          title="按执行人统计数量 Top 10"
          valueLabel="单"
        />
        <ExecutionChart
          categories={topPeople.map((item) => item.person)}
          kind="stackedBar"
          series={stackedSeries}
          title="执行人 × 单据类型金额"
        />
        <ExecutionChart
          categories={lifecycle.map((item) => item.label)}
          series={[{ name: "链路金额", values: lifecycle.map((item) => item.amount) }]}
          title="公司视角：五类单据金额"
        />
        <ExecutionChart
          categories={topSuppliers.map((item) => item.supplier)}
          kind="horizontalBar"
          series={[{ name: "供应商金额", values: topSuppliers.map((item) => item.amount) }]}
          title="采购组长视角：供应商 Top 10"
        />
        <ExecutionChart
          categories={topOrgs.map((item) => item.org)}
          kind="horizontalBar"
          series={[{ name: "组织金额", values: topOrgs.map((item) => item.amount) }]}
          title="公司视角：组织金额 Top 10"
        />
      </section>
    </main>
  );
}
