import type { ExecutionSummary } from "../types";

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
