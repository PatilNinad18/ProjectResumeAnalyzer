import { useState } from "react";
import styles from "./CandidateDetailDrawer.module.css";
import { MATCH_TIER_LABELS, resumeProfileDownloadUrl, type CandidateEvaluationDetail, type RequirementEvaluation, type MatchTier, type ScreeningOverrideRequest } from "@/lib/screening_api";

interface CandidateDetailDrawerProps {
  isOpen: boolean;
  isLoading: boolean;
  candidate: CandidateEvaluationDetail | null;
  onClose: () => void;
  onOpenRun: (resumeId: string, evaluationId: string) => Promise<void>;
  onOverride: (request: ScreeningOverrideRequest) => Promise<void>;
  onRerun?: (resumeId: string) => Promise<void>;
}

const TIER_META: Record<MatchTier, { label: string; cls: string; icon: string }> = {
  STRONG_MATCH: { label: "Strong Match", cls: styles.tierStrong, icon: "🟢" },
  POTENTIAL_MATCH: { label: "Potential Match", cls: styles.tierPotential, icon: "🟡" },
  NOT_A_FIT: { label: "Limited evidence", cls: styles.tierNotFit, icon: "🔴" },
};

function EvalStatusBadge({ status, grade }: { status: string; grade?: RequirementEvaluation["evidence_grade"] }) {
  const cls = status === "MET" ? styles.statusMet : status === "PARTIALLY_MET" ? styles.statusPartial : styles.statusNone;
  const label = grade === "MENTION" ? "MENTION ONLY" : status === "MET" ? "✓ MET" : status === "PARTIALLY_MET" ? "⟳ PARTIALLY MET" : "⚪ NOT EVIDENCED";
  return <span className={`${styles.statusBadge} ${cls}`}>{label}</span>;
}

const points = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });

function RequirementRow({ eval: ev }: { eval: RequirementEvaluation }) {
  const quotes = ev.evidence_quotes?.length ? ev.evidence_quotes : ev.evidence_quote ? [ev.evidence_quote] : [];
  return (
    <div className={styles.reqRow}>
      <div className={styles.reqHeader}>
        <span className={styles.reqText}>{ev.requirement}</span>
        {ev.critical && <span className={styles.reviewChip}>Critical</span>}
        <EvalStatusBadge status={ev.status} grade={ev.evidence_grade} />
      </div>
      {ev.points_earned != null && ev.points_available != null && (
        <p className={styles.reasoning}>{points.format(ev.points_earned)} / {points.format(ev.points_available)} points</p>
      )}
      {quotes.length > 0 && (
        <blockquote className={styles.evidenceQuote}>
          <span className={styles.evidenceLabel}>📄 Resume Evidence</span>
          {quotes.map((quote) => <div className={styles.evidenceText} key={quote}>“{quote}”</div>)}
        </blockquote>
      )}
      {ev.reasoning && (
        <p className={styles.reasoning}>{ev.reasoning}</p>
      )}
    </div>
  );
}

