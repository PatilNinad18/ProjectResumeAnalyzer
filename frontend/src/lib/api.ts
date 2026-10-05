// frontend/src/lib/api.ts
// Typed API client. Set NEXT_PUBLIC_API_URL in .env.local to change the backend URL.

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export type ProcessingStatus =
  | "UPLOADED"
  | "PARSING"
  | "UNDERSTANDING"
  | "VALIDATING"
  | "GENERATING"
  | "READY"
  | "NEEDS_REVIEW"
  | "FAILED";

export const TERMINAL_STATUSES: ProcessingStatus[] = ["READY", "NEEDS_REVIEW", "FAILED"];

export interface CompanyDetails {
  companyName: string;
  department: string;
  projectName: string;
}

export interface CreatedAgent {
  id: string;
  agentName: string;
  title: string;
  companyDetails: CompanyDetails;
  jdId: string;
  jdText: string;
  markdown: string;
  jsonData: Record<string, unknown>;
  specificationVersion: number;
  status: "ACTIVE" | "INACTIVE";
  createdAt: string;
  updatedAt: string;
}

export interface AnalysisStatusResponse {
  status: ProcessingStatus;
  error_message: string | null;
  started_at?: string | number | null;
  finished_at?: string | number | null;
  elapsed_seconds?: number | null;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

// ---------------------------------------------------------------------------
// Low-level request helper: timeout + FastAPI error parsing
// ---------------------------------------------------------------------------
async function request<T>(
  path: string,
  init: RequestInit & { timeoutMs?: number } = {}
): Promise<T> {
  const { timeoutMs = 30_000, signal, ...rest } = init;
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onAbort = () => controller.abort();
  signal?.addEventListener("abort", onAbort);

  try {
    const res = await fetch(`${API_BASE}${path}`, { ...rest, signal: controller.signal });
    if (!res.ok) {
      let detail = `Request failed (${res.status})`;
      try {
        const body = await res.json();
        if (typeof body?.detail === "string") detail = body.detail;
        else if (Array.isArray(body?.detail)) detail = body.detail.map((d: { msg?: string }) => d.msg).join("; ");
      } catch {
        /* non-JSON error body */
      }
      throw new Error(detail);
    }
    return (await res.json()) as T;
  } catch (e) {
    if ((e as Error).name === "AbortError") {
      if (timedOut) throw new Error(`The request timed out after ${Math.round(timeoutMs / 1000)}s.`);
      throw e; // cancelled by the caller
    }
    if (e instanceof TypeError) {
      throw new Error(`Cannot reach the backend at ${API_BASE}. Is it running?`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
}

// ---------------------------------------------------------------------------
// JD endpoints
// ---------------------------------------------------------------------------
export async function uploadJD(
  projectId: string,
  input: { text?: string; file?: File },
  title?: string
): Promise<{ jd_id: string; title: string; jd_version_id: string }> {
  const form = new FormData();
  form.append("project_id", projectId);
  if (title) form.append("title", title);
  if (input.file) form.append("file", input.file);
  else if (input.text) form.append("text", input.text);
  return request("/api/jds", { method: "POST", body: form, timeoutMs: 60_000 });
}

/** Returns immediately (HTTP 202); the analysis runs in the background. */
export async function analyzeJD(jdId: string): Promise<{ status: string }> {
  return request(`/api/jds/${jdId}/analyze`, { method: "POST", timeoutMs: 15_000 });
}

export async function getAnalysisStatus(jdId: string, signal?: AbortSignal): Promise<AnalysisStatusResponse> {
  return request(`/api/jds/${jdId}/analysis`, { signal, timeoutMs: 15_000 });
}

export async function getMarkdown(jdId: string): Promise<{ markdown: string; specification_version: number }> {
  return request(`/api/jds/${jdId}/markdown`);
}

export async function getJson(jdId: string): Promise<{ json: Record<string, unknown>; specification_version: number }> {
  return request(`/api/jds/${jdId}/json`);
}

// ---------------------------------------------------------------------------
// Polling
// ---------------------------------------------------------------------------
function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException("Aborted", "AbortError"));
    const t = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(t);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * Poll until the analysis reaches a terminal status.
 * Tolerates brief network blips, supports cancellation, and gives up after timeoutMs.
 */
export async function pollUntilDone(
  jdId: string,
  opts: {
    onStatus?: (status: ProcessingStatus) => void;
    signal?: AbortSignal;
    intervalMs?: number;
    timeoutMs?: number;
    maxConsecutiveErrors?: number;
  } = {}
): Promise<AnalysisStatusResponse> {
  const { onStatus, signal, intervalMs = 2000, timeoutMs = 30 * 60_000, maxConsecutiveErrors = 5 } = opts;
  const started = Date.now();
  let errors = 0;

  for (;;) {
    if (Date.now() - started > timeoutMs) {
      throw new Error("Timed out waiting for the analysis to finish. Check the backend logs.");
    }
    try {
      const s = await getAnalysisStatus(jdId, signal);
      errors = 0;
      onStatus?.(s.status);
      if (TERMINAL_STATUSES.includes(s.status)) return s;
    } catch (e) {
      if ((e as Error).name === "AbortError") throw e;
      errors += 1;
      if (errors >= maxConsecutiveErrors) throw e;
    }
    await sleep(intervalMs, signal);
  }
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------
export async function askJDChatbot(
  jdId: string | null,
  question: string,
  markdownContext: string | null,
  history: ChatTurn[] = []
): Promise<{ answer: string }> {
  const body = JSON.stringify({ question, markdown: markdownContext, history });
  const init = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    timeoutMs: 180_000, // a local model can take a while
  };
  return jdId ? request(`/api/jds/${jdId}/chat`, init) : request("/api/chat", init);
}