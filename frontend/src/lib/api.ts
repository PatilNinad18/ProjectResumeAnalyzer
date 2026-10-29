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
  progress_percent?: number;
  stage_label?: string;
  current_stage?: string;
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
  const { timeoutMs = 30_000, signal, headers, ...rest } = init;
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onAbort = () => controller.abort();
  signal?.addEventListener("abort", onAbort);

  const reqHeaders = new Headers(headers);
  if (typeof rest.body === "string" && !reqHeaders.has("Content-Type")) {
    reqHeaders.set("Content-Type", "application/json");
  }

  try {
    const res = await fetch(`${API_BASE}${path}`, { ...rest, headers: reqHeaders, signal: controller.signal });
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

export async function cancelAnalysis(jdId: string): Promise<{ status: string; message: string }> {
  return request(`/api/jds/${jdId}/analysis/cancel`, { method: "POST", timeoutMs: 10_000 });
}

export async function getAnalysisStatus(jdId: string, signal?: AbortSignal): Promise<AnalysisStatusResponse> {
  return request(`/api/jds/${jdId}/analysis`, { signal, timeoutMs: 15_000 });
}

export async function getMarkdown(
  jdId: string,
  enriched?: boolean,
  version?: number
): Promise<{ markdown: string; specification_version: number; is_enriched?: boolean }> {
  const params = new URLSearchParams();
  if (enriched !== undefined) params.append("enriched", String(enriched));
  if (version !== undefined) params.append("version", String(version));
  const query = params.toString() ? `?${params.toString()}` : "";
  return request(`/api/jds/${jdId}/markdown${query}`);
}

export async function getJson(
  jdId: string,
  version?: number
): Promise<{ json: Record<string, unknown>; specification_version: number }> {
  const query = version !== undefined ? `?version=${version}` : "";
  return request(`/api/jds/${jdId}/json${query}`);
}

// ---------------------------------------------------------------------------
// Long-running background tasks (enrichment, clarification resolve)
// The POST returns immediately (HTTP 202); call waitForTask() to wait for the result,
// then fetch it with getMarkdown / getJson / getClarifications.
// ---------------------------------------------------------------------------
export type TaskKind = "enrich" | "resolve";

export interface TaskStatusResponse {
  kind: TaskKind;
  status: "idle" | "running" | "done" | "failed";
  error: string | null;
  elapsed_seconds: number | null;
  stage?: string;
  stage_label?: string;
  progress_percent?: number;
}

/** Starts Ollama enrichment in the background (HTTP 202). Follow with waitForTask(jdId, "enrich"). */
export async function enrichJD(jdId: string): Promise<{ status: string }> {
  return request(`/api/jds/${jdId}/enrich`, { method: "POST", timeoutMs: 15_000 });
}

export async function getTaskStatus(jdId: string, kind: TaskKind, signal?: AbortSignal): Promise<TaskStatusResponse> {
  return request(`/api/jds/${jdId}/tasks/${kind}`, { signal, timeoutMs: 15_000 });
}

export async function cancelTask(jdId: string, kind: TaskKind): Promise<{ status: string; message: string }> {
  return request(`/api/jds/${jdId}/tasks/${kind}/cancel`, { method: "POST", timeoutMs: 10_000 });
}

export interface ClarificationQuestionItem {
  question_key: string;
  category: string;
  priority: string;
  question_text: string;
  field_target: string;
  status: string;
  answer?: string | null;
  answer_text?: string | null;
  rationale?: string;
  suggested_options?: string[];
}

export interface ClarificationsResponse {
  has_ambiguities: boolean;
  questions: ClarificationQuestionItem[];
  ambiguities: Array<Record<string, unknown>>;
  missing_information: Array<Record<string, unknown>>;
  specification_version: number;
  lifecycle_status: string;
}

export async function getClarifications(jdId: string): Promise<ClarificationsResponse> {
  return request(`/api/jds/${jdId}/clarifications`);
}

/** Starts "apply TA answers + generate final spec" in the background (HTTP 202). Follow with waitForTask(jdId, "resolve"). */
export async function resolveClarifications(
  jdId: string,
  answers: Record<string, string>,
  answeredBy: string = "TA / Hiring Team"
): Promise<{ status: string }> {
  return request(`/api/jds/${jdId}/clarifications/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers, answered_by: answeredBy }),
    timeoutMs: 15_000,
  });
}

// ---------------------------------------------------------------------------
// JD Context Comparison
// ---------------------------------------------------------------------------
export type JDContextType = "baseline" | "enriched" | "resolved";

export interface RequirementDiffItem {
  id: string;
  text: string;
  priority: string;
  clause_type?: string;
  is_mandatory?: boolean;
  origin_type: string;
  provenance_type: "source_evidence" | "ta_confirmed" | "llm_hypothesis" | "ekg_derived";
  provenance_badge: string;
  source_text?: string;
  source_section?: string;
  author?: string | null;
  timestamp?: string | null;
  diff_status: "added" | "removed" | "modified" | "unchanged";
  diff_badge: string;
  diff_reason?: string;
  base_priority?: string;
  target_priority?: string;
  base_provenance?: string;
  target_provenance?: string;
  base_text?: string;
  changes?: string[];
  enriched_guidance?: {
    technical_concept_summary?: string;
    strong_evidence_signals?: string[];
    weak_or_ambiguous_signals?: string[];
    screening_question?: string;
  };
}

export interface AmbiguityItem {
  question_key: string;
  question_text: string;
  category: string;
  priority: string;
  status: string;
  answer_text?: string;
  answered_by?: string;
  answered_at?: string;
  is_ta_confirmed?: boolean;
  is_blocking?: boolean;
  why_ambiguous?: string;
  suggested_options?: string[];
}

export interface ContextComparisonResponse {
  jd_id: string;
  has_baseline: boolean;
  has_enriched: boolean;
  has_resolved: boolean;
  selected_base_context: string;
  selected_target_context: string;
  versions: Array<{
    specification_version: number;
    created_at: string | null;
    has_enrichment: boolean;
    lifecycle_status: string;
  }>;
  contexts: {
    baseline?: {
      version: number;
      markdown: string;
      requirements_count: number;
      created_at: string | null;
    };
    enriched?: {
      version: number | null;
      markdown: string;
      has_guidance: boolean;
      evaluation_priorities: string[];
      created_at: string | null;
    };
    resolved?: {
      version: number | null;
      markdown: string;
      requirements_count: number;
      lifecycle_status: string | null;
      created_at: string | null;
    };
  };
  diff: {
    added: RequirementDiffItem[];
    removed: RequirementDiffItem[];
    modified: RequirementDiffItem[];
    unchanged: RequirementDiffItem[];
    counts: {
      total_base: number;
      total_target: number;
      added: number;
      removed: number;
      modified: number;
      unchanged: number;
    };
  };
  ambiguities: {
    resolved: AmbiguityItem[];
    unresolved: AmbiguityItem[];
    counts: {
      resolved: number;
      unresolved: number;
    };
  };
}

export async function getComparison(
  jdId: string,
  base: string = "baseline",
  target?: string
): Promise<ContextComparisonResponse> {
  const params = new URLSearchParams();
  if (base) params.append("base", base);
  if (target) params.append("target", target);
  return request(`/api/jds/${jdId}/compare?${params.toString()}`);
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
    onProgress?: (progress: { percent: number; stageLabel: string; status: ProcessingStatus }) => void;
    signal?: AbortSignal;
    intervalMs?: number;
    timeoutMs?: number;
    maxConsecutiveErrors?: number;
  } = {}
): Promise<AnalysisStatusResponse> {
  const { onStatus, onProgress, signal, intervalMs = 2000, timeoutMs = 30 * 60_000, maxConsecutiveErrors = 5 } = opts;
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
      if (onProgress && s.progress_percent !== undefined && s.stage_label) {
        onProgress({
          percent: s.progress_percent,
          stageLabel: s.stage_label,
          status: s.status,
        });
      }
      if (TERMINAL_STATUSES.includes(s.status)) return s;
    } catch (e) {
      if ((e as Error).name === "AbortError") throw e;
      errors += 1;
      if (errors >= maxConsecutiveErrors) throw e;
    }
    await sleep(intervalMs, signal);
  }
}

/**
 * Poll a background task (enrich / resolve) until it is done.
 * Resolves when the task finished successfully; throws Error(message) if it failed.
 */
export async function waitForTask(
  jdId: string,
  kind: TaskKind,
  opts: {
    signal?: AbortSignal;
    onTick?: (s: TaskStatusResponse) => void;
    intervalMs?: number;
    timeoutMs?: number;
    maxConsecutiveErrors?: number;
  } = {}
): Promise<TaskStatusResponse> {
  const { signal, onTick, intervalMs = 2000, timeoutMs = 30 * 60_000, maxConsecutiveErrors = 5 } = opts;
  const started = Date.now();
  let errors = 0;

  for (;;) {
    if (Date.now() - started > timeoutMs) {
      throw new Error(`Timed out waiting for "${kind}" to finish. Check the backend logs.`);
    }
    try {
      const s = await getTaskStatus(jdId, kind, signal);
      errors = 0;
      onTick?.(s);
      if (s.status === "done") return s;
      if (s.status === "failed") throw new Error(s.error || `The "${kind}" task failed. Check the backend logs.`);
      if (s.status === "idle") {
        throw new Error(`The "${kind}" task was not found on the server (it may have restarted). Please try again.`);
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") throw e;
      // A real task failure carries a message from the server; network blips are retried.
      if (e instanceof TypeError || /Cannot reach the backend|timed out after/.test((e as Error).message)) {
        errors += 1;
        if (errors >= maxConsecutiveErrors) throw e;
      } else {
        throw e;
      }
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
    timeoutMs: 300_000, // safety margin for CPU inference
  };
  return jdId ? request(`/api/jds/${jdId}/chat`, init) : request("/api/chat", init);
}


// ---------------------------------------------------------------------------
// Agent Management (CRUD)
// ---------------------------------------------------------------------------

export async function getAgents(signal?: AbortSignal): Promise<CreatedAgent[]> {
  return request<CreatedAgent[]>("/api/agents", { signal });
}

export async function getAgent(agentId: string, signal?: AbortSignal): Promise<CreatedAgent> {
  return request<CreatedAgent>(`/api/agents/${encodeURIComponent(agentId)}`, { signal });
}

export async function createAgentApi(payload: Partial<CreatedAgent>, signal?: AbortSignal): Promise<CreatedAgent> {
  return request<CreatedAgent>("/api/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
}

export async function updateAgentApi(
  agentId: string,
  payload: Partial<CreatedAgent>,
  signal?: AbortSignal
): Promise<CreatedAgent> {
  return request<CreatedAgent>(`/api/agents/${encodeURIComponent(agentId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
}

export async function deleteAgentApi(
  agentId: string,
  cancelActive: boolean = false,
  signal?: AbortSignal
): Promise<{
  agent_id: string;
  status: string;
  message: string;
  job_description_retained: boolean;
}> {
  return request<{
    agent_id: string;
    status: string;
    message: string;
    job_description_retained: boolean;
  }>(`/api/agents/${encodeURIComponent(agentId)}?cancel_active=${cancelActive ? "true" : "false"}`, {
    method: "DELETE",
    signal,
  });
}
