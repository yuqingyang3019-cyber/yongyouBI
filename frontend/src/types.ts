export interface Totals {
  count: number;
  amount: number;
  missingPersonCount: number;
}

export interface PersonMetric {
  person: string;
  count: number;
  amount: number;
}

export interface DocumentTypeMetric {
  type: string;
  label: string;
  count: number;
  amount: number;
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
  totals: Totals;
  byPerson: PersonMetric[];
  byDocumentType: DocumentTypeMetric[];
  matrix: MatrixMetric[];
  availableDocumentTypes: DocumentTypeOption[];
}
