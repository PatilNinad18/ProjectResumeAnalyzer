import styles from "./ScreeningPage.module.css";
import { useRef, useCallback } from "react";
import ResumeUploadZone from "./ResumeUploadZone";
import CandidateLeaderboard from "./CandidateLeaderboard";
import CandidateDetailDrawer from "./CandidateDetailDrawer";
import { useCandidateScreening, type SortKey, type TierFilter } from "@/hooks/useCandidateScreening";

interface ScreeningPageProps {
  /** The JD ID to screen against. If not set, shows a placeholder. */
  jdId?: string | null;
  jdTitle?: string | null;
}

export default function ScreeningPage({ jdId, jdTitle }: ScreeningPageProps) {
  const screening = useCandidateScreening();

  // Set the JD whenever it changes via prop
  const prevJdIdRef = useRef<string | null>(null);
  if (jdId && jdId !== prevJdIdRef.current) {
    prevJdIdRef.current = jdId;
    screening.setJdId(jdId);
    screening.refreshLeaderboard();
  }

  if (!jdId) {
    return (
      <div className={styles.emptyState}>
        <div className={styles.emptyIcon}>📋</div>
        <h2 className={styles.emptyTitle}>No Job Description Selected</h2>
        <p className={styles.emptyDesc}>
          Complete the JD Workflow and finalize Specification v2 first, then return here to screen candidates.
        </p>
      </div>
    );
  }

  return (
    <div className={styles.screeningPage}>
      {/* Page header */}
      <div className={styles.pageHeader}>
        <div className={styles.pageHeaderLeft}>
          <h1 className={styles.pageTitle}>
            🎯 Candidate Screening
          </h1>
          {jdTitle && (
            <span className={styles.pageSubtitle}>
              Specification v2 — {jdTitle}
            </span>
          )}
        </div>
        <div className={styles.pageHeaderRight}>
          {screening.isPolling && (
            <span className={styles.pollingBadge}>⟳ Evaluating…</span>
          )}
          <span className={styles.countBadge}>
            {screening.totalCandidates} candidate{screening.totalCandidates !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* Error banner */}
      {screening.error && (
        <div className={styles.errorBanner}>
          ⚠️ {screening.error}
          <button onClick={() => screening.setError(null)} className={styles.errorClose}>✕</button>
        </div>
      )}

      {/* Upload zone */}
      <ResumeUploadZone
        isUploading={screening.isUploading}
        isScreening={screening.isScreening}
        uploadResult={screening.uploadResult}
        hasResumes={screening.totalCandidates > 0}
        onUpload={screening.handleUpload}
        onScreenAll={screening.handleScreenAll}
      />

      {/* Leaderboard */}
      {screening.totalCandidates > 0 && (
        <CandidateLeaderboard
          candidates={screening.filteredAndSorted}
          totalCandidates={screening.totalCandidates}
          sortKey={screening.sortKey}
          tierFilter={screening.tierFilter}
          onSortChange={(k) => screening.setSortKey(k as SortKey)}
          onTierFilterChange={(f) => screening.setTierFilter(f as TierFilter)}
          onSelectCandidate={screening.openCandidateDetail}
          onDeleteCandidate={screening.handleDeleteCandidate}
        />
      )}

      {/* Detail drawer */}
      <CandidateDetailDrawer
        isOpen={screening.isDrawerOpen}
        isLoading={screening.isLoadingDetail}
        candidate={screening.selectedCandidate}
        onClose={screening.closeDrawer}
      />
    </div>
  );
}
