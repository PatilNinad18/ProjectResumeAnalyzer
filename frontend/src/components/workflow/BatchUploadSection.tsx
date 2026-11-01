import ReactMarkdown from "react-markdown";
import { API_BASE, type BatchTask, type ClarificationsResponse, type CanonicalAmbiguityItem } from "@/lib/api";
import type { useJDBatch } from "@/hooks/useJDBatch";
import styles from "./BatchUploadSection.module.css";

type BatchHook = ReturnType<typeof useJDBatch>;

export interface BatchUploadSectionProps {
  state: BatchHook;
}

const taskStatusLabel: Record<BatchTask["status"], string> = {
  QUEUED: "Queued",
  PROCESSING: "Processing",
  COMPLETED: "Analysis complete",
  FAILED: "Failed",
  CANCELLED: "Cancelled",
};

function isFinalSpecification(data: ClarificationsResponse | null) {
  return Boolean(data && (
    data.lifecycle_status === "FINALIZED" ||
    (data.questions.every((question) => question.status === "ANSWERED" || question.status === "EXPLICITLY_UNSPECIFIED") &&
      data.ambiguities.every((ambiguity) => ambiguity.ta_confirmation_required === false))
  ));
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

function changedEnrichedLines(baseline: string, enriched: string) {
  const available = new Map<string, number>();
  for (const line of baseline.split(/\r?\n/)) {
    available.set(line, (available.get(line) ?? 0) + 1);
  }
  const changed: Array<{ line: string; index: number }> = [];
  enriched.split(/\r?\n/).forEach((line, index) => {
    const remaining = available.get(line) ?? 0;
    if (remaining > 0) {
      available.set(line, remaining - 1);
    } else if (line.trim()) {
      changed.push({ line, index: index + 1 });
    }
  });
  return changed;
}

function missingInfoLabel(item: Record<string, unknown>, index: number) {
  const name = item.parameter_name ?? item.field ?? item.name;
  return typeof name === "string" && name.trim() ? name.replace(/_/g, " ") : `Missing information ${index + 1}`;
}

export default function BatchUploadSection({ state }: BatchUploadSectionProps) {
  const {
    batch,
    selectedTask,
    selectedTaskId,
    setSelectedTaskId,
    clarifications,
    selectedAnswers,
    setAnswer,
    markdown,
    baselineMarkdown,
    enrichedMarkdown,
    hasEnrichedMarkdown,
    isEnrichedView,
    setIsEnrichedView,
    comparison,
    comparisonError,
    isResolving,
    isLoadingTask,
    error,
    taskError,
    resolveSelectedTask,
    retryTask,
    cancelTask,
  } = state;
  const pendingAmbiguities = clarifications ? distinctAmbiguities(clarifications) : [];
  const actionableQuestions = clarifications?.questions ?? [];
  const hasOpenAmbiguities = Boolean(
    actionableQuestions.some((question) =>
      question.status !== "ANSWERED" &&
      question.status !== "EXPLICITLY_UNSPECIFIED"
    ) || pendingAmbiguities.some(({ ambiguity }) => ambiguity.ta_confirmation_required !== false)
  );
  const finalSpecification = isFinalSpecification(clarifications);
  const changedLines = baselineMarkdown && enrichedMarkdown
    ? changedEnrichedLines(baselineMarkdown, enrichedMarkdown)
    : [];
  const requirementChanges = comparison
    ? [...comparison.diff.added, ...comparison.diff.modified]
    : [];

  if (!batch) return null;

  return (
    <section className={styles.section} aria-labelledby="batch-jd-heading">
      <header className={styles.header}>
        <div>
          <h4 id="batch-jd-heading">Parallel JD processing</h4>
          <p>Each uploaded JD runs independently with its own progress, ambiguities, and Markdown.</p>
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

          <div className={styles.selectorRow}>
            <label htmlFor="batch-jd-selector">View job description</label>
            <select
              id="batch-jd-selector"
              value={selectedTaskId ?? ""}
              onChange={(event) => setSelectedTaskId(event.currentTarget.value || null)}
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
                  <section className={styles.ambiguities}>
                    <h5>
                      {hasOpenAmbiguities
                        ? `Ambiguities for ${selectedTask.filename}`
                        : (actionableQuestions.length || pendingAmbiguities.length || clarifications.missing_information.length)
                          ? "Ambiguities reviewed"
                          : "No ambiguities found for this JD"}
                    </h5>

                    {actionableQuestions.map((question) => (
                      <div className={styles.question} key={question.question_key}>
                        <label htmlFor={`batch-${selectedTask.jd_id}-${question.question_key}`}>
                          {question.question_text}
                        </label>
                        {question.structured_options?.length ? (
                          <div className={styles.options}>
                            {question.structured_options.map((option) => (
                              <button
                                type="button"
                                key={option.label}
                                className={styles.option}
                                aria-pressed={selectedAnswers[question.question_key] === option.label}
                                onClick={() => setAnswer(question.question_key, option.label)}
                              >
                                <strong>{option.label}</strong>
                                {option.description && <span>{option.description}</span>}
                              </button>
                            ))}
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

                    {clarifications.missing_information.length > 0 && (
                      <div className={styles.missingInfo}>
                        <strong>Missing information (not assumed)</strong>
                        <ul>
                          {clarifications.missing_information.map((item, index) => (
                            <li key={`${missingInfoLabel(item, index)}-${index}`}>
                              <strong>{missingInfoLabel(item, index)}:</strong>{" "}
                              {String(item.why_it_matters ?? item.reason ?? item.recommended_action ?? "Not specified in the JD.")}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {hasOpenAmbiguities && !finalSpecification && (
                      <button
                        type="button"
                        className="btn-primary"
                        onClick={() => void resolveSelectedTask()}
                        disabled={isResolving || actionableQuestions.some(
                          (question) =>
                            question.status !== "ANSWERED" &&
                            question.status !== "EXPLICITLY_UNSPECIFIED" &&
                            !(selectedAnswers[question.question_key] ?? "").trim()
                        ) || pendingAmbiguities.some(
                          ({ ambiguity, index }) =>
                            ambiguity.ta_confirmation_required !== false &&
                            !(selectedAnswers[`amb_${index}`] ?? "").trim()
                        )}
                      >
                        {isResolving ? "Generating final Markdown…" : "Apply answers and generate final Markdown"}
                      </button>
                    )}
                    {finalSpecification && hasOpenAmbiguities && (
                      <p className={styles.finalNotice}>All ambiguities are resolved. This JD has a final specification.</p>
                    )}
                  </section>

                  {markdown && (
                    <section className={styles.markdown}>
                      <div className={styles.markdownHeader}>
                        <div>
                          <h5>{finalSpecification ? "Final Markdown" : "Job Description Markdown"}</h5>
                          <div className={styles.viewToggle}>
                            <button
                              type="button"
                              className={!isEnrichedView ? styles.activeView : ""}
                              onClick={() => setIsEnrichedView(false)}
                            >
                              Deterministic
                            </button>
                            <button
                              type="button"
                              className={isEnrichedView ? styles.activeView : ""}
                              onClick={() => setIsEnrichedView(true)}
                              disabled={!hasEnrichedMarkdown}
                              title={hasEnrichedMarkdown ? "Show enriched Markdown" : "Enriched Markdown is not available for this JD"}
                            >
                              Enriched
                            </button>
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
                      {!hasEnrichedMarkdown && (
                        <p className={styles.statusMessage}>Enrichment is unavailable; showing the deterministic specification.</p>
                      )}
                      {isEnrichedView && hasEnrichedMarkdown && changedLines.length > 0 && (
                        <section className={styles.diffPanel}>
                          <strong>Enrichment changes</strong>
                          <p>Green lines are additions or modifications in the enriched Markdown.</p>
                          <ul>
                            {changedLines.map(({ line, index }) => (
                              <li key={`${index}-${line}`}><code>{line}</code></li>
                            ))}
                          </ul>
                        </section>
                      )}
                      {isEnrichedView && hasEnrichedMarkdown && comparisonError && (
                        <div className="alert-error" role="alert">{comparisonError}</div>
                      )}
                      {isEnrichedView && hasEnrichedMarkdown && comparison && requirementChanges.length > 0 && (
                        <section className={styles.fieldChanges}>
                          <strong>Requirement-level changes</strong>
                          {requirementChanges.map((item) => (
                            <div className={styles.fieldChange} key={item.id}>
                              <span>{item.diff_status === "added" ? "Added" : "Modified"}</span>
                              <p>{item.text}</p>
                              {item.changes?.length ? <small>{item.changes.join(" · ")}</small> : null}
                            </div>
                          ))}
                        </section>
                      )}
                      <div className={styles.markdownBody}><ReactMarkdown>{markdown}</ReactMarkdown></div>
                    </section>
                  )}
                </>
              )}
            </article>
          )}
        </div>
    </section>
  );
}
