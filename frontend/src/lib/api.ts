const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api";

export type ProcessingStatus =
  | "UPLOADED"
  | "PARSING"
  | "UNDERSTANDING"
  | "VALIDATING"
  | "GENERATING"
  | "READY"
  | "NEEDS_REVIEW"
  | "FAILED";

export async function uploadJD(projectId: string, text: string, title?: string) {
  const form = new FormData();
  form.append("project_id", projectId);
  form.append("text", text);
  if (title) form.append("title", title);
  const res = await fetch(`${API_BASE}/jds`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json() as Promise<{ jd_id: string; jd_version_id: string; version: number; status: string }>;
}

export async function analyzeJD(jdId: string) {
  const res = await fetch(`${API_BASE}/jds/${jdId}/analyze`, { method: "POST" });
  if (!res.ok) throw new Error(`Analyze failed: ${res.status}`);
  return res.json();
}

export async function getAnalysisStatus(jdId: string) {
  const res = await fetch(`${API_BASE}/jds/${jdId}/analysis`);
  if (!res.ok) throw new Error(`Status fetch failed: ${res.status}`);
  return res.json() as Promise<{ status: ProcessingStatus; error_message: string | null }>;
}

export async function getMarkdown(jdId: string) {
  const res = await fetch(`${API_BASE}/jds/${jdId}/markdown`);
  if (!res.ok) throw new Error(`Markdown fetch failed: ${res.status}`);
  return res.json() as Promise<{ markdown: string; specification_version: number }>;
}

export async function getJson(jdId: string) {
  const res = await fetch(`${API_BASE}/jds/${jdId}/json`);
  if (!res.ok) throw new Error(`JSON fetch failed: ${res.status}`);
  return res.json() as Promise<{ json: Record<string, unknown>; specification_version: number }>;
}

export async function getVersions(jdId: string) {
  const res = await fetch(`${API_BASE}/jds/${jdId}/versions`);
  if (!res.ok) throw new Error(`Versions fetch failed: ${res.status}`);
  return res.json();
}
