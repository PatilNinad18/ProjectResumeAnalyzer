import styles from "./ScreeningPage.module.css";
import { useEffect, useState } from "react";
import ResumeUploadZone from "./ResumeUploadZone";
import CandidateLeaderboard from "./CandidateLeaderboard";
import CandidateDetailDrawer from "./CandidateDetailDrawer";
import BatchScreening from "./BatchScreening";
import { useCandidateScreening, type SortKey, type TierFilter } from "@/hooks/useCandidateScreening";
import { listJDs, type SavedJD } from "@/lib/api";
import type { ScreeningCriterion } from "@/lib/screening_api";

interface ScreeningPageProps {
  preferredJdId: string | null;
  onSelectJd: (id: string) => void;
  initialBatchIds: string[];
}

function CriticalRequirements({ criteria, onSave }: { criteria: ScreeningCriterion[]; onSave: (ids: string[]) => Promise<void> }) {
  const [selected, setSelected] = useState(() => criteria.filter((item) => item.critical).map((item) => item.requirement_id));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const changed = criteria.some((item) => item.critical !== selected.includes(item.requirement_id));
  return (
    <details className={styles.criticalPolicy}>
      <summary>Critical requirements</summary>
      <p>Mark must-haves that need full evidence before a result can qualify as a strong match. Saving creates a new specification and marks earlier results for rerun.</p>
      <div className={styles.criticalOptions}>
        {criteria.map((item) => (
          <label key={item.requirement_id}>
            <input type="checkbox" checked={selected.includes(item.requirement_id)} disabled={saving} onChange={(e) => {
              const checked = e.currentTarget.checked;
              setSelected((ids) => checked ? [...ids, item.requirement_id] : ids.filter((id) => id !== item.requirement_id));
            }} />
            {item.text}
          </label>
        ))}
      </div>
      {error && <p role="alert">{error}</p>}
      <button type="button" className={styles.policyButton} disabled={!changed || saving} onClick={async () => {
        setSaving(true);
        setError(null);
        try {
          await onSave(selected);
        } catch (e: unknown) {
          setError(e instanceof Error ? e.message : "Could not save critical requirements.");
        } finally {
          setSaving(false);
        }
      }}>{saving ? "Saving…" : "Save critical requirements"}</button>
    </details>
  );
}

export default function ScreeningPage({ preferredJdId, onSelectJd, initialBatchIds }: ScreeningPageProps) {
  const [jobs, setJobs] = useState<SavedJD[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobsRevision, setJobsRevision] = useState(0);
  const [leaderboardRevision, setLeaderboardRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void listJDs(controller.signal).then((savedJobs) => {
      if (!controller.signal.aborted) {
        setJobs(savedJobs);
        setError(null);
      }
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) {
        setError(cause instanceof Error ? cause.message : "Could not load jobs.");
      }
    });
    return () => controller.abort();
  }, [jobsRevision]);

  const finalizedJobs = (jobs ?? []).filter((job) => job.lifecycle_status === "FINALIZED" && job.spec_version_id);
  const selectedJob = preferredJdId ? finalizedJobs.find((job) => job.jd_id === preferredJdId) : finalizedJobs[0];

  return (
    <div className={styles.screeningPage}>
      <h1 className={styles.pageTitle}>Candidate Screening</h1>
      {error && (
        <div className={styles.errorBanner} role="alert">
          {error}
          <button type="button" className={styles.policyButton} onClick={() => setJobsRevision((n) => n + 1)}>Retry</button>
        </div>
      )}
      {!jobs && !error && <p role="status">Loading saved jobs…</p>}
      {jobs && finalizedJobs.length === 0 && (
        <div className={styles.emptyState}>
          <h2 className={styles.emptyTitle}>No finalized jobs</h2>
          <p className={styles.emptyDesc}>Finalize a job specification in Workflow to make it available for screening.</p>
        </div>
      )}
      {finalizedJobs.length > 0 && (
        <>
          <label className={styles.jobSelector}>
            Job description
            <select value={selectedJob?.jd_id ?? ""} onChange={(event) => onSelectJd(event.currentTarget.value)}>
              {!selectedJob && <option value="" disabled>Choose a finalized job</option>}
              {finalizedJobs.map((job) => (
                <option key={job.jd_id} value={job.jd_id}>{job.title} · {job.project_id}</option>
              ))}
            </select>
          </label>
          {!selectedJob && <p role="status">The requested job has no current finalized specification.</p>}
          {finalizedJobs.length > 1 && (
            <BatchScreening
              jobs={finalizedJobs}
              initialJobIds={initialBatchIds}
              onViewJob={onSelectJd}
              onRequestsFinished={() => {
                setLeaderboardRevision((n) => n + 1);
                setJobsRevision((n) => n + 1);
              }}
            />
          )}
          {selectedJob && (
            <JobScreening
              key={selectedJob.jd_id}
              job={selectedJob}
              leaderboardRevision={leaderboardRevision}
              onPolicySaved={() => setJobsRevision((n) => n + 1)}
            />
          )}
        </>
      )}
    </div>
  );
}

function JobScreening({ job, leaderboardRevision, onPolicySaved }: {
  job: SavedJD;
  leaderboardRevision: number;
  onPolicySaved: () => void;
}) {
  const screening = useCandidateScreening();
  const { setJdId, refreshLeaderboard, screeningSpec } = screening;

  useEffect(() => {
    setJdId(job.jd_id);
    void refreshLeaderboard();
  }, [job.jd_id, job.spec_version_id, leaderboardRevision, refreshLeaderboard, setJdId]);

  return (
    <section className={styles.jobScreening} aria-labelledby="screening-job-title">
      {/* Page header */}
      <div className={styles.pageHeader}>
        <div className={styles.pageHeaderLeft}>
          <h2 id="screening-job-title" className={styles.jobTitle}>{job.title}</h2>
          <span className={styles.pageSubtitle}>
            {screeningSpec?.specification_version != null ? `Specification v${screeningSpec.specification_version}` : "Loading specification…"}
          </span>
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

      {screeningSpec?.spec_finalized && screeningSpec.criteria.length > 0 && (
        <CriticalRequirements key={screeningSpec.spec_version_id} criteria={screeningSpec.criteria} onSave={async (criticalIds) => {
          await screening.handlePolicyChange(criticalIds);
          onPolicySaved();
        }} />
      )}

      {/* Upload zone */}
      <ResumeUploadZone
        isUploading={screening.isUploading}
        isScreening={screening.isScreening}
        uploadResult={screening.uploadResult}
        hasResumes={screening.totalCandidates > 0}
        specFinalized={screeningSpec?.spec_finalized === true}
        specificationVersion={screeningSpec?.specification_version ?? null}
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
        onOpenRun={screening.openCandidateDetail}
        onOverride={screening.handleOverride}
        onRerun={screeningSpec?.spec_finalized ? screening.handleScreenCandidate : undefined}
      />
    </section>
  );
}
