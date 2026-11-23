import styles from "./CandidateLeaderboard.module.css";
import type { ScreeningLeaderboardItem, MatchTier } from "@/lib/screening_api";
import type { SortKey, TierFilter } from "@/hooks/useCandidateScreening";

interface CandidateLeaderboardProps {
  candidates: ScreeningLeaderboardItem[];
  totalCandidates: number;
  sortKey: SortKey;
  tierFilter: TierFilter;
  onSortChange: (key: string) => void;
  onTierFilterChange: (filter: string) => void;
  onSelectCandidate: (resumeId: string) => void;
  onDeleteCandidate: (resumeId: string) => void;
}

const TIER_META: Record<MatchTier, { label: string; color: string; icon: string }> = {
  STRONG_MATCH:    { label: "Strong Match",    color: styles.tierStrong,    icon: "🟢" },
  POTENTIAL_MATCH: { label: "Potential Match", color: styles.tierPotential, icon: "🟡" },
  NOT_A_FIT:       { label: "Not a Fit",       color: styles.tierNotFit,    icon: "🔴" },
};

function ScoreRing({ score }: { score: number | null }) {
  if (score === null) return <span className={styles.scoreEmpty}>—</span>;
  const color = score >= 80 ? "#16a34a" : score >= 60 ? "#d97706" : "#dc2626";
  const r = 18;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;
  return (
    <div className={styles.scoreRing} title={`${score}%`}>
      <svg width="44" height="44" viewBox="0 0 44 44">
        <circle cx="22" cy="22" r={r} fill="none" stroke="#e5e7eb" strokeWidth="4" />
        <circle
          cx="22" cy="22" r={r}
          fill="none"
          stroke={color}
          strokeWidth="4"
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
          transform="rotate(-90 22 22)"
        />
      </svg>
      <span className={styles.scoreLabel} style={{ color }}>{score}%</span>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  if (status === "COMPLETED") return null;
  const map: Record<string, string> = {
    QUEUED: styles.pillQueued,
    ANALYZING: styles.pillAnalyzing,
    FAILED: styles.pillFailed,
  };
  return (
    <span className={`${styles.statusPill} ${map[status] ?? ""}`}>
      {status === "ANALYZING" ? "⟳ Analyzing" : status === "QUEUED" ? "Queued" : "Failed"}
    </span>
  );
}

export default function CandidateLeaderboard({
  candidates, totalCandidates, sortKey, tierFilter,
  onSortChange, onTierFilterChange, onSelectCandidate, onDeleteCandidate,
}: CandidateLeaderboardProps) {
  return (
    <div className={styles.leaderboardCard}>
      {/* Controls */}
      <div className={styles.controls}>
        <div className={styles.controlsLeft}>
          <span className={styles.resultCount}>{candidates.length} of {totalCandidates}</span>
          <div className={styles.filterBtns}>
            {(["ALL", "STRONG_MATCH", "POTENTIAL_MATCH", "NOT_A_FIT"] as TierFilter[]).map((f) => (
              <button
                key={f}
                className={`${styles.filterBtn} ${tierFilter === f ? styles.filterActive : ""}`}
                onClick={() => onTierFilterChange(f)}
              >
                {f === "ALL" ? "All" : f === "STRONG_MATCH" ? "🟢 Strong" : f === "POTENTIAL_MATCH" ? "🟡 Potential" : "🔴 Not a Fit"}
              </button>
            ))}
          </div>
        </div>
        <div className={styles.sortRow}>
          <span className={styles.sortLabel}>Sort:</span>
          {(["rank", "score", "tier", "name", "experience"] as SortKey[]).map((k) => (
            <button
              key={k}
              className={`${styles.sortBtn} ${sortKey === k ? styles.sortActive : ""}`}
              onClick={() => onSortChange(k)}
            >
              {k.charAt(0).toUpperCase() + k.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      {candidates.length === 0 ? (
        <div className={styles.noResults}>No candidates match the current filter.</div>
      ) : (
        <div className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>#</th>
                <th>Candidate</th>
                <th>Score</th>
                <th>Tier</th>
                <th>Must-Haves</th>
                <th>Experience</th>
                <th>Gaps</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c) => {
                const tier = c.match_tier ? TIER_META[c.match_tier] : null;
                return (
                  <tr
                    key={c.candidate_resume_id}
                    className={styles.tableRow}
                    onClick={() => c.status === "COMPLETED" && onSelectCandidate(c.candidate_resume_id)}
                    title={c.status !== "COMPLETED" ? `Status: ${c.status}` : "Click to view details"}
                  >
                    <td className={styles.rank}>#{c.rank}</td>
                    <td className={styles.candidateCell}>
                      <div className={styles.candidateName}>
                        {c.candidate_name ?? <em className={styles.unknown}>Unknown</em>}
                      </div>
                      <div className={styles.candidateMeta}>
                        {c.email && <span>{c.email}</span>}
                        <span className={styles.filename}>{c.filename}</span>
                      </div>
                      <StatusPill status={c.status} />
                    </td>
                    <td><ScoreRing score={c.overall_score} /></td>
                    <td>
                      {tier ? (
                        <span className={`${styles.tierBadge} ${tier.color}`}>
                          {tier.icon} {tier.label}
                        </span>
                      ) : <span className={styles.scoreEmpty}>—</span>}
                    </td>
                    <td>
                      <div className={styles.mustHaveBar}>
                        <span className={styles.mustHaveCount}>
                          {c.must_haves_met}/{c.must_haves_total}
                        </span>
                        <div className={styles.barTrack}>
                          <div
                            className={styles.barFill}
                            style={{
                              width: c.must_haves_total > 0
                                ? `${(c.must_haves_met / c.must_haves_total) * 100}%`
                                : "0%",
                              background: c.must_haves_met === c.must_haves_total ? "#16a34a" : "#d97706",
                            }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className={styles.expCell}>
                      {c.total_experience_years != null ? `${c.total_experience_years}y` : "—"}
                    </td>
                    <td>
                      {c.not_evidenced_count > 0 ? (
                        <span className={styles.gapBadge}>
                          ⚠️ {c.not_evidenced_count} gap{c.not_evidenced_count !== 1 ? "s" : ""}
                        </span>
                      ) : c.status === "COMPLETED" ? (
                        <span className={styles.noGap}>✓ None</span>
                      ) : null}
                    </td>
                    <td className={styles.actionCell} onClick={(e) => e.stopPropagation()}>
                      <button
                        className={styles.deleteBtn}
                        onClick={() => onDeleteCandidate(c.candidate_resume_id)}
                        title="Remove candidate"
                      >✕</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
