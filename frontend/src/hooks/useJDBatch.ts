"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  cancelBatchTask,
  createJDBatch,
  getClarifications,
  getJDBatch,
  getMarkdown,
  refreshBatchTaskArtifacts,
  resolveClarifications,
  retryBatchTask,
  waitForTask,
  type BatchTask,
  type ClarificationsResponse,
  type JDBatch,
} from "@/lib/api";

const isBatchActive = (batch: JDBatch) =>
  batch.tasks.some((task) => task.status === "QUEUED" || task.status === "PROCESSING");

export function useJDBatch(projectId: string) {
  const [files, setFiles] = useState<File[]>([]);
  const [batch, setBatch] = useState<JDBatch | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [clarifications, setClarifications] = useState<ClarificationsResponse | null>(null);
  const [answersByJd, setAnswersByJd] = useState<Record<string, Record<string, string>>>({});
  const [baselineMarkdown, setBaselineMarkdown] = useState<string | null>(null);
  const [enrichedMarkdown, setEnrichedMarkdown] = useState<string | null>(null);
  const [resolvedMarkdown, setResolvedMarkdown] = useState<string | null>(null);
  const [hasEnrichedMarkdown, setHasEnrichedMarkdown] = useState(false);
  const [hasResolvedMarkdown, setHasResolvedMarkdown] = useState(false);
  const [specViewMode, setSpecViewMode] = useState<"baseline" | "enriched" | "resolved">("enriched");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResolving, setIsResolving] = useState(false);
  const [isLoadingTask, setIsLoadingTask] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [artifactRevision, setArtifactRevision] = useState(0);
  const resolveLock = useRef(false);

  const selectedTask = useMemo(
    () => batch?.tasks.find((task) => task.task_id === selectedTaskId) ?? null,
    [batch, selectedTaskId]
  );
  const selectedAnswers = selectedTask ? answersByJd[selectedTask.jd_id] ?? {} : {};

  const markdown = useMemo(() => {
    if (specViewMode === "resolved" && resolvedMarkdown) return resolvedMarkdown;
    if (specViewMode === "baseline") return baselineMarkdown || enrichedMarkdown || "";
    return enrichedMarkdown || baselineMarkdown || resolvedMarkdown || "";
  }, [specViewMode, resolvedMarkdown, enrichedMarkdown, baselineMarkdown]);

  const isEnrichedView = specViewMode !== "baseline";
  const setIsEnrichedView = (val: boolean) => {
    if (val) {
      setSpecViewMode(hasResolvedMarkdown ? "resolved" : "enriched");
    } else {
      setSpecViewMode("baseline");
    }
  };

  async function submitBatch() {
    if (!files.length || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    setTaskError(null);
    setClarifications(null);
    setBaselineMarkdown(null);
    setEnrichedMarkdown(null);
    setResolvedMarkdown(null);
    setHasEnrichedMarkdown(false);
    setHasResolvedMarkdown(false);
    setAnswersByJd({});
    setSelectedTaskId(null);
    try {
      const created = await createJDBatch(projectId, files);
      setBatch(created);
      setSelectedTaskId(created.tasks[0]?.task_id ?? null);
      setFiles([]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not start batch processing.");
    } finally {
      setIsSubmitting(false);
    }
  }

  useEffect(() => {
    if (!batch?.batch_id || !isBatchActive(batch)) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const poll = async () => {
      try {
        const latest = await getJDBatch(batch.batch_id, controller.signal);
        if (stopped) return;
        setBatch(latest);
        if (isBatchActive(latest)) timer = setTimeout(poll, 1800);
      } catch (cause) {
        if (stopped || (cause instanceof Error && cause.name === "AbortError")) return;
        setError(cause instanceof Error ? cause.message : "Could not refresh batch status.");
        timer = setTimeout(poll, 5000);
      }
    };

    timer = setTimeout(poll, 1800);
    return () => {
      stopped = true;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [batch?.batch_id, batch?.status, batch?.tasks]);

  useEffect(() => {
    if (!batch || !selectedTask) {
      setClarifications(null);
      setBaselineMarkdown(null);
      setEnrichedMarkdown(null);
      setResolvedMarkdown(null);
      setHasEnrichedMarkdown(false);
      setHasResolvedMarkdown(false);
      return;
    }
    if (selectedTask.status !== "COMPLETED") {
      setClarifications(null);
      setBaselineMarkdown(null);
      setEnrichedMarkdown(null);
      setResolvedMarkdown(null);
      setHasEnrichedMarkdown(false);
      setHasResolvedMarkdown(false);
      setIsLoadingTask(false);
      setTaskError(null);
      return;
    }

    const controller = new AbortController();
    let stopped = false;
    setIsLoadingTask(true);
    setTaskError(null);
    setClarifications(null);
    setBaselineMarkdown(null);
    setEnrichedMarkdown(null);
    setResolvedMarkdown(null);
    setHasEnrichedMarkdown(false);
    setHasResolvedMarkdown(false);

    Promise.all([
      getClarifications(selectedTask.jd_id),
      getMarkdown(selectedTask.jd_id, false, 1).catch(() => getMarkdown(selectedTask.jd_id, false)),
      getMarkdown(selectedTask.jd_id, true, 1).catch(() => getMarkdown(selectedTask.jd_id, true)),
      getMarkdown(selectedTask.jd_id, undefined).catch(() => null),
    ])
      .then(([response, baseline, enriched, latest]) => {
        if (stopped) return;
        setClarifications(response);
        setBaselineMarkdown(baseline?.markdown ?? null);
        setEnrichedMarkdown(enriched?.markdown ?? null);
        setHasEnrichedMarkdown(enriched?.is_enriched === true);

        const hasResolved = Boolean(latest && latest.specification_version >= 2);
        if (hasResolved && latest) {
          setResolvedMarkdown(latest.markdown);
          setHasResolvedMarkdown(true);
          setSpecViewMode("resolved");
        } else {
          setResolvedMarkdown(null);
          setHasResolvedMarkdown(false);
          setSpecViewMode(enriched?.is_enriched ? "enriched" : "baseline");
        }

        setAnswersByJd((current) => {
          const next = { ...(current[selectedTask.jd_id] ?? {}) };
          for (const question of response.questions) {
            const existing = question.answer_text || question.answer || "";
            if (existing && next[question.question_key] === undefined) {
              next[question.question_key] = existing;
            }
          }
          return { ...current, [selectedTask.jd_id]: next };
        });
      })
      .catch((cause: unknown) => {
        if (!stopped) {
          setTaskError(cause instanceof Error ? cause.message : "Could not load this JD's results.");
        }
      })
      .finally(() => {
        if (!stopped) setIsLoadingTask(false);
      });

    return () => {
      stopped = true;
      controller.abort();
    };
  }, [batch?.batch_id, selectedTask?.jd_id, selectedTask?.status, artifactRevision]);

  function setAnswer(questionKey: string, value: string) {
    if (!selectedTask) return;
    setAnswersByJd((current) => ({
      ...current,
      [selectedTask.jd_id]: {
        ...(current[selectedTask.jd_id] ?? {}),
        [questionKey]: value,
      },
    }));
  }

  async function resolveSelectedTask() {
    if (!batch || !selectedTask || !clarifications || resolveLock.current) return;
    const unansweredAmbiguities = clarifications.ambiguities
      .map((ambiguity, index) => ({ ambiguity, index }))
      .filter(({ ambiguity, index }) =>
        ambiguity.ta_confirmation_required !== false &&
        !(selectedAnswers[`amb_${index}`] ?? "").trim()
      );
    if (unansweredAmbiguities.length) {
      setTaskError("Answer each ambiguity for this JD before generating its final Markdown.");
      return;
    }
    resolveLock.current = true;
    setIsResolving(true);
    setTaskError(null);
    try {
      await resolveClarifications(selectedTask.jd_id, selectedAnswers);
      await waitForTask(selectedTask.jd_id, "resolve");
      await refreshBatchTaskArtifacts(batch.batch_id, selectedTask.task_id);
      const latest = await getJDBatch(batch.batch_id);
      setBatch(latest);
      setArtifactRevision((revision) => revision + 1);
    } catch (cause) {
      setTaskError(cause instanceof Error ? cause.message : "Could not resolve this JD's ambiguities.");
    } finally {
      resolveLock.current = false;
      setIsResolving(false);
    }
  }

  async function retryTask(task: BatchTask) {
    if (!batch) return;
    try {
      await retryBatchTask(batch.batch_id, task.task_id);
      setBatch(await getJDBatch(batch.batch_id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not retry this JD.");
    }
  }

  async function cancelTask(task: BatchTask) {
    if (!batch) return;
    try {
      await cancelBatchTask(batch.batch_id, task.task_id);
      setBatch(await getJDBatch(batch.batch_id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not cancel this JD.");
    }
  }

  return {
    files,
    setFiles,
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
    resolvedMarkdown,
    hasEnrichedMarkdown,
    hasResolvedMarkdown,
    specViewMode,
    setSpecViewMode,
    isEnrichedView,
    setIsEnrichedView,
    isSubmitting,
    isResolving,
    isLoadingTask,
    error,
    taskError,
    submitBatch,
    resolveSelectedTask,
    retryTask,
    cancelTask,
  };
}