function OverrideForm({ candidate, onSave }: { candidate: CandidateEvaluationDetail; onSave: CandidateDetailDrawerProps["onOverride"] }) {
  const [tier, setTier] = useState<MatchTier>(candidate.recruiter_override_tier ?? candidate.match_tier ?? "POTENTIAL_MATCH");
  const [score, setScore] = useState(candidate.recruiter_override_score?.toString() ?? "");
  const [reviewer, setReviewer] = useState(candidate.overridden_by ?? "");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <details className={styles.reviewPanel}>
      <summary>Override match recommendation</summary>
      <form className={styles.reviewForm} onSubmit={async (e) => {
        e.preventDefault();
        if (!candidate.evaluation_id) return;
        setSaving(true);
        setError(null);
        try {
          await onSave({
            evaluation_id: candidate.evaluation_id,
            override_tier: tier,
            override_score: score === "" ? null : Number(score),
            overridden_by: reviewer.trim(),
            reason: reason.trim(),
          });
          setReason("");
        } catch (e: unknown) {
          setError(e instanceof Error ? e.message : "Could not save the override.");
        } finally {
          setSaving(false);
        }
      }}>
        <label>Recruiter name<input value={reviewer} onChange={(e) => setReviewer(e.target.value)} maxLength={255} required /></label>
        <label>Match tier<select value={tier} onChange={(e) => setTier(e.target.value as MatchTier)}>
          {Object.entries(MATCH_TIER_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
        </select></label>
        <label>Override score (optional)<input type="number" min={0} max={100} step={1} value={score} onChange={(e) => setScore(e.target.value)} /></label>
        <label>Reason<textarea value={reason} onChange={(e) => setReason(e.target.value)} minLength={10} maxLength={2000} required rows={3} /></label>
        {error && <p role="alert">{error}</p>}
        <button type="submit" className={styles.reviewButton} disabled={saving || !reviewer.trim() || reason.trim().length < 10}>
          {saving ? "Saving…" : "Save override"}
        </button>
      </form>
    </details>
  );
}

export default function CandidateDetailDrawer({ isOpen, isLoading, candidate, onClose, onOpenRun, onOverride, onRerun }: CandidateDetailDrawerProps) {
  if (!isOpen) return null;

  const tier = candidate?.match_tier ? TIER_META[candidate.match_tier] : null;
  const profile = candidate?.candidate_profile;
  const mhSummary = candidate?.must_haves_summary;
  const tenureEvidence = candidate?.score_breakdown?.tenure_evidence ?? [];
  const breakdown = candidate?.score_breakdown;
  const mustHaveEvals = candidate?.detailed_evaluations.filter((e) => e.category === "must_have") ?? [];
  const preferredEvals = candidate?.detailed_evaluations.filter((e) => e.category === "preferred") ?? [];

  return (
    <>
      {/* Backdrop */}
      <div className={styles.backdrop} onClick={onClose} />

      {/* Drawer panel */}
      <aside className={styles.drawer}>
        {/* Header */}
        <div className={styles.drawerHeader}>
          <div className={styles.headerLeft}>
            <h2 className={styles.drawerTitle}>
              {profile?.candidate_name ?? candidate?.candidate_resume_id?.slice(0, 8) ?? "Candidate"}
            </h2>
            {tier && (
              <span className={`${styles.tierBadge} ${tier.cls}`}>
                {tier.icon} {tier.label}
              </span>
            )}
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">✕</button>
        </div>

        {isLoading ? (
          <div className={styles.loadingState}>
            <span className={styles.spinner} />
            <span>Loading evaluation…</span>
          </div>
        ) : !candidate ? null : (
          <div className={styles.drawerBody}>
            {candidate.review_reason && (
              <div className={styles.mhSummary}>
                <span className={styles.sectionTitle}>Needs review</span>
                <p className={styles.reasoning}>{candidate.review_reason}</p>
                {candidate.status === "NEEDS_REVIEW" && !candidate.spec_outdated && onRerun && (
                  <button type="button" className={styles.reviewButton} onClick={() => onRerun(candidate.candidate_resume_id)}>Rerun screening</button>
                )}
              </div>
            )}
            {candidate.spec_outdated && (
              <div className={styles.reviewPanel}>
                <strong>Outdated result</strong>
                <p>This run used an earlier specification or evaluator. Rerun screening for a current rank.</p>
                {onRerun && <button type="button" className={styles.reviewButton} onClick={() => onRerun(candidate.candidate_resume_id)}>Rerun screening</button>}
              </div>
            )}

            {/* Score + profile summary */}
            <div className={styles.summaryRow}>
              {candidate.overall_score !== null && <div className={styles.scoreBig}>
                <span className={styles.scoreNum} style={{
                  color: candidate.overall_score >= 75 ? "#16a34a"
                       : candidate.overall_score >= 50 ? "#d97706" : "#dc2626"
                }}>
                  {candidate.overall_score}%
                </span>
                <span className={styles.scoreSubLabel}>ATS match score</span>
              </div>}
              <div className={styles.profileMeta}>
                {profile?.email && <span>✉️ {profile.email}</span>}
                {profile?.phone && <span>📞 {profile.phone}</span>}
                {profile?.total_experience_years != null && (
                  <span>🗓 {profile.total_experience_years}y experience</span>
                )}
                {profile?.current_or_last_title && (
                  <span>💼 {profile.current_or_last_title}</span>
                )}
              </div>
            </div>

            {candidate.has_resume_profile && (
              <div className={styles.profileDownloads} aria-label="Structured resume files">
                <a href={resumeProfileDownloadUrl(candidate.job_description_id, candidate.candidate_resume_id, "json")}>Download resume JSON</a>
                <a href={resumeProfileDownloadUrl(candidate.job_description_id, candidate.candidate_resume_id, "md")}>Download resume Markdown</a>
              </div>
            )}
            {candidate.evaluation_id && (
              <div className={styles.reviewPanel}>
                <strong>Screening run</strong>
                <p>Specification v{candidate.specification_version} · {candidate.provenance?.model_name ? `Ollama · ${candidate.provenance.model_name}` : candidate.provenance?.evaluator_engine ?? "Legacy evaluator"}</p>
                {candidate.spec_checksum && <p>Specification checksum <code className={styles.digest}>{candidate.spec_checksum}</code></p>}
                {candidate.quote_verification_pass === false && <p>One or more excerpts could not be verified.</p>}
                {candidate.runs.length > 1 && (
                  <label className={styles.runSelector}>View previous runs
                    <select value={candidate.evaluation_id} onChange={(e) => onOpenRun(candidate.candidate_resume_id, e.target.value)}>
                      {candidate.runs.map((run) => <option key={run.evaluation_id} value={run.evaluation_id}>
                        v{run.specification_version} · {run.overall_score !== null ? `${run.overall_score}%` : run.status} · {run.created_at ? new Date(run.created_at).toLocaleString() : "Unknown date"}
                      </option>)}
                    </select>
                  </label>
                )}
              </div>
            )}

            {candidate.recruiter_override_tier && (
              <div className={styles.reviewPanel}>
                <strong>Recruiter override</strong>
                <p>{MATCH_TIER_LABELS[candidate.recruiter_override_tier]}{candidate.recruiter_override_score != null ? ` · ${candidate.recruiter_override_score}%` : ""} · {candidate.overridden_by}</p>
                <p>{candidate.override_reason}</p>
                {candidate.override_history.length > 0 && <details>
                  <summary>Override history</summary>
                  <ul>
                    {candidate.override_history.map((event, i) => <li key={event.created_at + i}>
                      <strong>{event.reviewer ?? "Recruiter"} · {MATCH_TIER_LABELS[event.tier]}{event.score != null ? ` · ${event.score}%` : ""}</strong>
                      <p>{new Date(event.created_at).toLocaleString()} · {event.reason}</p>
                    </li>)}
                  </ul>
                </details>}
              </div>
            )}
            {candidate.can_override && <OverrideForm key={candidate.evaluation_id} candidate={candidate} onSave={onOverride} />}

            {!!candidate.score_breakdown?.critical_to_verify?.length && (
              <div className={styles.reviewPanel}>
                <strong>Critical requirements to verify</strong>
                <ul>{candidate.score_breakdown.critical_to_verify.map((requirement) => <li key={requirement}>{requirement}</li>)}</ul>
              </div>
            )}

            {((breakdown?.tenure_base_weight ?? 0) > 0 || tenureEvidence.length > 0) && (
              <div className={styles.mhSummary}>
                <span className={styles.sectionTitle}>Overall experience</span>
                {breakdown?.experience_points != null && (
                  <p className={styles.reasoning}>
                    {points.format(breakdown.experience_points)} / {points.format(100 * breakdown.tenure_base_weight / breakdown.active_weight_total)} points
                    {breakdown.experience_years_required != null && ` · ${breakdown.experience_years_required} years required`}
                  </p>
                )}
                {tenureEvidence.length > 0 && <ul>
                  {tenureEvidence.map((quote) => <li key={quote}>{quote}</li>)}
                </ul>}
              </div>
            )}

            {/* Must-have summary bar */}
            {mhSummary && (
              <div className={styles.mhSummary}>
                <span className={styles.sectionTitle}>Must-Have Coverage</span>
                <div className={styles.mhCounts}>
                  <span className={styles.mhMet}>✓ {mhSummary.met} MET</span>
                  <span className={styles.mhPartial}>⟳ {mhSummary.partially_met} PARTIAL</span>
                  <span className={styles.mhNone}>⚪ {mhSummary.not_evidenced} NOT EVIDENCED</span>
                  <span className={styles.mhTotal}>of {mhSummary.total}</span>
                </div>
              </div>
            )}

            {/* Skills */}
            {profile?.skills && profile.skills.length > 0 && (
              <div className={styles.section}>
                <span className={styles.sectionTitle}>Detected Skills</span>
                <div className={styles.skillTags}>
                  {profile.skills.slice(0, 20).map((s) => (
                    <span key={s} className={styles.skillTag}>{s}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Must-have evaluations */}
            {mustHaveEvals.length > 0 && (
              <div className={styles.section}>
                <span className={styles.sectionTitle}>Must-Have Requirements</span>
                <div className={styles.reqList}>
                  {mustHaveEvals.map((ev, i) => <RequirementRow key={i} eval={ev} />)}
                </div>
              </div>
            )}

            {/* Preferred evaluations */}
            {preferredEvals.length > 0 && (
              <div className={styles.section}>
                <span className={styles.sectionTitle}>Preferred Qualifications</span>
                <div className={styles.reqList}>
                  {preferredEvals.map((ev, i) => <RequirementRow key={i} eval={ev} />)}
                </div>
              </div>
            )}

            {/* Validation checkpoints */}
            {candidate.validation_checkpoints.length > 0 && (
              <div className={styles.section}>
                <span className={styles.sectionTitle}>⚠️ Interview Verification Checkpoints</span>
                <p className={styles.checkpointNote}>
                  These requirements were NOT EVIDENCED or PARTIALLY MET in the resume.
                  Verify via interview before making a decision.
                </p>
                <div className={styles.checkpointList}>
                  {candidate.validation_checkpoints.map((cp, i) => (
                    <div key={i} className={styles.checkpointItem}>
                      <span className={styles.checkpointReq}>{cp.requirement}</span>
                      <EvalStatusBadge status={cp.status} />
                      <div className={styles.interviewQ}>
                        🎤 <em>{cp.interview_question}</em>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Timeline Observations */}
            {candidate.timeline_observations && candidate.timeline_observations.length > 0 && (
              <div className={styles.section}>
                <span className={styles.sectionTitle}>⏱️ Timeline Observations (Neutral Notes)</span>
                <ul className={styles.redFlagList}>
                  {candidate.timeline_observations.map((flag, i) => (
                    <li key={i} className={styles.redFlagItem}>{flag}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Interview questions */}
            {candidate.tailored_interview_questions.length > 0 && (
              <div className={styles.section}>
                <span className={styles.sectionTitle}>🎤 Tailored Interview Questions</span>
                <ol className={styles.iqList}>
                  {candidate.tailored_interview_questions.map((q, i) => (
                    <li key={i} className={styles.iqItem}>{q}</li>
                  ))}
                </ol>
              </div>
            )}

          </div>
        )}
      </aside>
    </>
  );
}
