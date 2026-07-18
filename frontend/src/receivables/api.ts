import type { ContractOverdueResult, ContractSyncStatus } from "./types";

export interface DingTalkContact {
  userid: string;
  name: string;
  department: string;
  title: string;
}

export interface DingTalkDepartment {
  departmentId: number;
  name: string;
}

export interface NotificationSchedule {
  kind: "minutes" | "hours" | "daily" | "weekly";
  interval: number;
  hour: number;
  minute: number;
  weekday: number;
}

export interface NotificationTask {
  id: string;
  creatorName: string;
  recipients: DingTalkContact[];
  schedule: NotificationSchedule;
  enabled: boolean;
  nextRunAt: string;
  lastRunAt: string;
  lastStatus: string;
  lastError: string;
  createdAt: string;
}

export interface SqlBotEmbedConfig {
  baseUrl: string;
  embeddedId: number;
  token: string;
  expiresAt: number;
}

async function parseResponse<T>(request: Promise<Response>): Promise<T> {
  const response = await request;
  if (response.status === 401) {
    window.location.reload();
    throw new Error("登录已失效，正在重新登录");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(String(body?.detail || body?.message || `请求失败：${response.status}`));
  }
  return response.json();
}


export async function fetchContractOverdue(
  statuses: Array<"overdue" | "upcoming" | "normal">,
  sync = false
): Promise<ContractOverdueResult> {
  const params = new URLSearchParams();
  if (statuses.length > 0) {
    params.set("status", statuses.join(","));
  }
  params.set("sync", sync ? "true" : "false");
  return parseResponse(fetch(`/api/bi/contract-overdue?${params.toString()}`));
}


export async function fetchContractOverdueSyncStatus(): Promise<ContractSyncStatus> {
  return parseResponse(fetch("/api/bi/contract-overdue/sync-status"));
}


export async function triggerContractOverdueSync(): Promise<ContractSyncStatus> {
  return parseResponse(fetch("/api/bi/contract-overdue/sync", { method: "POST", credentials: "include" }));
}

export async function searchDingTalkContacts(keyword: string): Promise<DingTalkContact[]> {
  const params = new URLSearchParams({ q: keyword });
  const result = await parseResponse<{ items: DingTalkContact[] }>(
    fetch(`/api/notifications/contacts?${params}`, { credentials: "include" })
  );
  return result.items;
}

export async function searchDingTalkDepartments(keyword: string): Promise<DingTalkDepartment[]> {
  const params = new URLSearchParams({ q: keyword });
  const result = await parseResponse<{ items: DingTalkDepartment[] }>(
    fetch(`/api/notifications/departments?${params}`, { credentials: "include" })
  );
  return result.items;
}

export async function fetchNotificationTasks(): Promise<NotificationTask[]> {
  const result = await parseResponse<{ items: NotificationTask[] }>(
    fetch("/api/notifications/tasks", { credentials: "include" })
  );
  return result.items;
}

export async function createNotificationTask(
  recipientUserids: string[],
  recipientDepartmentIds: number[],
  schedule: NotificationSchedule
): Promise<{ task: NotificationTask; immediate: { success: boolean; error?: string } }> {
  return parseResponse(
    fetch("/api/notifications/tasks", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recipientUserids, recipientDepartmentIds, schedule })
    })
  );
}

export async function setNotificationTaskEnabled(id: string, enabled: boolean): Promise<NotificationTask> {
  const result = await parseResponse<{ task: NotificationTask }>(
    fetch(`/api/notifications/tasks/${id}`, {
      method: "PATCH",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled })
    })
  );
  return result.task;
}

export async function deleteNotificationTask(id: string): Promise<void> {
  await parseResponse(
    fetch(`/api/notifications/tasks/${id}`, {
      method: "DELETE",
      credentials: "include"
    })
  );
}

export async function fetchSqlBotEmbedConfig(): Promise<SqlBotEmbedConfig> {
  return parseResponse(
    fetch("/api/sqlbot/embed-token", {
      credentials: "include"
    })
  );
}
