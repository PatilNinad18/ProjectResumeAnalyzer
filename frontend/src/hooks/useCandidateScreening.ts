import { useState, useCallback, useRef } from "react";
import {
  uploadCandidateResumes,
  triggerScreening,
  fetchScreeningLeaderboard,
  fetchCandidateDetail,
  deleteCandidateResume,
  type ScreeningLeaderboardItem,
  type CandidateEvaluationDetail,
  type BatchResumeUploadResponse,
} from "@/lib/screening_api";

export type SortKey = "rank" | "score" | "tier" | "name" | "experience";
export type TierFilter = "ALL" | "STRONG_MATCH" | "POTENTIAL_MATCH" | "NOT_A_FIT" | "REVIEW";

export interface UseCandidateScreeningReturn {
  // State
  jdId: string | null;
  candidates: ScreeningLeaderboardItem[];
  totalCandidates: number;
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
  openCandidateDetail: (resumeId: string) => Promise<void>;
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
  const [selectedCandidate, setSelectedCandidate] = useState<CandidateEvaluationDetail | null>(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isScreening, setIsScreening] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [uploadResult, setUploadResult] = useState<BatchResumeUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("rank");
  const [tierFilter, setTierFilter] = useState<TierFilter>("ALL");

  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const currentJdIdRef = useRef<string | null>(null);

  const setJdId = useCallback((id: string) => {
    setJdIdState(id);
    currentJdIdRef.current = id;
  }, []);

  const refreshLeaderboard = useCallback(async () => {
    const id = currentJdIdRef.current;
    if (!id) return;
    try {
      const data = await fetchScreeningLeaderboard(id);
      setCandidates(data.candidates);
      setTotalCandidates(data.total_candidates);
    } catch (e: unknown) {
      // silently fail during polling to avoid UI flicker
    }
  }, []);

  const startPolling = useCallback(() => {
    if (pollTimerRef.current) return;
    setIsPolling(true);
    pollTimerRef.current = setInterval(async () => {
      await refreshLeaderboard();
      // Stop polling when all candidates are in a terminal state
      setCandidates((prev) => {
        const allDone = prev.length > 0 && prev.every(
<<<<<<< HEAD
          (c) => c.status !== "QUEUED" && c.status !== "ANALYZING"
=======
          (c) => c.status === "COMPLETED" || c.status === "FAILED" || c.status === "PARSE_FAILED"
>>>>>>> smartleaven_work/main
        );
        if (allDone && pollTimerRef.current) {
          clearInterval(pollTimerRef.current);
          pollTimerRef.current = null;
          setIsPolling(false);
        }
        return prev;
      });
    }, POLL_INTERVAL_MS);
  }, [refreshLeaderboard]);

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

  const handleScreenAll = useCallback(async () => {
    const id = currentJdIdRef.current;
    if (!id) { setError("Select a Job Description first."); return; }
    setIsScreening(true);
    setError(null);
    try {
      await triggerScreening(id);
      await refreshLeaderboard();
      startPolling();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Screening trigger failed.");
    } finally {
      setIsScreening(false);
    }
  }, [refreshLeaderboard, startPolling]);

  const openCandidateDetail = useCallback(async (resumeId: string) => {
    const id = currentJdIdRef.current;
    if (!id) return;
    setIsLoadingDetail(true);
    setIsDrawerOpen(true);
    try {
      const detail = await fetchCandidateDetail(id, resumeId);
      setSelectedCandidate(detail);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load candidate detail.");
      setIsDrawerOpen(false);
    } finally {
      setIsLoadingDetail(false);
    }
  }, []);

  const closeDrawer = useCallback(() => {
    setIsDrawerOpen(false);
    setSelectedCandidate(null);
  }, []);

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
    } else if (tierFilter !== "ALL") {
      list = list.filter((c) => c.match_tier === tierFilter);
    }
    list.sort((a, b) => {
      if (sortKey === "score") return (b.overall_score ?? -1) - (a.overall_score ?? -1);
      if (sortKey === "name") return (a.candidate_name ?? "").localeCompare(b.candidate_name ?? "");
      if (sortKey === "experience") return (b.total_experience_years ?? 0) - (a.total_experience_years ?? 0);
      if (sortKey === "tier") {
        const order = { STRONG_MATCH: 0, POTENTIAL_MATCH: 1, NOT_A_FIT: 2 };
        return (a.match_tier ? order[a.match_tier] : 3) - (b.match_tier ? order[b.match_tier] : 3);
      }
      return (a.rank ?? Number.MAX_SAFE_INTEGER) - (b.rank ?? Number.MAX_SAFE_INTEGER);
    });
    return list;
  })();

  return {
    jdId, candidates, totalCandidates, selectedCandidate, isDrawerOpen,
    isUploading, isScreening, isPolling, isLoadingDetail, uploadResult, error,
    sortKey, tierFilter,
    setJdId, handleUpload, handleScreenAll, openCandidateDetail, closeDrawer,
    handleDeleteCandidate, setSortKey, setTierFilter, setError, refreshLeaderboard,
    filteredAndSorted,
  };
}
