import styles from "./CandidateDetailDrawer.module.css";
import type { CandidateEvaluationDetail, RequirementEvaluation, ValidationCheckpoint, MatchTier } from "@/lib/screening_api";

interface CandidateDetailDrawerProps {
  isOpen: boolean;
  isLoading: boolean;
  candidate: CandidateEvaluationDetail | null;
  onClose: () => void;
}

const TIER_META: Record<MatchTier, { label: string; cls: string; icon: string }> = {
  STRONG_MATCH:    { label: "Strong Match",    cls: styles.tierStrong,    icon: "🟢" },
  POTENTIAL_MATCH: { label: "Potential Match", cls: styles.tierPotential, icon: "🟡" },
  NOT_A_FIT:       { label: "Not a Fit",       cls: styles.tierNotFit,    icon: "🔴" },
};

function EvalStatusBadge({ status }: { status: string }) {
  const cls = status === "MET" ? styles.statusMet : status === "PARTIALLY_MET" ? styles.statusPartial : styles.statusNone;
  const label = status === "MET" ? "✓ MET" : status === "PARTIALLY_MET" ? "⟳ PARTIALLY MET" : "⚪ NOT EVIDENCED";
  return <span className={`${styles.statusBadge} ${cls}`}>{label}</span>;
}

function RequirementRow({ eval: ev }: { eval: RequirementEvaluation }) {
  const quotes = ev.evidence_quotes?.length ? ev.evidence_quotes : ev.evidence_quote ? [ev.evidence_quote] : [];
  return (
    <div className={styles.reqRow}>
      <div className={styles.reqHeader}>
        <span className={styles.reqText}>{ev.requirement}</span>
        <EvalStatusBadge status={ev.status} />
      </div>
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

export default function CandidateDetailDrawer({ isOpen, isLoading, candidate, onClose }: CandidateDetailDrawerProps) {
  if (!isOpen) return null;

  const tier = candidate?.match_tier ? TIER_META[candidate.match_tier] : null;
  const profile = candidate?.candidate_profile;
  const mhSummary = candidate?.must_haves_summary;
  const tenureEvidence = candidate?.score_breakdown?.tenure_evidence ?? [];
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
              </div>
            )}

            {/* Score + profile summary */}
            <div className={styles.summaryRow}>
              {candidate.overall_score !== null && <div className={styles.scoreBig}>
                <span className={styles.scoreNum} style={{
                  color: (candidate.overall_score ?? 0) >= 80 ? "#16a34a"
                       : (candidate.overall_score ?? 0) >= 60 ? "#d97706" : "#dc2626"
                }}>
                  {candidate.overall_score}%
                </span>
                <span className={styles.scoreSubLabel}>Match Score</span>
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

            {tenureEvidence.length > 0 && (
              <div className={styles.mhSummary}>
                <span className={styles.sectionTitle}>Dates used for experience scoring</span>
                <ul>
                  {tenureEvidence.map((quote) => <li key={quote}>{quote}</li>)}
                </ul>
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

            {/* Red flags */}
            {candidate.red_flags.length > 0 && (
              <div className={styles.section}>
                <span className={styles.sectionTitle}>🚩 Resume Red Flags</span>
                <ul className={styles.redFlagList}>
                  {candidate.red_flags.map((flag, i) => (
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
