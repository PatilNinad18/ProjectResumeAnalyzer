import { useMemo, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import { API_BASE, type BatchTask, type ClarificationsResponse, type CanonicalAmbiguityItem } from "@/lib/api";
import type { useJDBatch } from "@/hooks/useJDBatch";
import styles from "./BatchUploadSection.module.css";

type BatchHook = ReturnType<typeof useJDBatch>;

export interface BatchUploadSectionProps {
  state: BatchHook;
  onLaunchAgent: (agentName: string, task: BatchTask, markdown: string) => Promise<void>;
}

const taskStatusLabel: Record<BatchTask["status"], string> = {
  QUEUED: "Queued",
  PROCESSING: "Processing",
  COMPLETED: "Analysis complete",
  FAILED: "Failed",
  CANCELLED: "Cancelled",
};

function isFinalSpecification(data: ClarificationsResponse | null) {
  return Boolean(data && data.lifecycle_status === "FINALIZED");
}

function ambiguityStatement(ambiguity: CanonicalAmbiguityItem) {
  return ambiguity.statement?.trim() || "Unspecified ambiguity";
}

function distinctAmbiguities(data: ClarificationsResponse) {
  const questionEvidence = data.questions.flatMap((question) => [
    question.question_text.toLowerCase(),
    question.rationale?.toLowerCase() ?? "",
  ]);
  return data.ambiguities
    .map((ambiguity, index) => ({ ambiguity, index }))
    .filter(({ ambiguity }) => {
      const statement = ambiguityStatement(ambiguity).toLowerCase();
      return !questionEvidence.some((evidence) => evidence.includes(statement));
    });
}

function synthesizeMissingInfoQuestions(data: ClarificationsResponse | null): ClarificationsResponse["questions"] {
  if (!data?.missing_information?.length) return [];
  const synthesized: ClarificationsResponse["questions"] = [];
  const existingKeys = new Set(data.questions.map((q) => q.question_key));

  for (const mi of data.missing_information) {
    const raw = (mi.field || mi.parameter_name || mi.name || "").toString().trim();
    if (!raw) continue;
    const low = raw.toLowerCase();
    let key = `missing_${low.replace(/[^a-z0-9]+/g, "_")}`;
    let questionText = `What is the expectation for ${raw.replace(/_/g, " ")}?`;
    let structured: Array<{ label: string; description: string }> = [];

    if (low.includes("salary") || low.includes("compensation")) {
      key = "compensation_salary_range";
      questionText = "Is a salary range or compensation band available for this role?";
      structured = [
        { label: "Competitive / Market standard", description: "Calibrated to prevailing competitive market compensation benchmarks." },
        { label: "Yes, I can provide it", description: "Provide a specific compensation band or hourly rate." },
        { label: "Not disclosed", description: "Confidential or discussed during interview rounds." },
      ];
    } else if (low.includes("team") || low.includes("size")) {
      key = "org_metadata_team_size";
      questionText = "What is the expected team size or reporting structure for this role?";
      structured = [
        { label: "1–5 people", description: "Small, tight-knit founding engineering team or pod." },
        { label: "6–15 people", description: "Mid-sized dedicated product engineering team." },
        { label: "16–50 people", description: "Broad engineering organization." },
        { label: "50+ people", description: "Large enterprise engineering division." },
        { label: "Not specified / Flexible", description: "Keep team size flexible for screening." },
      ];
    } else if (low.includes("location") || low.includes("hybrid") || low.includes("remote")) {
      key = "location_hybrid_arrangement";
      questionText = `Location is listed as '${raw}'. What does the hybrid arrangement look like?`;
      structured = [
        { label: "Hybrid (2–3 days in office)", description: "Regular weekly in-office collaboration." },
        { label: "On-site full-time", description: "100% on-site required." },
        { label: "Flexible / mostly remote", description: "Remote work permitted with office visits as needed." },
      ];
    } else {
      structured = [
        { label: "Disclosing now", description: `Provide clarification for ${raw}.` },
        { label: "Not required / Unspecified", description: "Do not evaluate or disqualify on this criterion." },
      ];
    }

    if (!existingKeys.has(key)) {
      synthesized.push({
        question_key: key,
        question_text: questionText,
        category: "MISSING_METADATA",
        priority: "OPTIONAL",
        field_target: `job_context.${low.includes("team") ? "team_size" : low.includes("salary") ? "salary_range" : key}`,
        status: "UNANSWERED",
        short_topic: low.includes("team") ? "Team size" : low.includes("salary") ? "Salary" : raw,
        structured_options: structured,
      });
      existingKeys.add(key);
    }
  }
  return synthesized;
}

function missingInfoLabel(item: Record<string, unknown>, index: number) {
  const name = item.parameter_name ?? item.field ?? item.name;
  return typeof name === "string" && name.trim()
    ? name.replace(/_/g, " ")
    : `Missing information ${index + 1}`;
}

export default function BatchUploadSection({ state, onLaunchAgent }: BatchUploadSectionProps) {
  const [agentName, setAgentName] = useState("");
  const [isLaunchingAgent, setIsLaunchingAgent] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const launchInFlight = useRef(false);
  const {
    batch,
    selectedTask,
    selectedTaskId,
    setSelectedTaskId,
    clarifications,
    selectedAnswers,
    setAnswer,
    markdown,
    hasEnrichedMarkdown,
    hasResolvedMarkdown,
    specViewMode,
    setSpecViewMode,
    markdownDiff,
    setMarkdownDiff,
    showDiffHighlights,
    setShowDiffHighlights,
    diffChangedCount,
    isResolving,
    isLoadingTask,
    error,
    taskError,
    resolveSelectedTask,
    retryTask,
    cancelTask,
  } = state;
  const isDiffActive = Boolean(
    markdownDiff &&
    diffChangedCount > 0 &&
    specViewMode === "resolved"
  );
  const pendingAmbiguities = clarifications ? distinctAmbiguities(clarifications) : [];
  const synthesizedMissing = clarifications ? synthesizeMissingInfoQuestions(clarifications) : [];
  // Combine technical ambiguity questions from Ollama/engine and missing metadata (team size, salary)
  // Deduplicate by question_key and short_topic
  const actionableQuestions = useMemo(() => {
    if (!clarifications) return [];
    const questions = clarifications.questions ?? [];
    const missing = synthesizeMissingInfoQuestions(clarifications);

    const genuineQuestions = questions.filter((q) => {
      const low = (q.short_topic || q.question_text || "").toLowerCase();
      return !low.includes("compliance disclaimer") && !low.includes("equal opportunity");
    });

    const seenKeys = new Set<string>();
    const seenTopics = new Set<string>();
    const result: typeof questions = [];

    for (const q of [...genuineQuestions, ...missing]) {
      const topicLow = (q.short_topic || q.question_text).toLowerCase();
      if (!seenKeys.has(q.question_key) && !seenTopics.has(topicLow)) {
        seenKeys.add(q.question_key);
        seenTopics.add(topicLow);
        result.push(q);
      }
    }
    return result;
  }, [clarifications]);
  const hasOpenAmbiguities = Boolean(
    actionableQuestions.some((question) =>
      question.status !== "ANSWERED" &&
      question.status !== "EXPLICITLY_UNSPECIFIED"
    ) || pendingAmbiguities.some(({ ambiguity }) => ambiguity.ta_confirmation_required !== false)
  );
  const finalSpecification = isFinalSpecification(clarifications);
  const hasClarificationItems = actionableQuestions.length > 0 || pendingAmbiguities.length > 0;
  const hasUnansweredItems =
    actionableQuestions.some((question) => !(selectedAnswers[question.question_key] ?? "").trim()) ||
    pendingAmbiguities.some(
      ({ ambiguity, index }) =>
        ambiguity.ta_confirmation_required !== false &&
        !(selectedAnswers[`amb_${index}`] ?? "").trim()
    );

  const nextUnfinishedTask = batch?.tasks.find(
    (t) => t.task_id !== selectedTask?.task_id && t.status === "COMPLETED" && t.lifecycle_status !== "FINALIZED"
  ) || batch?.tasks.find((t) => t.task_id !== selectedTask?.task_id);

  async function handleResolveAndNext() {
    await resolveSelectedTask();
    if (nextUnfinishedTask) {
      setSelectedTaskId(nextUnfinishedTask.task_id);
    }
  }

  async function handleLaunchAgent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = agentName.trim();
    if (!selectedTask || !markdown?.trim() || !name || launchInFlight.current) return;

    launchInFlight.current = true;
    setIsLaunchingAgent(true);
    setLaunchError(null);
    try {
      await onLaunchAgent(name, selectedTask, markdown);
    } catch (error) {
      setLaunchError(error instanceof Error ? error.message : "Could not launch the agent. Please try again.");
    } finally {
      launchInFlight.current = false;
      setIsLaunchingAgent(false);
    }
  }

  if (!batch) return null;

  return (
    <section className={styles.section} aria-labelledby="batch-jd-heading">
      <header className={styles.header}>
        <div>
          <h4 id="batch-jd-heading">Multi-JD Sequential Queue & Analysis</h4>
          <p>Each uploaded JD is analyzed in a deterministic sequential queue to prevent engine overload.</p>
        </div>
        <a
          className="btn-secondary"
          href={`${API_BASE}/api/batches/${encodeURIComponent(batch.batch_id)}/downloads.zip`}
          download
        >
          Download completed files (.zip)
        </a>
      </header>

      <div className={styles.batch}>
        {error && <div className="alert-error" role="alert">{error}</div>}
        <div className={styles.summary}>
          <strong>Batch progress</strong>
          <span>{batch.completed} / {batch.total} complete</span>
          <span>{batch.processing} processing</span>
          <span>{batch.queued} queued</span>
          <span>{batch.failed} failed</span>
          <span>{batch.cancelled} cancelled</span>
        </div>
        <div className={styles.progressTrack} role="progressbar" aria-valuenow={batch.progress_percent} aria-valuemin={0} aria-valuemax={100}>
          <div className={styles.progressFill} style={{ width: `${batch.progress_percent}%` }} />
        </div>

        {/* Horizontal Tabbed Selector Bar */}
        <div className={styles.taskTabBar} role="tablist" aria-label="Batch Job Descriptions">
          {batch.tasks.map((task) => {
            const isFinalized = task.status === "COMPLETED" && task.lifecycle_status === "FINALIZED";
            const badgeClass = isFinalized
              ? styles.badge_finalized
              : styles[`badge_${task.status.toLowerCase()}`] || styles.badge_queued;
            const badgeText = isFinalized
              ? "✓ Finalized v2"
              : task.status === "PROCESSING"
              ? `Processing (${task.progress_percent}%)`
              : task.status === "QUEUED"
              ? "Pending"
              : task.stage_label || taskStatusLabel[task.status];

            return (
              <button
                key={task.task_id}
                type="button"
                role="tab"
                aria-selected={task.task_id === selectedTaskId}
                className={`${styles.taskTab} ${task.task_id === selectedTaskId ? styles.taskTabActive : ""}`}
                onClick={() => setSelectedTaskId(task.task_id)}
                disabled={isLaunchingAgent}
              >
                <span className={styles.taskTabTitle} title={task.title || task.filename}>
                  {task.title || task.filename}
                </span>
                <span className={`${styles.taskTabBadge} ${badgeClass}`}>
                  {badgeText}
                </span>
              </button>
            );
          })}
        </div>

        <div className={styles.selectorRow}>
          <label htmlFor="batch-jd-selector">Or choose from list:</label>
          <select
            id="batch-jd-selector"
            value={selectedTaskId ?? ""}
            onChange={(event) => setSelectedTaskId(event.currentTarget.value || null)}
            disabled={isLaunchingAgent}
          >
            <option value="" disabled>Select a JD</option>
            {batch.tasks.map((task) => (
              <option key={task.task_id} value={task.task_id}>
                {task.filename} — {task.stage_label || taskStatusLabel[task.status]}
                {task.status === "PROCESSING" ? ` (${task.progress_percent}%)` : ""}
              </option>
            ))}
          </select>
          {selectedTask && (
            <div className={styles.taskActions}>
              {(selectedTask.status === "QUEUED" || selectedTask.status === "PROCESSING") && (
                <button type="button" className="btn-ghost-dark" onClick={() => void cancelTask(selectedTask)}>Cancel JD</button>
              )}
              {(selectedTask.status === "FAILED" || selectedTask.status === "CANCELLED") && (
                <button type="button" className="btn-ghost-dark" onClick={() => void retryTask(selectedTask)}>Retry JD</button>
              )}
            </div>
          )}
        </div>

        {selectedTask && (
          <article className={styles.taskDetail}>
            <h5>{selectedTask.title}</h5>
            {selectedTask.status !== "COMPLETED" && (
              <p className={styles.statusMessage}>
                {selectedTask.stage_label || taskStatusLabel[selectedTask.status]}
                {selectedTask.status === "PROCESSING" ? ` — ${selectedTask.progress_percent}%` : ""}
              </p>
            )}
            {selectedTask.status === "FAILED" && selectedTask.error_message && (
              <div className="alert-error" role="alert">{selectedTask.error_message}</div>
            )}
            {isLoadingTask && <p>Loading this JD&apos;s ambiguities and Markdown…</p>}
            {taskError && <div className="alert-error" role="alert">{taskError}</div>}

            {selectedTask.status === "COMPLETED" && !isLoadingTask && clarifications && (
              <>
                {markdown && (
                  <section className={styles.markdown}>
                    <div className={styles.markdownHeader}>
                      <div>
                        <h5>{finalSpecification ? "Final Resolved Specification (v2)" : "Specification"}</h5>
                        <div className={styles.viewToggle}>
                          <button
                            type="button"
                            className={specViewMode === "baseline" ? styles.activeView : ""}
                            onClick={() => setSpecViewMode("baseline")}
                          >
                            Baseline (v1)
                          </button>
                          <button
                            type="button"
                            className={specViewMode === "enriched" ? styles.activeView : ""}
                            onClick={() => setSpecViewMode("enriched")}
                            disabled={!hasEnrichedMarkdown}
                            title={hasEnrichedMarkdown ? "Show enriched Markdown" : "Enriched Markdown is not available for this JD"}
                          >
                            Enriched
                          </button>
                          {hasResolvedMarkdown && (
                            <button
                              type="button"
                              className={specViewMode === "resolved" ? styles.activeView : ""}
                              onClick={() => setSpecViewMode("resolved")}
                            >
                              Resolved (v2)
                            </button>
                          )}
                          {isDiffActive && (
                            <button
                              type="button"
                              onClick={() => setShowDiffHighlights(!showDiffHighlights)}
                              style={{
                                fontSize: "0.78rem",
                                padding: "4px 12px",
                                borderRadius: "20px",
                                border: `1px solid ${showDiffHighlights ? "#10b981" : "#d1d5db"}`,
                                background: showDiffHighlights ? "#ecfdf5" : "#f9fafb",
                                color: showDiffHighlights ? "#065f46" : "#6b7280",
                                cursor: "pointer",
                                fontWeight: 600,
                                display: "flex",
                                alignItems: "center",
                                gap: "5px",
                                marginLeft: "8px",
                              }}
                            >
                              <span>{showDiffHighlights ? "✦" : "○"}</span>
                              Highlight Changes ({diffChangedCount})
                            </button>
                          )}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => {
                          const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
                          const url = URL.createObjectURL(blob);
                          const link = document.createElement("a");
                          link.href = url;
                          link.download = `${selectedTask.filename.replace(/\.[^.]+$/, "")}-specification.md`;
                          link.click();
                          setTimeout(() => URL.revokeObjectURL(url), 1000);
                        }}
                      >
                        Download .md
                      </button>
                    </div>
                    {!hasEnrichedMarkdown && specViewMode === "enriched" && (
                      <p className={styles.statusMessage}>Enrichment is unavailable; showing the deterministic baseline specification.</p>
                    )}
                    {/* What Changed Banner (shown after ambiguity resolution with diffs) */}
                    {isDiffActive && (
                      <div
                        style={{
                          background: "linear-gradient(135deg, #ecfdf5 0%, #f0fdf4 100%)",
                          border: "1px solid #a7f3d0",
                          borderRadius: "10px",
                          padding: "14px 18px",
                          margin: "12px 0 16px 0",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: "12px",
                          flexWrap: "wrap",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                          <span style={{ fontSize: "1.25rem" }}>✨</span>
                          <div>
                            <div style={{ fontWeight: 700, fontSize: "0.95rem", color: "#065f46" }}>
                              Specification v2 Generated with Your Clarifications
                            </div>
                            <div style={{ fontSize: "0.82rem", color: "#047857", marginTop: "2px" }}>
                              {diffChangedCount} line{diffChangedCount !== 1 ? "s" : ""} updated — highlighted below in green
                            </div>
                          </div>
                        </div>
                        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                          <button
                            type="button"
                            onClick={() => setShowDiffHighlights(!showDiffHighlights)}
                            style={{
                              fontSize: "0.78rem",
                              padding: "4px 12px",
                              borderRadius: "20px",
                              border: "1px solid #10b981",
                              background: showDiffHighlights ? "#10b981" : "#fff",
                              color: showDiffHighlights ? "#fff" : "#065f46",
                              cursor: "pointer",
                              fontWeight: 600,
                            }}
                          >
                            {showDiffHighlights ? "✦ Highlights ON" : "○ Highlights OFF"}
                          </button>
                          <button
                            type="button"
                            onClick={() => setMarkdownDiff(null)}
                            style={{
                              fontSize: "0.78rem",
                              padding: "4px 10px",
                              borderRadius: "20px",
                              border: "1px solid #d1d5db",
                              background: "#fff",
                              color: "#6b7280",
                              cursor: "pointer",
                            }}
                          >
                            ✕ Dismiss
                          </button>
                        </div>
                      </div>
                    )}
                    <div className={styles.markdownBody}>
                      {isDiffActive && showDiffHighlights && markdownDiff ? (
                        <div style={{ lineHeight: 1.7 }}>
                          {markdownDiff.map((seg, idx) => (
                            <div
                              key={idx}
                              style={
                                seg.changed
                                  ? {
                                      background: "rgba(16, 185, 129, 0.10)",
                                      borderLeft: "3px solid #10b981",
                                      paddingLeft: "10px",
                                      marginLeft: "-10px",
                                      borderRadius: "0 4px 4px 0",
                                      position: "relative",
                                    }
                                  : {}
                              }
                            >
                              {seg.changed && (
                                <span
                                  style={{
                                    position: "absolute",
                                    right: "8px",
                                    top: "2px",
                                    fontSize: "0.65rem",
                                    fontWeight: 700,
                                    color: "#059669",
                                    background: "#d1fae5",
                                    padding: "1px 5px",
                                    borderRadius: "3px",
                                    letterSpacing: "0.02em",
                                  }}
                                >
                                  ✦ UPDATED
                                </span>
                              )}
                              <ReactMarkdown>{seg.text || " "}</ReactMarkdown>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <ReactMarkdown>{markdown}</ReactMarkdown>
                      )}
                    </div>
                  </section>
                )}

                <section className={styles.ambiguities}>
                  <h5>
                    {hasOpenAmbiguities
                      ? `Ambiguities for ${selectedTask.filename}`
                      : (actionableQuestions.length || pendingAmbiguities.length)
                        ? "Ambiguities reviewed"
                        : "No ambiguities found for this JD"}
                  </h5>

                  {actionableQuestions.map((question) => (
                    <div className={styles.question} key={question.question_key}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "6px" }}>
                        {question.short_topic && (
                          <span style={{
                            display: "inline-block",
                            padding: "2px 8px",
                            fontSize: "0.72rem",
                            fontWeight: 700,
                            borderRadius: "4px",
                            backgroundColor: "rgba(59, 130, 246, 0.12)",
                            color: "var(--accent-text, #2563eb)",
                            letterSpacing: "0.03em",
                            border: "1px solid rgba(59, 130, 246, 0.25)",
                          }}>
                            {question.short_topic}
                          </span>
                        )}
                        <label htmlFor={`batch-${selectedTask.jd_id}-${question.question_key}`} style={{ fontWeight: 600, margin: 0 }}>
                          {question.question_text}
                        </label>
                      </div>
                      {question.structured_options?.length ? (
                        <div className={styles.options}>
                          {question.structured_options.map((option) => {
                            const isSelected =
                              selectedAnswers[question.question_key] === option.label ||
                              selectedAnswers[question.question_key]?.startsWith(`${option.label}:`);
                            return (
                              <button
                                type="button"
                                key={option.label}
                                className={styles.option}
                                aria-pressed={isSelected}
                                onClick={() => {
                                  const val = option.description
                                    ? `${option.label}: ${option.description}`
                                    : option.label;
                                  setAnswer(question.question_key, val);
                                }}
                              >
                                <strong>{option.label}</strong>
                                {option.description && <span>{option.description}</span>}
                              </button>
                            );
                          })}
                        </div>
                      ) : null}
                      <textarea
                        id={`batch-${selectedTask.jd_id}-${question.question_key}`}
                        value={selectedAnswers[question.question_key] ?? ""}
                        onChange={(event) => setAnswer(question.question_key, event.currentTarget.value)}
                        placeholder="Choose an option or enter a clarification"
                      />
                    </div>
                  ))}

                  {pendingAmbiguities.map(({ ambiguity, index }) => (
                    <div className={styles.question} key={ambiguity.id || ambiguity.ambiguity_id || index}>
                      <label htmlFor={`batch-${selectedTask.jd_id}-ambiguity-${index}`}>
                        <strong>{ambiguityStatement(ambiguity)}</strong>
                      </label>
                      {ambiguity.why_ambiguous && <p>{ambiguity.why_ambiguous}</p>}
                      {ambiguity.suggested_interpretation && (
                        <p>Suggested interpretation: {ambiguity.suggested_interpretation}</p>
                      )}
                      {ambiguity.ta_confirmation_required === false ? (
                        <p className={styles.finalNotice}>TA decision recorded.</p>
                      ) : (
                        <textarea
                          id={`batch-${selectedTask.jd_id}-ambiguity-${index}`}
                          value={selectedAnswers[`amb_${index}`] ?? ""}
                          onChange={(event) => setAnswer(`amb_${index}`, event.currentTarget.value)}
                          placeholder="Enter the TA decision for this ambiguity"
                        />
                      )}
                    </div>
                  ))}



                  {hasClarificationItems && (
                    <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" }}>
                      <button
                        type="button"
                        className="btn-primary"
                        onClick={() => void resolveSelectedTask()}
                        disabled={isResolving || hasUnansweredItems}
                      >
                        {isResolving ? "Regenerating Markdown…" : "Regenerate Markdown with solved ambiguities"}
                      </button>
                      {batch.tasks.length > 1 && nextUnfinishedTask && (
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => void handleResolveAndNext()}
                          disabled={isResolving || hasUnansweredItems}
                        >
                          {isResolving ? "Resolving…" : "Resolve & Next JD →"}
                        </button>
                      )}
                    </div>
                  )}
                  {hasOpenAmbiguities && finalSpecification && (
                    <p className={styles.finalNotice}>All ambiguities are resolved. This JD has a final specification.</p>
                  )}
                </section>
              </>
            )}
            {selectedTask.status === "COMPLETED" && !isLoadingTask && markdown?.trim() && (
              <section className={styles.launchAgent} aria-labelledby="batch-launch-agent-heading">
                <h5 id="batch-launch-agent-heading">Chat with this job description</h5>
                <form className={styles.launchAgentForm} onSubmit={(event) => void handleLaunchAgent(event)}>
                  <label htmlFor={`batch-agent-name-${selectedTask.jd_id}`}>Agent name</label>
                  <input
                    id={`batch-agent-name-${selectedTask.jd_id}`}
                    type="text"
                    value={agentName}
                    onChange={(event) => setAgentName(event.currentTarget.value)}
                    placeholder="Enter an agent name"
                    maxLength={120}
                    required
                    disabled={isLaunchingAgent}
                  />
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={isLaunchingAgent || !agentName.trim()}
                  >
                    {isLaunchingAgent ? "Launching agent…" : "Launch the agent"}
                  </button>
                </form>
                {launchError && <div className="alert-error" role="alert">{launchError}</div>}
              </section>
            )}
          </article>
        )}
      </div>
    </section>
  );
}
