import { useState, useCallback, useEffect, useRef } from "react";
import {
  uploadCandidateResumes,
  triggerScreening,
  fetchScreeningLeaderboard,
  fetchCandidateDetail,
  deleteCandidateResume,
  saveScreeningOverride,
  updateScreeningPolicy,
  type ScreeningLeaderboardItem,
  type CandidateEvaluationDetail,
  type BatchResumeUploadResponse,
  type ScreeningLeaderboardResponse,
  type ScreeningOverrideRequest,
} from "@/lib/screening_api";

export type SortKey = "rank" | "score" | "tier" | "name" | "experience";
export type TierFilter = "ALL" | "STRONG_MATCH" | "POTENTIAL_MATCH" | "NOT_A_FIT" | "REVIEW" | "OUTDATED";

export interface UseCandidateScreeningReturn {
  // State
  jdId: string | null;
  candidates: ScreeningLeaderboardItem[];
  totalCandidates: number;
  screeningSpec: Pick<ScreeningLeaderboardResponse, "spec_version_id" | "specification_version" | "spec_finalized" | "criteria"> | null;
  selectedCandidate: CandidateEvaluationDetail | null;
  isDrawerOpen: boolean;
  isUploading: boolean;
  isScreening: boolean;
  isPolling: boolean;
  isLoadingDetail: boolean;
  uploadResult: BatchResumeUploadResponse | null;
  error: string | null;
  sortKey: SortKey;
  tierFilter: TierFilter;
  // Actions
  setJdId: (id: string) => void;
  handleUpload: (files: File[]) => Promise<void>;
  handleScreenAll: () => Promise<void>;
  openCandidateDetail: (resumeId: string, evaluationId?: string) => Promise<void>;
  handleScreenCandidate: (resumeId: string) => Promise<void>;
  handleOverride: (body: ScreeningOverrideRequest) => Promise<void>;
  handlePolicyChange: (criticalIds: string[]) => Promise<void>;
  closeDrawer: () => void;
  handleDeleteCandidate: (resumeId: string) => Promise<void>;
  setSortKey: (k: SortKey) => void;
  setTierFilter: (f: TierFilter) => void;
  setError: (e: string | null) => void;
  refreshLeaderboard: () => Promise<void>;
  filteredAndSorted: ScreeningLeaderboardItem[];
}

const POLL_INTERVAL_MS = 3000;

