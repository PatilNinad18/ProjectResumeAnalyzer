"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  uploadJD,
  analyzeJD,
  cancelAnalysis,
  getMarkdown,
  enrichJD,
  getJson,
  getClarifications,
  resolveClarifications,
  pollUntilDone,
  waitForTask,
  cancelTask,
  getComparison,
  type ClarificationsResponse,
  type ProcessingStatus,
  type CompanyDetails,
  type CreatedAgent,
  type ContextComparisonResponse,
  type RequirementDiffItem,
  type AmbiguityItem,
  type JDContextType,
} from "@/lib/api";
import { formatElapsed } from "@/lib/ui";

interface UseJDWorkflowOptions {
  agents: CreatedAgent[];
  setCreatedAgentSuccess: (message: string | null) => void;
  setAgentNameInput: (name: string) => void;
}

export function useJDWorkflow({
  agents,
  setCreatedAgentSuccess,
  setAgentNameInput,
}: UseJDWorkflowOptions) {
  const pollAbortRef = useRef<AbortController | null>(null);

  useEffect(() => () => pollAbortRef.current?.abort(), []);

  const isAbort = (error: unknown) => (error as Error)?.name === "AbortError";

  function computeMarkdownDiff(
    oldMd: string,
    newMd: string
  ): { segments: Array<{ text: string; changed: boolean }>; changedCount: number } {
    const oldSet = new Set(oldMd.split("\n").map((line) => line.trim()));
    const segments = newMd.split("\n").map((line) => ({
      text: line,
      changed: line.trim().length > 0 && !oldSet.has(line.trim()),
    }));
    return {
      segments,
      changedCount: segments.filter((segment) => segment.changed).length,
    };
  }


  // Linear Workflow State (Step 1 -> 5).
  // NOTE: no fake defaults ("Acme Corp") - they ended up on real agents and confused chat context.
  const [companyDetails, setCompanyDetails] = useState<CompanyDetails>({
    companyName: "",
    department: "",
    projectName: "",
  });

  const [isCompanySaved, setIsCompanySaved] = useState(false);


  const [jobTitle, setJobTitle] = useState("");

  const [jdText, setJdText] = useState("");

  const [jdId, setJdId] = useState<string | null>(null);

  const [status, setStatus] = useState<ProcessingStatus | null>(null);

  const [error, setError] = useState<string | null>(null);

  const [markdown, setMarkdown] = useState<string | null>(null);

  const [jsonData, setJsonData] = useState<Record<string, unknown> | null>(null);

  const [specVersion, setSpecVersion] = useState<number>(1);

  const [contextTab, setContextTab] = useState<"markdown" | "json" | "compare">("markdown");

  const [isEnriching, setIsEnriching] = useState<boolean>(false);

  const [isEnrichedView, setIsEnrichedView] = useState<boolean>(false);

  const [enrichError, setEnrichError] = useState<string | null>(null);


  // Progress Indicators & Notifications State
  const [analysisProgress, setAnalysisProgress] = useState<{ percent: number; stageLabel: string }>({
    percent: 0,
    stageLabel: "",
  });

  const [analysisSuccessMsg, setAnalysisSuccessMsg] = useState<string | null>(null);

  const [resolveProgress, setResolveProgress] = useState<{ percent: number; stageLabel: string }>({
    percent: 0,
    stageLabel: "",
  });

  const [resolveError, setResolveError] = useState<string | null>(null);


  // JD Context Comparison State
  const [comparisonData, setComparisonData] = useState<ContextComparisonResponse | null>(null);

  const [isLoadingComparison, setIsLoadingComparison] = useState<boolean>(false);

  const [comparisonBaseContext, setComparisonBaseContext] = useState<JDContextType>("baseline");

  const [comparisonTargetContext, setComparisonTargetContext] = useState<JDContextType>("resolved");

  const [comparisonFilter, setComparisonFilter] = useState<"all" | "added" | "modified" | "removed" | "unchanged">("all");

  const [comparisonViewMode, setComparisonViewMode] = useState<"unified" | "side_by_side">("unified");


  // Ambiguities & Clarification State
  const [clarificationsData, setClarificationsData] = useState<ClarificationsResponse | null>(null);

  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});

  const [activeClarificationIndex, setActiveClarificationIndex] = useState<number>(0);

  const [clarificationViewMode, setClarificationViewMode] = useState<"wizard" | "all">("wizard");

  const [isResolvingClarifications, setIsResolvingClarifications] = useState<boolean>(false);

  const [resolveSuccessMsg, setResolveSuccessMsg] = useState<string | null>(null);


  // Markdown Diff Highlighting State (strictly scoped to specific jdId and specVersion > 1)
  const [diffJdId, setDiffJdId] = useState<string | null>(null);

  const [prevMarkdown, setPrevMarkdown] = useState<string | null>(null);

  const [markdownDiff, setMarkdownDiff] = useState<Array<{ text: string; changed: boolean }> | null>(null);

  const [showDiffHighlights, setShowDiffHighlights] = useState<boolean>(false);

  const [diffChangedCount, setDiffChangedCount] = useState<number>(0);

  const step4Ref = useRef<HTMLDivElement | null>(null);


  // Selected File for multi-format upload (.txt, .pdf, .docx)
  const [selectedFile, setSelectedFile] = useState<File | null>(null);



  // Elapsed-time display while a (slow, local) analysis is running
  const [analysisStartedAt, setAnalysisStartedAt] = useState<number | null>(null);

  const [nowTs, setNowTs] = useState<number>(() => Date.now());

  const elapsedLabel = analysisStartedAt ? `(${formatElapsed(nowTs - analysisStartedAt)})` : "";


  // Tick once per second only while an analysis is running
  useEffect(() => {
    if (analysisStartedAt === null) return;
    setNowTs(Date.now());
    const t = setInterval(() => setNowTs(Date.now()), 1000);
    return () => clearInterval(t);
  }, [analysisStartedAt]);


  // Automatically sync incoming answered questions into clarificationAnswers state
  useEffect(() => {
    if (clarificationsData?.questions && clarificationsData.questions.length > 0) {
      setClarificationAnswers((prev) => {
        let changed = false;
        const next = { ...prev };
        for (const q of clarificationsData.questions) {
          if (q.answer_text && next[q.question_key] === undefined) {
            next[q.question_key] = q.answer_text;
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }
  }, [clarificationsData]);


  // Unified, normalized clarification items (includes Claude-style topics & structured options)
  const allClarificationItems = useMemo(() => {
    const items: Array<{
      key: string;
      topic: string;
      questionText: string;
      rationale?: string;
      category?: string;
      priority?: string;
      structuredOptions: Array<{ label: string; description: string }>;
      isResolved: boolean;
      currentValue: string;
    }> = [];

    if (clarificationsData?.questions && clarificationsData.questions.length > 0) {
      for (const q of clarificationsData.questions) {
        const currentVal = clarificationAnswers[q.question_key] !== undefined
          ? clarificationAnswers[q.question_key]
          : (q.answer_text || q.answer || "");

        const structured: Array<{ label: string; description: string }> = [];
        if (q.structured_options && q.structured_options.length > 0) {
          structured.push(...q.structured_options);
        } else if (q.suggested_options && q.suggested_options.length > 0) {
          for (const opt of q.suggested_options) {
            const parts = opt.split(" — ");
            if (parts.length === 2) {
              structured.push({ label: parts[0].trim(), description: parts[1].trim() });
            } else {
              structured.push({ label: opt, description: "" });
            }
          }
        }

        items.push({
          key: q.question_key,
          topic: q.short_topic || q.category.replace(/_/g, " "),
          questionText: q.question_text,
          rationale: q.rationale,
          category: q.category,
          priority: q.priority,
          structuredOptions: structured,
          isResolved: q.status === "ANSWERED" || Boolean(currentVal && currentVal.trim()),
          currentValue: currentVal,
        });
      }
    }

    return items;
  }, [clarificationsData, clarificationAnswers]);


  // Derived Workflow Progress Step (1 to 5)
  const isStep1Done = isCompanySaved || Boolean(companyDetails.companyName.trim());

  const isStep2Done = Boolean(jdText.trim()) || Boolean(selectedFile);

  const isStep3Done = (status === "READY" || status === "NEEDS_REVIEW") && markdown !== null;

  // Step 4 is done if initial analysis is done AND (0 ambiguities exist OR all are answered/finalized/v2)
  const hasUnresolvedQuestions = allClarificationItems.some((i) => !i.isResolved);
  const isStep4Done = isStep3Done && (
    allClarificationItems.length === 0 ||
    clarificationsData?.lifecycle_status === "FINALIZED" ||
    specVersion > 1 ||
    !hasUnresolvedQuestions
  );

  const isStep5Done = agents.length > 0;


  // Diff highlights are ONLY valid when:
  // 1) showDiffHighlights is toggled on
  // 2) markdownDiff exists with positive changed lines
  // 3) specVersion > 1 (ambiguities were resolved to produce v2+; NEVER on initial v1 analysis)
  // 4) diff belongs strictly to the currently loaded jdId
  const isDiffActive = Boolean(
    showDiffHighlights &&
    markdownDiff &&
    diffChangedCount > 0 &&
    specVersion > 1 &&
    diffJdId === jdId
  );


  const currentStep = !isStep1Done ? 1 : !isStep2Done ? 2 : !isStep3Done ? 3 : !isStep4Done ? 4 : 5;


  // Step 1 Save Handler
  function handleSaveCompanyDetails(e: React.FormEvent) {
    e.preventDefault();
    if (!companyDetails.companyName.trim()) return;
    setIsCompanySaved(true);
  }


  // Fetch Context Comparison
  async function fetchComparison(base: JDContextType = comparisonBaseContext, target: JDContextType = comparisonTargetContext, targetJdId?: string) {
    const idToUse = targetJdId || jdId;
    if (!idToUse) return;
    setIsLoadingComparison(true);
    try {
      let res = await getComparison(idToUse, base, target);
      // Fall back to the available enriched context when no resolved version exists.
      if (!res.has_resolved && target === "resolved" && res.has_enriched) {
        setComparisonTargetContext("enriched");
        res = await getComparison(idToUse, base, "enriched");
      }
      setComparisonData(res);
    } catch (e) {
      console.error("Failed to load JD context comparison:", e);
    } finally {
      setIsLoadingComparison(false);
    }
  }


  // Cancel in-flight JD Analysis
  async function handleCancelAnalysis() {
    pollAbortRef.current?.abort();
    if (jdId) {
      try {
        await cancelAnalysis(jdId);
      } catch {
        /* ignore */
      }
    }
    setStatus(null);
    setAnalysisStartedAt(null);
    setAnalysisProgress({ percent: 0, stageLabel: "" });
    setError("Analysis was cancelled by user.");
  }


  // Cancel in-flight Ambiguity Resolution
  async function handleCancelResolve() {
    pollAbortRef.current?.abort();
    if (jdId) {
      try {
        await cancelTask(jdId, "resolve");
      } catch {
        /* ignore */
      }
    }
    setIsResolvingClarifications(false);
    setResolveProgress({ percent: 0, stageLabel: "" });
    setResolveError("Ambiguity resolution was cancelled by user.");
  }


  // Reset workflow form for adding a new JD
  function handleResetForNewJD() {
    pollAbortRef.current?.abort();
    setAnalysisStartedAt(null);
    setJdId(null);
    setStatus(null);
    setError(null);
    setMarkdown(null);
    setJsonData(null);
    setJdText("");
    setSelectedFile(null);
    setCreatedAgentSuccess(null);
    setAgentNameInput("");
    setJobTitle("");
    setIsEnrichedView(false);
    setEnrichError(null);
    setClarificationsData(null);
    setClarificationAnswers({});
    setActiveClarificationIndex(0);
    setResolveSuccessMsg(null);
    setResolveError(null);
    setAnalysisSuccessMsg(null);
    setAnalysisProgress({ percent: 0, stageLabel: "" });
    setResolveProgress({ percent: 0, stageLabel: "" });
    setComparisonData(null);
    setContextTab("markdown");

    // Clear diff highlights from previous JD so new JD is clean and un-highlighted
    setMarkdownDiff(null);
    setShowDiffHighlights(false);
    setPrevMarkdown(null);
    setDiffChangedCount(0);
    setDiffJdId(null);
  }


  // Handle Grounded TA Evidence Enrichment via Ollama
  async function handleEnrichJD() {
    if (!jdId) return;
    setIsEnriching(true);
    setEnrichError(null);
    pollAbortRef.current?.abort();
    const controller = new AbortController();
    pollAbortRef.current = controller;
    try {
      await enrichJD(jdId);
      await waitForTask(jdId, "enrich", {
        signal: controller.signal,
        onTick: (s) => {
          if (s.stage_label) {
            setEnrichError(null);
          }
        },
      });
      const res = await getMarkdown(jdId, true);
      setMarkdown(res.markdown);
      setIsEnrichedView(Boolean(res.is_enriched));
      if (contextTab === "compare") {
        fetchComparison(comparisonBaseContext, "enriched", jdId);
      }
    } catch (e) {
      if (isAbort(e)) return;
      const msg = (e as Error).message || "";
      setEnrichError(
        msg.includes("503") || msg.toLowerCase().includes("unavailable")
          ? "Local Ollama service is unreachable or target model is not running. Start Ollama and try again."
          : `Enrichment failed: ${msg}`
      );
    } finally {
      setIsEnriching(false);
    }
  }


  // Toggle between baseline and enriched markdown view
  async function handleToggleEnrichment(enable: boolean) {
    if (!jdId) return;
    try {
      const res = await getMarkdown(jdId, enable);
      setMarkdown(res.markdown);
      setIsEnrichedView(enable && Boolean(res.is_enriched));
      // Toggling direct baseline/enriched view turns off diff highlights
      setShowDiffHighlights(false);
    } catch (e) {
      console.error(e);
    }
  }


  // Submit TA answers for detected ambiguities & generate final specification
  async function handleResolveClarifications() {
    if (!jdId) return;
    setIsResolvingClarifications(true);
    setResolveSuccessMsg(null);
    setResolveError(null);
    setMarkdownDiff(null);
    setShowDiffHighlights(false);
    setResolveProgress({ percent: 15, stageLabel: "Queueing ambiguity resolution..." });
    pollAbortRef.current?.abort();
    const controller = new AbortController();
    pollAbortRef.current = controller;

    // Capture the pre-resolution markdown for diffing
    const snapshotBeforeResolve = markdown;

    try {
      await resolveClarifications(jdId, clarificationAnswers);
      await waitForTask(jdId, "resolve", {
        signal: controller.signal,
        onTick: (s) => {
          setResolveProgress({
            percent: s.progress_percent !== undefined ? s.progress_percent : 50,
            stageLabel: s.stage_label || "Resolving clarifications...",
          });
        },
      });
      const [mdRes, jsonRes, clarRes] = await Promise.all([
        getMarkdown(jdId),
        getJson(jdId),
        getClarifications(jdId),
      ]);

      // Compute sentence-level diff between v1 and v2 markdown (only if version > 1 and markdown changed)
      const newVer = mdRes.specification_version || 2;
      if (snapshotBeforeResolve && mdRes.markdown && snapshotBeforeResolve !== mdRes.markdown && newVer > 1) {
        const { segments, changedCount } = computeMarkdownDiff(snapshotBeforeResolve, mdRes.markdown);
        setMarkdownDiff(segments);
        setDiffChangedCount(changedCount);
        setShowDiffHighlights(changedCount > 0);
        setPrevMarkdown(snapshotBeforeResolve);
        setDiffJdId(jdId);
      } else {
        setMarkdownDiff(null);
        setShowDiffHighlights(false);
        setDiffChangedCount(0);
        setDiffJdId(null);
      }

      setMarkdown(mdRes.markdown);
      setJsonData(jsonRes.json);
      setSpecVersion(mdRes.specification_version);
      setIsEnrichedView(Boolean(mdRes.is_enriched));
      setClarificationsData(clarRes);
      setResolveProgress({ percent: 100, stageLabel: "Ambiguities resolved!" });
      setResolveSuccessMsg("✓ Ambiguities resolved! Final specification generated.");

      // Switch to Markdown tab and auto-scroll to Step 4
      setContextTab("markdown");
      setTimeout(() => {
        step4Ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 300);

      // Refresh comparison
      fetchComparison(comparisonBaseContext, "resolved", jdId);
    } catch (e) {
      if (isAbort(e)) return;
      const errMsg = (e as Error).message || "Failed to resolve clarifications";
      setResolveError(errMsg);
      setResolveProgress({ percent: 0, stageLabel: "Resolution failed" });
    } finally {
      setIsResolvingClarifications(false);
    }
  }


  // Step 3 Analyse Handler.
  // The backend now returns immediately from /analyze (HTTP 202) and we poll for progress,
  // showing live status + honest stage-based progress + elapsed time.
  async function handleAnalyseJD() {
    if (!jdText.trim() && !selectedFile) return;
    setError(null);
    setAnalysisSuccessMsg(null);
    setMarkdown(null);
    setJsonData(null);
    setCreatedAgentSuccess(null);
    setClarificationsData(null);
    setClarificationAnswers({});
    setActiveClarificationIndex(0);
    setResolveSuccessMsg(null);
    setResolveError(null);
    setComparisonData(null);
    setAnalysisProgress({ percent: 10, stageLabel: "Uploading Job Description..." });

    // Clear previous JD diff highlights so initial analysis starts pristine
    setMarkdownDiff(null);
    setShowDiffHighlights(false);
    setPrevMarkdown(null);
    setDiffChangedCount(0);
    setDiffJdId(null);

    pollAbortRef.current?.abort();
    const controller = new AbortController();
    pollAbortRef.current = controller;

    try {
      const { jd_id, title: returnedTitle } = await uploadJD(
        companyDetails.projectName.trim() || "default-project",
        {
          text: selectedFile ? undefined : jdText,
          file: selectedFile || undefined,
        },
        jobTitle.trim() || undefined
      );
      setJdId(jd_id);
      if (returnedTitle && !jobTitle.trim()) setJobTitle(returnedTitle);

      setStatus("UPLOADED");
      setAnalysisStartedAt(Date.now());
      setAnalysisProgress({ percent: 15, stageLabel: "Starting background analysis..." });
      await analyzeJD(jd_id);

      const final = await pollUntilDone(jd_id, {
        onStatus: setStatus,
        onProgress: (p) => {
          setAnalysisProgress({
            percent: p.percent,
            stageLabel: p.stageLabel,
          });
        },
        signal: controller.signal,
      });

      if (final.status === "FAILED") {
        setError(final.error_message || "Processing failed.");
        setAnalysisProgress({ percent: 0, stageLabel: "Analysis failed" });
        return;
      }

      setAnalysisProgress({ percent: 100, stageLabel: "Analysis Complete!" });
      setAnalysisSuccessMsg("✓ Job Description successfully analyzed! Specification v1 generated.");

      const [mdRes, jsonRes, clarRes] = await Promise.all([
        getMarkdown(jd_id),
        getJson(jd_id),
        getClarifications(jd_id).catch(() => null),
      ]);
      setMarkdown(mdRes.markdown);
      setJsonData(jsonRes.json);
      setSpecVersion(mdRes.specification_version || 1);
      setIsEnrichedView(Boolean(mdRes.is_enriched));
      if (clarRes) setClarificationsData(clarRes);
      // Guarantee diff highlights are reset on fresh baseline v1 specification
      setMarkdownDiff(null);
      setShowDiffHighlights(false);
      setDiffChangedCount(0);
      setDiffJdId(null);

      // Pre-fetch comparison baseline
      fetchComparison("baseline", "resolved", jd_id);
    } catch (e) {
      if (isAbort(e)) return;
      setError((e as Error).message);
      setStatus("FAILED"); // unlock the Analyse button
      setAnalysisProgress({ percent: 0, stageLabel: "Analysis failed" });
    } finally {
      if (pollAbortRef.current === controller) setAnalysisStartedAt(null);
    }
  }


  // File Upload Handler (.txt, .pdf, .docx)
  function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".txt") && !lower.endsWith(".pdf") && !lower.endsWith(".docx")) {
      setError("Unsupported file format. Please upload .txt, .pdf, or .docx");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setError("File is too large (max 5 MB).");
      return;
    }

    setError(null);
    setSelectedFile(file);

    const baseName = file.name.replace(/\.[^/.]+$/, "").replace(/_/g, " ").replace(/-/g, " ");
    setJobTitle(baseName);

    if (lower.endsWith(".txt")) {
      const reader = new FileReader();
      reader.onload = (evt) => {
        const text = evt.target?.result as string;
        if (text) setJdText(text);
      };
      reader.readAsText(file);
    } else {
      setJdText(`[Attached file: ${file.name} (${Math.round(file.size / 1024)} KB)]`);
    }
  }


  // Download File Helper
  function downloadFile(filename: string, content: string, mime: string) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  return {
    companyDetails,
    isCompanySaved,
    jobTitle,
    jdText,
    jdId,
    status,
    error,
    markdown,
    jsonData,
    specVersion,
    contextTab,
    isEnriching,
    isEnrichedView,
    enrichError,
    analysisProgress,
    analysisSuccessMsg,
    resolveProgress,
    resolveError,
    comparisonData,
    isLoadingComparison,
    comparisonBaseContext,
    comparisonTargetContext,
    comparisonFilter,
    comparisonViewMode,
    clarificationsData,
    clarificationAnswers,
    activeClarificationIndex,
    clarificationViewMode,
    isResolvingClarifications,
    resolveSuccessMsg,
    diffJdId,
    prevMarkdown,
    markdownDiff,
    showDiffHighlights,
    diffChangedCount,
    step4Ref,
    selectedFile,
    analysisStartedAt,
    nowTs,
    elapsedLabel,
    allClarificationItems,
    isStep1Done,
    isStep2Done,
    isStep3Done,
    isStep4Done,
    isStep5Done,
    isDiffActive,
    currentStep,
    setCompanyDetails,
    setIsCompanySaved,
    setJobTitle,
    setJdText,
    setJdId,
    setStatus,
    setError,
    setMarkdown,
    setJsonData,
    setSpecVersion,
    setContextTab,
    setIsEnriching,
    setIsEnrichedView,
    setEnrichError,
    setAnalysisProgress,
    setAnalysisSuccessMsg,
    setResolveProgress,
    setResolveError,
    setComparisonData,
    setIsLoadingComparison,
    setComparisonBaseContext,
    setComparisonTargetContext,
    setComparisonFilter,
    setComparisonViewMode,
    setClarificationsData,
    setClarificationAnswers,
    setActiveClarificationIndex,
    setClarificationViewMode,
    setIsResolvingClarifications,
    setResolveSuccessMsg,
    setDiffJdId,
    setPrevMarkdown,
    setMarkdownDiff,
    setShowDiffHighlights,
    setDiffChangedCount,
    setSelectedFile,
    setAnalysisStartedAt,
    setNowTs,
    handleSaveCompanyDetails,
    fetchComparison,
    handleCancelAnalysis,
    handleCancelResolve,
    handleResetForNewJD,
    handleEnrichJD,
    handleToggleEnrichment,
    handleResolveClarifications,
    handleAnalyseJD,
    handleFileUpload,
    downloadFile,
    pollAbortRef,
  };
}
