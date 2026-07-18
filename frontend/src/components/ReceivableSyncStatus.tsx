import { Alert, Badge, Typography } from "antd";

import type { ContractOverdueResult } from "../receivables/types";

const { Text } = Typography;

interface ReceivableSyncStatusProps {
  data: ContractOverdueResult | null;
}

function buildSyncSummary(data: ContractOverdueResult | null): string {
  const syncStatus = data?.meta.sync;
  const collectionSync = data?.meta.collectionSync;
  if (!syncStatus) {
    return "准备中…";
  }
  const invoicePart =
    syncStatus.status === "running"
      ? `发票同步中 ${syncStatus.doneCount}/${syncStatus.totalListed}`
      : `发票 ${syncStatus.cachedCount} 张`;
  const collectionPart = collectionSync
    ? collectionSync.status === "running"
      ? `收款同步中 ${collectionSync.doneCount}/${collectionSync.totalListed}`
      : `收款 ${collectionSync.cachedCount} 笔`
    : "收款准备中";
  if (syncStatus.status === "error") {
    return `发票同步失败：${syncStatus.error || "未知错误"}`;
  }
  if (collectionSync?.status === "error") {
    return `收款同步失败：${collectionSync.error || "未知错误"}`;
  }
  if (data?.meta.emptyCache) {
    return "本地暂无缓存，正在等待首次同步结果";
  }
  if (syncStatus.lastSyncedAt) {
    return `${invoicePart} · ${collectionPart} · 上次同步 ${syncStatus.lastSyncedAt}`;
  }
  return `${invoicePart} · ${collectionPart}`;
}

export function ReceivableSyncStatusInline({ data }: ReceivableSyncStatusProps) {
  const syncStatus = data?.meta.sync;
  const collectionSync = data?.meta.collectionSync;
  const isRunning =
    syncStatus?.status === "running" || collectionSync?.status === "running" || data?.meta.emptyCache;
  const hasError = syncStatus?.status === "error" || collectionSync?.status === "error";

  if (isRunning || hasError || !data) {
    return <Badge status={hasError ? "error" : "processing"} text={buildSyncSummary(data)} />;
  }

  return data.meta.updatedAt ? <Text type="secondary">数据更新于 {data.meta.updatedAt}</Text> : null;
}

export function ReceivableSyncStatusBanner({ data }: ReceivableSyncStatusProps) {
  const syncStatus = data?.meta.sync;
  const collectionSync = data?.meta.collectionSync;
  const isRunning =
    syncStatus?.status === "running" || collectionSync?.status === "running" || data?.meta.emptyCache;
  const hasError = syncStatus?.status === "error" || collectionSync?.status === "error";

  if (!isRunning && !hasError) {
    return null;
  }

  return (
    <Alert
      type={hasError ? "error" : "info"}
      showIcon
      message={buildSyncSummary(data)}
      style={{ marginBottom: 16 }}
    />
  );
}
