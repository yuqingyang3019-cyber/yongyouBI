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
