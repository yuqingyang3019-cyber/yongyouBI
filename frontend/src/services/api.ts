import type { ExecutionSummary } from "../types";

export async function fetchExecutionSummary(month: string, docTypes: string[]): Promise<ExecutionSummary> {
  const params = new URLSearchParams();
  if (month) {
    params.set("month", month);
  }
  if (docTypes.length > 0) {
    params.set("docTypes", docTypes.join(","));
  }

  const response = await fetch(`/api/bi/execution-summary?${params.toString()}`);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `请求失败：${response.status}`);
  }
  return response.json();
}
