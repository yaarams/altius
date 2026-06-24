// ============================================================
// Sync (R6)
// ============================================================

export type SyncStage =
  | 'discover'
  | 'download'
  | 'classify'
  | 'extract'
  | 'index';

export type SyncStageStatus = 'pending' | 'running' | 'done' | 'error';

export interface SyncStageEvent {
  stage: SyncStage;
  status: SyncStageStatus;
  files_discovered?: number;
  files_downloaded?: number;
  files_classified?: number;
  files_extracted?: number;
  files_indexed?: number;
  error?: string;
}

export interface SyncCompleteEvent {
  type: 'complete';
  stages: SyncStageEvent[];
}

export interface SyncErrorEvent {
  type: 'error';
  message: string;
}

export type SyncStreamEvent =
  | ({ type: 'stage' } & SyncStageEvent)
  | SyncCompleteEvent
  | SyncErrorEvent;

export interface SyncStartResponse {
  status: 'started';
  sync_id: string;
}

// ============================================================
// Holdings (R7)
// ============================================================

export interface HoldingLineItem {
  name: string;
  value: number;
  currency: string;
}

export interface FundSnapshot {
  fund_name: string;
  as_of_date: string; // ISO date string
  currency: string;   // ISO code e.g. "USD", "EUR"
  total_value: number;
  holdings: HoldingLineItem[];
}

// ============================================================
// Chat (R8)
// ============================================================

export interface Citation {
  file_id: string;
  file_name: string;
  period: string | null;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  out_of_context: boolean;
}

export interface ChatRequest {
  query: string;
}

// ============================================================
// Files (R9)
// ============================================================

export type DocType =
  | 'capital_account_statement'
  | 'report'
  | 'other';

export interface FileRecord {
  file_id: string;
  file_name: string;
  doc_type: DocType;
  classification_confidence: number; // 0..1
  low_confidence: boolean;           // true when confidence < 0.75
  period: string | null;
  fund_name: string | null;
  uploaded_at: string;               // ISO datetime string
}

// ============================================================
// Error types
// ============================================================

export class SyncInProgressError extends Error {
  constructor() {
    super('A sync is already in progress.');
    this.name = 'SyncInProgressError';
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}
