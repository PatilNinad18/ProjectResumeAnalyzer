// Screening API types and client functions
// Appended to the existing api.ts pattern — import these from "@/lib/api"

export const API_BASE_SCREENING = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ScreeningStatus = "QUEUED" | "ANALYZING" | "COMPLETED" | "FAILED" | "PARSE_FAILED";
export type EvaluationStatus = "MET" | "PARTIALLY_MET" | "NOT_EVIDENCED";
export type MatchTier = "STRONG_MATCH" | "POTENTIAL_MATCH" | "NOT_A_FIT";

export interface ResumeUploadItem {
  candidate_resume_id: string;
  filename: string;
  file_size_bytes: number | null;
  status: ScreeningStatus;
  message: string;
}

export interface BatchResumeUploadResponse {
  uploaded: ResumeUploadItem[];
  failed: Array<{ filename: string; error: string }>;
  total_queued: number;
}

export interface RequirementEvaluation {
  requirement: string;
  category: "must_have" | "preferred";
  status: EvaluationStatus;
  score_weight: number;
  evidence_quote: string | null;
  reasoning: string;
}

export interface ValidationCheckpoint {
  requirement: string;
  status: EvaluationStatus;
  interview_question: string;
}

export interface RequirementSummary {
  total: number;
  met: number;
  partially_met: number;
  not_evidenced: number;
}

export interface ScoreBreakdown {
  must_have_subscore: number;
  preferred_subscore: number;
  tenure_subscore: number;
  active_weight_total: number;
  must_have_base_weight: number;
  preferred_base_weight: number;
  tenure_base_weight: number;
}

export interface CandidateProfile {
  candidate_name: string | null;
  email: string | null;
  phone: string | null;
  total_experience_years: number | null;
  skills: string[];
  companies: string[];
  current_or_last_title: string | null;
}

export interface EvaluatorProvenance {
  evaluator_engine: string;
  model_name: string | null;
  model_version: string | null;
  prompt_version: string;
  temperature: number;
  seed: number;
}

export interface CandidateEvaluationDetail {
  candidate_resume_id: string;
  job_description_id: string;
  spec_version_id: string | null;
  specification_version: number;
  spec_outdated?: boolean;
  status: ScreeningStatus;
  overall_score: number | null;
  match_tier: MatchTier | null;
  effective_tier?: MatchTier | null;
  provenance?: EvaluatorProvenance | null;
  quote_verification_pass?: boolean | null;
  candidate_profile: CandidateProfile | null;
  must_haves_summary: RequirementSummary | null;
  preferred_summary: RequirementSummary | null;
  score_breakdown: ScoreBreakdown | null;
  detailed_evaluations: RequirementEvaluation[];
  validation_checkpoints: ValidationCheckpoint[];
  timeline_observations?: string[];
  red_flags?: string[];
  tailored_interview_questions: string[];
  recruiter_override_tier?: MatchTier | null;
  recruiter_override_score?: number | null;
  override_reason?: string | null;
  overridden_by?: string | null;
  overridden_at?: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface ScreeningLeaderboardItem {
  rank: number;
  candidate_resume_id: string;
  filename: string;
  candidate_name: string | null;
  email: string | null;
  total_experience_years: number | null;
  overall_score: number | null;
  match_tier: MatchTier | null;
  effective_tier?: MatchTier | null;
  must_haves_met: number;
  must_haves_total: number;
  not_evidenced_count: number;
  validation_checkpoints_count: number;
  status: ScreeningStatus;
  parse_failed?: boolean;
  spec_outdated?: boolean;
  created_at: string | null;
}

export interface ScreeningLeaderboardResponse {
  job_description_id: string;
  total_candidates: number;
  candidates: ScreeningLeaderboardItem[];
}

export interface ScreeningTriggerResponse {
  queued_count: number;
  candidate_resume_ids: string[];
  message: string;
}

// ---------------------------------------------------------------------------
// API client functions
// ---------------------------------------------------------------------------

export async function uploadCandidateResumes(
  jdId: string,
  files: File[]
): Promise<BatchResumeUploadResponse> {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const res = await fetch(`${API_BASE_SCREENING}/api/jds/${jdId}/resumes`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed (${res.status})`);
  }
  return res.json();
}

export async function triggerScreening(
  jdId: string,
  specVersionId?: string,
  candidateResumeIds?: string[]
): Promise<ScreeningTriggerResponse> {
  const res = await fetch(`${API_BASE_SCREENING}/api/jds/${jdId}/resumes/screen`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      spec_version_id: specVersionId ?? null,
      candidate_resume_ids: candidateResumeIds ?? null,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Screen trigger failed (${res.status})`);
  }
  return res.json();
}

export async function fetchScreeningLeaderboard(
  jdId: string
): Promise<ScreeningLeaderboardResponse> {
  const res = await fetch(`${API_BASE_SCREENING}/api/jds/${jdId}/resumes`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Fetch leaderboard failed (${res.status})`);
  }
  return res.json();
}

export async function fetchCandidateDetail(
  jdId: string,
  resumeId: string
): Promise<CandidateEvaluationDetail> {
  const res = await fetch(`${API_BASE_SCREENING}/api/jds/${jdId}/resumes/${resumeId}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Fetch candidate detail failed (${res.status})`);
  }
  return res.json();
}

export async function deleteCandidateResume(
  jdId: string,
  resumeId: string
): Promise<void> {
  const res = await fetch(`${API_BASE_SCREENING}/api/jds/${jdId}/resumes/${resumeId}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 204) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Delete failed (${res.status})`);
  }
}
