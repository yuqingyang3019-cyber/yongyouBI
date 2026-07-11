import { useEffect, useMemo, useRef, useState } from "react";

import { AttachmentDrawer, OverdueTable } from "../components/OverdueTable";
import { KpiCard } from "../components/KpiCard";
import {
  fetchContractOverdue,
  fetchContractOverdueSyncStatus,
  triggerContractOverdueSync
} from "../services/api";
import type { ContractOverdueResult, ContractOverdueRow, ContractSyncStatus } from "../types";

function formatMoney(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0
  }).format(value);
}

type UnpaidStatus = "overdue" | "upcoming" | "normal";

const STATUS_OPTIONS: Array<{ value: UnpaidStatus; label: string }> = [
  { value: "overdue", label: "已逾期" },
  { value: "upcoming", label: "即将逾期" },
  { value: "normal", label: "正常未付" }
];

export function ContractOverdue() {
  const [statuses, setStatuses] = useState<UnpaidStatus[]>(["overdue", "upcoming", "normal"]);
  const [data, setData] = useState<ContractOverdueResult | null>(null);
  const [syncStatus, setSyncStatus] = useState<ContractSyncStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedRow, setSelectedRow] = useState<ContractOverdueRow | null>(null);
  const updatedAtRef = useRef("");

  function loadOverdue(nextStatuses = statuses, withSync = true) {
    setLoading(true);
    setError("");
    return fetchContractOverdue(nextStatuses, withSync)
      .then((result) => {
        setData(result);
        setSyncStatus(result.meta.sync);
        updatedAtRef.current = result.meta.updatedAt || result.meta.sync.updatedAt || "";
      })
      .catch((exc: unknown) => {
        setError(exc instanceof Error ? exc.message : "数据加载失败");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    setError("");
    fetchContractOverdue(statuses, true)
      .then((result) => {
        if (ignore) {
          return;
        }
        setData(result);
        setSyncStatus(result.meta.sync);
        updatedAtRef.current = result.meta.updatedAt || result.meta.sync.updatedAt || "";
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
  }, [statuses]);

  useEffect(() => {
    let ignore = false;
    const timer = window.setInterval(() => {
      fetchContractOverdueSyncStatus()
        .then((status) => {
          if (ignore) {
            return;
          }
          setSyncStatus(status);
          const nextUpdated = status.updatedAt || "";
          if (nextUpdated && nextUpdated !== updatedAtRef.current) {
            updatedAtRef.current = nextUpdated;
            fetchContractOverdue(statuses, false)
              .then((result) => {
                if (!ignore) {
                  setData(result);
                }
              })
              .catch(() => undefined);
          }
        })
        .catch(() => undefined);
    }, 2000);
    return () => {
      ignore = true;
      window.clearInterval(timer);
    };
  }, [statuses]);

  const syncHint = useMemo(() => {
    if (!syncStatus) {
      return "";
    }
    if (syncStatus.status === "running") {
      return `后台同步近12个月合同…已更新 ${syncStatus.doneCount} 份，待同步 ${syncStatus.pending} 份`;
    }
    if (syncStatus.status === "error") {
      return `同步失败：${syncStatus.error || "未知错误"}`;
    }
    if (data?.meta.emptyCache) {
      return "本地暂无缓存，正在等待首次同步结果";
    }
    if (syncStatus.lastSyncedAt) {
      return `上次同步 ${syncStatus.lastSyncedAt} · 本地合同 ${syncStatus.cachedCount} 份`;
    }
    return `本地合同 ${syncStatus.cachedCount} 份 · 近12个月`;
  }, [data?.meta.emptyCache, syncStatus]);

  function toggleStatus(value: UnpaidStatus) {
    setStatuses((prev) => {
      if (prev.includes(value)) {
        const next = prev.filter((item) => item !== value);
        return next.length ? next : prev;
      }
      return [...prev, value];
    });
  }

  function handleSyncNow() {
    triggerContractOverdueSync()
      .then((status) => setSyncStatus(status))
      .catch((exc: unknown) => setError(exc instanceof Error ? exc.message : "触发同步失败"));
  }

  const paidCount = data?.meta.paidRowCount ?? data?.paidRows?.length ?? 0;

  return (
    <main className="dashboard">
      <header className="hero">
        <div>
          <p className="eyebrow">YonBIP BI</p>
          <h1>合同金额逾期管理</h1>
          <p>按付款期次明细排行：未付优先展示，已付清默认折叠。同步范围近 12 个月创建合同。</p>
        </div>
        <div className="month-picker">
          <span>同步状态</span>
          {syncHint ? <small>{syncHint}</small> : <small>准备中…</small>}
          {data?.range ? (
            <small>
              数据范围 {data.range.start} ~ {data.range.end}
            </small>
          ) : null}
        </div>
      </header>

      {error ? <div className="alert error">{error}</div> : null}
      {syncStatus?.status === "running" || data?.meta.emptyCache ? (
        <div className="alert warning">{syncHint || "后台同步中…"}</div>
      ) : null}
      {syncStatus?.status === "error" ? <div className="alert error">{syncHint}</div> : null}

      <section className="filter-card">
        <span>未付状态</span>
        <div className="chips">
          {STATUS_OPTIONS.map((item) => (
            <label className="chip" key={item.value}>
              <input
                type="checkbox"
                checked={statuses.includes(item.value)}
                onChange={() => toggleStatus(item.value)}
              />
              {item.label}
            </label>
          ))}
        </div>
        <button type="button" className="link-button" onClick={() => loadOverdue(statuses, false)}>
          {loading ? "刷新中…" : "刷新表格"}
        </button>
        <button type="button" className="link-button" onClick={handleSyncNow}>
          立即同步
        </button>
      </section>

      <section className="kpi-grid">
        <KpiCard
          label="已逾期"
          value={String(data?.summary.overdue.count ?? 0)}
          hint={formatMoney(data?.summary.overdue.amount ?? 0)}
        />
        <KpiCard
          label="即将逾期（7天内）"
          value={String(data?.summary.upcoming.count ?? 0)}
          hint={formatMoney(data?.summary.upcoming.amount ?? 0)}
        />
        <KpiCard
          label="正常未付"
          value={String(data?.summary.normal.count ?? 0)}
          hint={formatMoney(data?.summary.normal.amount ?? 0)}
        />
        <KpiCard
          label="未付明细"
          value={String(data?.meta.rowCount ?? 0)}
          hint={`已付清 ${paidCount} · 本地合同 ${data?.meta.cachedContractCount ?? 0}`}
        />
      </section>

      <section className="table-card">
        <div className="panel-heading">
          <span>未付明细排行</span>
          <strong>越逾期越靠前，同档按未付金额从高到低</strong>
        </div>
        <OverdueTable
          rows={data?.rows ?? []}
          onOpenAttachments={setSelectedRow}
          showRank
          emptyText="暂无未付付款期次"
        />
      </section>

      <section className="table-card paid-collapse">
        <details>
          <summary>
            已付清（{paidCount}）
            <span>{formatMoney(data?.summary.paid.amount ?? 0)}</span>
          </summary>
          <OverdueTable
            rows={data?.paidRows ?? []}
            onOpenAttachments={setSelectedRow}
            emptyText="暂无已付清期次"
          />
        </details>
      </section>

      <AttachmentDrawer
        open={Boolean(selectedRow)}
        title={selectedRow ? `${selectedRow.contractCode || selectedRow.contractId} · ${selectedRow.supplier}` : ""}
        attachments={selectedRow?.attachments ?? []}
        onClose={() => setSelectedRow(null)}
      />
    </main>
  );
}
