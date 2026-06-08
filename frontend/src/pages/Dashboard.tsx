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

export function Dashboard() {
  const [month, setMonth] = useState(currentMonth());
  const [selectedDocTypes, setSelectedDocTypes] = useState<string[]>([]);
  const [summary, setSummary] = useState<ExecutionSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    setError("");
    fetchExecutionSummary(month, selectedDocTypes)
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
  }, [month, selectedDocTypes]);

  const topPeople = useMemo(() => (summary?.byPerson ?? []).slice(0, 10), [summary]);
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

  return (
    <main className="dashboard">
      <header className="hero">
        <div>
          <p className="eyebrow">YonBIP BI</p>
          <h1>采购执行统计</h1>
          <p>按月汇总采购合同、采购订单、付款申请单的执行数量与金额。</p>
        </div>
        <label className="month-picker">
          统计月份
          <input type="month" value={month} onChange={(event) => setMonth(event.target.value)} />
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
        </section>
      ) : null}

      {error ? <div className="alert error">{error}</div> : null}
      {docErrors.map((item) => (
        <div className="alert warning" key={item.type}>
          {item.label} 加载失败：{item.error}
        </div>
      ))}

      <section className="kpi-grid">
        <KpiCard label="执行数量" value={formatNumber(summary?.totals.count ?? 0)} hint={loading ? "加载中" : "单据去重后计数"} />
        <KpiCard label="执行金额" value={formatMoney(summary?.totals.amount ?? 0)} hint="按各单据含税金额优先统计" />
        <KpiCard label="执行人数量" value={formatNumber(summary?.byPerson.length ?? 0)} hint="包含未分配" />
        <KpiCard
          label="缺失人员"
          value={formatNumber(summary?.totals.missingPersonCount ?? 0)}
          hint="人员字段为空的单据"
        />
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
          categories={(summary?.byDocumentType ?? []).map((item) => item.label)}
          series={[{ name: "执行金额", values: (summary?.byDocumentType ?? []).map((item) => item.amount) }]}
          title="单据类型金额概览"
        />
      </section>
    </main>
  );
}