export function useCandidateScreening(): UseCandidateScreeningReturn {
  const [jdId, setJdIdState] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<ScreeningLeaderboardItem[]>([]);
  const [totalCandidates, setTotalCandidates] = useState(0);
  const [screeningSpec, setScreeningSpec] = useState<UseCandidateScreeningReturn["screeningSpec"]>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<CandidateEvaluationDetail | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isScreening, setIsScreening] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [uploadResult, setUploadResult] = useState<BatchResumeUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("rank");
  const [tierFilter, setTierFilter] = useState<TierFilter>("ALL");

  const currentJdIdRef = useRef<string | null>(null);
  const detailRequestRef = useRef(0);

  const setJdId = useCallback((id: string) => {
    if (id === currentJdIdRef.current) return;
    detailRequestRef.current++;
    setSelectedCandidate(null);
    setIsDrawerOpen(false);
    setCandidates([]);
    setTotalCandidates(0);
    setScreeningSpec(null);
    setJdIdState(id);
    currentJdIdRef.current = id;
  }, []);

  const refreshLeaderboard = useCallback(async () => {
    const id = currentJdIdRef.current;
    if (!id) return;
    try {
      const data = await fetchScreeningLeaderboard(id);
      if (currentJdIdRef.current !== id) return;
      setCandidates(data.candidates);
      setTotalCandidates(data.total_candidates);
      setScreeningSpec(data);
    } catch (e: unknown) {
      // silently fail during polling to avoid UI flicker
    }
  }, []);

  const isPolling = candidates.some(
    (candidate) => candidate.evaluation_id !== null && (candidate.status === "QUEUED" || candidate.status === "ANALYZING")
  );
  useEffect(() => {
    if (!isPolling) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    function scheduleRefresh() {
      timer = setTimeout(async () => {
        await refreshLeaderboard();
        if (!stopped) scheduleRefresh();
      }, POLL_INTERVAL_MS);
    }
    scheduleRefresh();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [jdId, isPolling, refreshLeaderboard]);

  const handleUpload = useCallback(async (files: File[]) => {
    const id = currentJdIdRef.current;
    if (!id) { setError("Select a Job Description first."); return; }
    setIsUploading(true);
    setError(null);
    try {
      const result = await uploadCandidateResumes(id, files);
      setUploadResult(result);
      await refreshLeaderboard();
      if (result.failed.length > 0 && result.uploaded.length === 0) {
        setError(`All uploads failed: ${result.failed.map((f) => f.error).join("; ")}`);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  }, [refreshLeaderboard]);

  const queueScreening = useCallback(async (resumeIds?: string[]) => {
    const id = currentJdIdRef.current;
    if (!id) { setError("Select a Job Description first."); return; }
    setIsScreening(true);
    setError(null);
    try {
      await triggerScreening(id, screeningSpec?.spec_version_id ?? undefined, resumeIds);
      if (currentJdIdRef.current !== id) return;
      await refreshLeaderboard();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Screening trigger failed.");
      await refreshLeaderboard();
    } finally {
      setIsScreening(false);
    }
  }, [refreshLeaderboard, screeningSpec]);

  const handleScreenAll = useCallback(() => queueScreening(), [queueScreening]);

  const openCandidateDetail = useCallback(async (resumeId: string, evaluationId?: string) => {
    const id = currentJdIdRef.current;
    if (!id) return;
    const request = ++detailRequestRef.current;
    setIsLoadingDetail(true);
    setIsDrawerOpen(true);
    try {
      const detail = await fetchCandidateDetail(id, resumeId, evaluationId);
      if (detailRequestRef.current === request) setSelectedCandidate(detail);
    } catch (e: unknown) {
      if (detailRequestRef.current === request) {
        setError(e instanceof Error ? e.message : "Failed to load candidate detail.");
        setIsDrawerOpen(false);
      }
    } finally {
      if (detailRequestRef.current === request) setIsLoadingDetail(false);
    }
  }, []);

  const closeDrawer = useCallback(() => {
    detailRequestRef.current++;
    setIsDrawerOpen(false);
    setSelectedCandidate(null);
  }, []);

  const handleScreenCandidate = useCallback(async (resumeId: string) => {
    closeDrawer();
    await queueScreening([resumeId]);
  }, [closeDrawer, queueScreening]);

  const handleOverride = useCallback(async (body: ScreeningOverrideRequest) => {
    const id = currentJdIdRef.current;
    const resumeId = selectedCandidate?.candidate_resume_id;
    if (!id || !resumeId) throw new Error("Open the candidate's current evaluation.");
    const request = detailRequestRef.current;
    await saveScreeningOverride(id, resumeId, body);
    await refreshLeaderboard();
    if (detailRequestRef.current === request) await openCandidateDetail(resumeId);
  }, [openCandidateDetail, refreshLeaderboard, selectedCandidate]);

  const handlePolicyChange = useCallback(async (criticalIds: string[]) => {
    const id = currentJdIdRef.current;
    const specId = screeningSpec?.spec_version_id;
    if (!id || !specId) throw new Error("Open the current finalized specification.");
    await updateScreeningPolicy(id, specId, criticalIds);
    await refreshLeaderboard();
  }, [refreshLeaderboard, screeningSpec]);

  const handleDeleteCandidate = useCallback(async (resumeId: string) => {
    const id = currentJdIdRef.current;
    if (!id) return;
    try {
      await deleteCandidateResume(id, resumeId);
      setCandidates((prev) => prev.filter((c) => c.candidate_resume_id !== resumeId));
      setTotalCandidates((n) => Math.max(0, n - 1));
      if (selectedCandidate?.candidate_resume_id === resumeId) closeDrawer();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Delete failed.");
    }
  }, [selectedCandidate, closeDrawer]);

  // Filtered + sorted derived list
  const filteredAndSorted: ScreeningLeaderboardItem[] = (() => {
    let list = [...candidates];
    if (tierFilter === "REVIEW") {
      list = list.filter((c) => c.status === "NEEDS_REVIEW" || c.status === "PARSE_FAILED");
    } else if (tierFilter === "OUTDATED") {
      list = list.filter((c) => c.spec_outdated);
    } else if (tierFilter !== "ALL") {
      list = list.filter((c) => (c.effective_tier ?? c.match_tier) === tierFilter);
    }
    list.sort((a, b) => {
      if (sortKey === "score") return (b.overall_score ?? -1) - (a.overall_score ?? -1);
      if (sortKey === "name") return (a.candidate_name ?? "").localeCompare(b.candidate_name ?? "");
      if (sortKey === "experience") return (b.total_experience_years ?? 0) - (a.total_experience_years ?? 0);
      if (sortKey === "tier") {
        const order = { STRONG_MATCH: 0, POTENTIAL_MATCH: 1, NOT_A_FIT: 2 };
        const aTier = a.effective_tier ?? a.match_tier;
        const bTier = b.effective_tier ?? b.match_tier;
        return (aTier ? order[aTier] : 3) - (bTier ? order[bTier] : 3);
      }
      return (a.rank ?? Number.MAX_SAFE_INTEGER) - (b.rank ?? Number.MAX_SAFE_INTEGER);
    });
    return list;
  })();

  return {
    jdId, candidates, totalCandidates, screeningSpec, selectedCandidate, isDrawerOpen,
    isUploading, isScreening, isPolling, isLoadingDetail, uploadResult, error,
    sortKey, tierFilter,
    setJdId, handleUpload, handleScreenAll, openCandidateDetail, closeDrawer, handleScreenCandidate,
    handleOverride, handlePolicyChange,
    handleDeleteCandidate, setSortKey, setTierFilter, setError, refreshLeaderboard,
    filteredAndSorted,
  };
}
