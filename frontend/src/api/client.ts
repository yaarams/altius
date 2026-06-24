import type {
  SyncStartResponse,
  SyncStreamEvent,
  FundSnapshot,
  ChatRequest,
  ChatResponse,
  FileRecord,
} from './types';
import { SyncInProgressError, ApiError } from './types';

const BASE_URL = '/api';

// ── Low-level fetch helper ──────────────────────────────────

async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json() as { detail?: string; message?: string };
      message = body.detail ?? body.message ?? message;
    } catch {
      // ignore parse error
    }
    throw new ApiError(res.status, message);
  }

  // For endpoints that return no body (204, etc.)
  const ct = res.headers.get('content-type') ?? '';
  if (!ct.includes('application/json')) {
    return undefined as unknown as T;
  }
  return res.json() as Promise<T>;
}

// ── Sync ────────────────────────────────────────────────────

/**
 * POST /api/sync — start a sync run.
 * Throws SyncInProgressError on 409.
 */
export async function startSync(): Promise<SyncStartResponse> {
  try {
    return await apiFetch<SyncStartResponse>('/sync', { method: 'POST' });
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      throw new SyncInProgressError();
    }
    throw err;
  }
}

/**
 * Subscribe to staged SSE progress stream.
 * Returns a cleanup function to close the EventSource.
 */
export function subscribeSync(
  onEvent: (event: SyncStreamEvent) => void,
  onError?: (err: Event) => void,
): () => void {
  const es = new EventSource(`${BASE_URL}/sync/stream`);

  es.addEventListener('stage', (e: MessageEvent) => {
    const data = JSON.parse(e.data) as SyncStreamEvent;
    onEvent(data);
  });

  es.addEventListener('complete', (e: MessageEvent) => {
    const data = JSON.parse(e.data) as SyncStreamEvent;
    onEvent(data);
    es.close();
  });

  es.addEventListener('error', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data) as SyncStreamEvent;
      onEvent(data);
    } catch {
      // connection-level error
      if (onError) onError(e);
    }
    es.close();
  });

  es.onerror = (e) => {
    if (onError) onError(e);
    es.close();
  };

  return () => es.close();
}

// ── Holdings ────────────────────────────────────────────────

/** Backend shape returned by GET /api/holdings */
interface BackendHoldingRow {
  fund_name: string;
  current_value: string;   // pre-formatted, e.g. "$15,400,000.00"
  statement_date: string;  // human string or ISO, e.g. "March 31, 2025"
  file_id: number;
}

interface HoldingsResponse {
  holdings: BackendHoldingRow[];
}

/** Currency symbol → ISO 4217 code */
const SYMBOL_TO_CODE: Record<string, string> = {
  '$': 'USD',
  '€': 'EUR',
  '£': 'GBP',
};

/**
 * Parse a pre-formatted currency string like "$15,400,000.00" to a number.
 * Strips leading currency symbol, commas, and whitespace before parsing.
 */
function parseCurrencyValue(raw: string): number {
  const cleaned = raw.replace(/[^\d.]/g, '');
  return parseFloat(cleaned) || 0;
}

/**
 * Infer ISO currency code from the leading symbol in a formatted string.
 * Defaults to "USD" if unknown.
 */
function inferCurrencyCode(raw: string): string {
  const trimmed = raw.trimStart();
  for (const [symbol, code] of Object.entries(SYMBOL_TO_CODE)) {
    if (trimmed.startsWith(symbol)) return code;
  }
  return 'USD';
}

/**
 * Convert a human-readable or ISO date string to YYYY-MM-DD.
 * Falls back to the original string if parsing fails.
 */
function toIsoDate(raw: string): string {
  const d = new Date(raw);
  if (!isNaN(d.getTime())) {
    return d.toISOString().slice(0, 10);
  }
  return raw;
}

/** GET /api/holdings → array of latest fund snapshots (may be empty). */
export async function getHoldings(): Promise<FundSnapshot[]> {
  const res = await apiFetch<HoldingsResponse>('/holdings');
  return (res.holdings ?? []).map((row) => ({
    fund_name: row.fund_name,
    total_value: parseCurrencyValue(row.current_value),
    currency: inferCurrencyCode(row.current_value),
    as_of_date: toIsoDate(row.statement_date),
    holdings: [],
  }));
}

// ── Chat ────────────────────────────────────────────────────

/** POST /api/chat */
export async function postChat(req: ChatRequest): Promise<ChatResponse> {
  return apiFetch<ChatResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

// ── Files ───────────────────────────────────────────────────

/** GET /api/files → full file list */
export async function getFiles(): Promise<FileRecord[]> {
  return apiFetch<FileRecord[]>('/files');
}

/**
 * Returns the URL to open/download a specific file.
 * Use as <a href={fileDownloadUrl(id)} target="_blank"> or window.open().
 */
export function fileDownloadUrl(fileId: string): string {
  return `${BASE_URL}/files/${fileId}/download`;
}

// Re-export types and errors so consumers can import everything from one place
export type {
  SyncStartResponse,
  SyncStreamEvent,
  FundSnapshot,
  ChatRequest,
  ChatResponse,
  FileRecord,
};
export { SyncInProgressError, ApiError };
