/** API client for NL2SQL backend services. */

const API_BASE = '';
const CHAT_TIMEOUT_MS = 120_000;

async function fetchWithTimeout(input: RequestInfo | URL, init: RequestInit = {}, timeoutMs = CHAT_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    });
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s. The backend may still be generating SQL.`);
    }
    throw err;
  } finally {
    window.clearTimeout(timeout);
  }
}

export interface ChatRequest {
  question: string;
  conversation_id?: string;
}

export interface ChatResponse {
  trace_id: string;
  question: string;
  sql: string;
  generated_sql?: string;
  result: any[] | string;
  columns: string[];
  execution_time: number;
  error: string | null;
  explanation?: string;
  insights?: string[];
}

export interface TableSchema {
  tables: Array<{
    table_name: string;
    columns: Array<{
      name: string;
      type: string;
      nullable: boolean;
      primary_key: boolean;
      default: string;
    }>;
    sample_rows: Record<string, any>[];
  }>;
}

export interface HealthStatus {
  status: string;
  models: {
    llm: { provider: string; model: string; connected: boolean };
    embedding: { provider: string; model: string; connected: boolean };
    reranker: { provider: string; model: string; loaded: boolean };
  };
  examples: { total: number };
}

export async function sendChat(request: ChatRequest): Promise<ChatResponse> {
  const res = await fetchWithTimeout(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error (${res.status}): ${err}`);
  }
  return res.json();
}

export async function getSchema(): Promise<TableSchema> {
  const res = await fetch(`${API_BASE}/api/schema`);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Failed to fetch schema (${res.status}): ${err}`);
  }
  return res.json();
}

export async function healthCheck(): Promise<HealthStatus> {
  const res = await fetch(`${API_BASE}/health`);
  return res.json();
}

export async function getTraceSummary(traceId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/traces/${traceId}/summary`);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Failed to fetch trace summary (${res.status}): ${err}`);
  }
  return res.json();
}

export async function getTraceDebug(traceId: string): Promise<any> {
  const res = await fetch(`${API_BASE}/api/traces/${traceId}/debug`);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Failed to fetch trace debug (${res.status}): ${err}`);
  }
  return res.json();
}
