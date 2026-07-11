import type { ContractOverdueResult, ContractSyncStatus, ExecutionSummary } from "../types";

export async function fetchExecutionSummary(
  month: string,
  docTypes: string[],
  persons: string[],
  personMatchMode: "contains" | "exact" = "contains",
  topN = 10,
  refresh = false
): Promise<ExecutionSummary> {
  const params = new URLSearchParams();
  if (month) {
    params.set("month", month);
  }
  if (docTypes.length > 0) {
    params.set("docTypes", docTypes.join(","));
  }
  if (persons.length > 0) {
    params.set("persons", persons.join(","));
  }
  params.set("personMatchMode", personMatchMode);
  params.set("topN", String(topN));
  if (refresh) {
    params.set("refresh", "true");
  }

  const response = await fetch(`/api/bi/execution-summary?${params.toString()}`);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `请求失败：${response.status}`);
  }
  return response.json();
}

export async function fetchContractOverdue(
  statuses: Array<"overdue" | "upcoming" | "normal">,
  sync = true
): Promise<ContractOverdueResult> {
  const params = new URLSearchParams();
  if (statuses.length > 0) {
    params.set("status", statuses.join(","));
  }
  params.set("sync", sync ? "true" : "false");

  const response = await fetch(`/api/bi/contract-overdue?${params.toString()}`);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `请求失败：${response.status}`);
  }
  return response.json();
}

export async function fetchContractOverdueSyncStatus(): Promise<ContractSyncStatus> {
  const response = await fetch("/api/bi/contract-overdue/sync-status");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `请求失败：${response.status}`);
  }
  return response.json();
}

export async function triggerContractOverdueSync(): Promise<ContractSyncStatus> {
  const response = await fetch("/api/bi/contract-overdue/sync", {
    method: "POST"
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `请求失败：${response.status}`);
  }
  return response.json();
}
