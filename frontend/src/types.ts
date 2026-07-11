export interface Totals {
  count: number;
  amount: number;
  quantity: number;
  missingPersonCount: number;
  missingSupplierCount: number;
}

export interface PersonMetric {
  person: string;
  count: number;
  amount: number;
  quantity: number;
}

export interface NamedMetric {
  count: number;
  amount: number;
  quantity: number;
}

export interface SupplierMetric extends NamedMetric {
  supplier: string;
}

export interface OrgMetric extends NamedMetric {
  org: string;
}

export interface StatusMetric extends NamedMetric {
  status: string;
}

export interface DocumentTypeMetric {
  type: string;
  label: string;
  count: number;
  amount: number;
  quantity: number;
  recordCount: number;
  fetchedPages: number;
  truncated: boolean;
  error: string;
}

export interface MatrixMetric {
  person: string;
  type: string;
  label: string;
  count: number;
  amount: number;
  quantity: number;
}

export interface LifecycleMetric {
  type: string;
  label: string;
  count: number;
  amount: number;
  quantity: number;
  stageOrder: number;
}

export interface DocumentTypeOption {
  type: string;
  label: string;
}

export interface ExecutionSummary {
  month: string;
  range: {
    start: string;
    end: string;
  };
  query: {
    persons: string[];
    personMatchMode: "contains" | "exact";
    topN: number;
    docTypes: string[];
  };
  totals: Totals;
  byPerson: PersonMetric[];
  byPersonTopN: PersonMetric[];
  bySupplier: SupplierMetric[];
  bySupplierTopN: SupplierMetric[];
  byOrg: OrgMetric[];
  byOrgTopN: OrgMetric[];
  byStatus: StatusMetric[];
  byDocumentType: DocumentTypeMetric[];
  lifecycle: LifecycleMetric[];
  coverage: {
    arrivalVsOrderAmount: number;
    invoiceVsOrderAmount: number;
    paymentApplyVsOrderAmount: number;
  };
  matrix: MatrixMetric[];
  availableDocumentTypes: DocumentTypeOption[];
  availablePeople: string[];
  meta: {
    fromCache: boolean;
    generatedAt: number | string;
    cacheKey: string;
  };
}

export type OverdueStatus = "overdue" | "upcoming" | "normal" | "paid";

export interface ContractAttachment {
  type: string;
  label: string;
  url: string;
  fileId: string;
}

export interface ContractOverdueRow {
  contractId: string;
  contractCode: string;
  supplier: string;
  person: string;
  payPeriod: number | string | null;
  payPointName: string;
  source: string;
  payTaxMoney: number;
  paidAmount: number;
  unpaidAmount: number;
  dueDate: string;
  daysUntilDue: number;
  status: OverdueStatus;
  attachments: ContractAttachment[];
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
    upcoming: StatusBucket;
    normal: StatusBucket;
    paid: StatusBucket;
  };
  rows: ContractOverdueRow[];
  paidRows: ContractOverdueRow[];
  meta: {
    cachedContractCount: number;
    rowCount: number;
    paidRowCount: number;
    updatedAt: string;
    sync: ContractSyncStatus;
    emptyCache: boolean;
  };
}
