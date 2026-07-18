export type OverdueStatus =
  | "overdue"
  | "upcoming"
  | "normal"
  | "pending_audit"
  | "unmatched"
  | "true_overdue"
  | "settled";

export type CollectionStatus = "settled" | "partial" | "unpaid";
export type MatchQuality = "exact" | "partial_exact" | "contract" | "estimated" | "unpaid";

export interface ContractOverdueRow {
  invoiceId: string;
  invoiceCode: string;
  contractCode: string;
  customer: string;
  salesman: string;
  taxAmount: number;
  collectedAmount: number;
  outstanding: number;
  collectionStatus: CollectionStatus;
  matchQuality: MatchQuality;
  auditTime: string;
  paymentTermDays: number;
  dueDate: string;
  daysUntilDue: number;
  status: OverdueStatus;
  calendarStatus?: OverdueStatus;
  trueStatus?: OverdueStatus;
}

export interface StatusBucket {
  count: number;
  amount: number;
}

export interface ContractSyncStatus {
  month: string;
  scope?: string;
  status: "idle" | "running" | "done" | "error";
  pending: number;
  doneCount: number;
  totalListed: number;
  skipped: number;
  error: string;
  lastSyncedAt: string;
  updatedAt: string;
  cachedCount: number;
  range?: {
    start: string;
    end: string;
  };
}

export interface ContractReceivableSummary {
  contractCode: string;
  customer: string;
  receivableAmount: number;
  collectedAmount: number;
  outstanding: number;
  trueOverdueAmount: number;
  invoiceCount: number;
  trueOverdueCount: number;
}

export interface ContractOverdueResult {
  scope: string;
  range: {
    start: string;
    end: string;
  };
  query: {
    statuses: Array<"overdue" | "upcoming" | "normal">;
  };
  summary: {
    overdue: StatusBucket;
    calendarOverdue: StatusBucket;
    trueOverdue: StatusBucket;
    upcoming: StatusBucket;
    normal: StatusBucket;
    settled: StatusBucket;
    unmatched: StatusBucket;
    pendingAudit: StatusBucket;
  };
  charts: ReceivableChartsData;
  rows: ContractOverdueRow[];
  pendingAuditRows: ContractOverdueRow[];
  unmatchedRows: ContractOverdueRow[];
  settledRows: ContractOverdueRow[];
  contractSummary: ContractReceivableSummary[];
  meta: {
    cachedInvoiceCount: number;
    cachedContractCount: number;
    cachedCollectionCount: number;
    rowCount: number;
    pendingAuditRowCount: number;
    unmatchedRowCount: number;
    settledRowCount: number;
    updatedAt: string;
    sync: ContractSyncStatus;
    collectionSync?: ContractSyncStatus;
    emptyCache: boolean;
  };
}

export interface ReceivableAgingBucket {
  label: string;
  count: number;
  amount: number;
}

export interface ReceivableTopCustomer {
  customer: string;
  amount: number;
  count: number;
}

export interface ReceivableChartsData {
  agingBuckets: ReceivableAgingBucket[];
  topCustomers: ReceivableTopCustomer[];
}
