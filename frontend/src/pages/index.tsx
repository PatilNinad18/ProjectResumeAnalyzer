"use client";

// ============================================================================
// REPLACE everything in your page.tsx from line 1 down to (but NOT including)
// the line `return (` with this file's content. Your <style jsx global> CSS and
// JSX stay exactly as they are (see the 3 small JSX edits listed in my reply).
// ============================================================================

import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import {
  uploadJD,
  analyzeJD,
  cancelAnalysis,
  getMarkdown,
  enrichJD,
  getJson,
  getClarifications,
  resolveClarifications,
  ClarificationsResponse,
  askJDChatbot,
  pollUntilDone,
  TERMINAL_STATUSES,
  ProcessingStatus,
  CompanyDetails,
  CreatedAgent,
  ChatTurn,
  waitForTask,
  cancelTask,
  getComparison,
  ContextComparisonResponse,
  RequirementDiffItem,
  AmbiguityItem,
  JDContextType,
} from "@/lib/api";

const statusConfig: Record<ProcessingStatus, { label: string; icon: string; className: string }> = {
  UPLOADED: { label: "Uploaded", icon: "↑", className: "status-uploaded" },
  PARSING: { label: "Parsing JD", icon: "◌", className: "status-processing" },
  UNDERSTANDING: { label: "Understanding JD", icon: "◌", className: "status-processing" },
  VALIDATING: { label: "Validating", icon: "◌", className: "status-processing" },
  GENERATING: { label: "Generating Context", icon: "◌", className: "status-processing" },
  READY: { label: "Analysis Ready", icon: "✓", className: "status-ready" },
  NEEDS_REVIEW: { label: "Needs Review", icon: "!", className: "status-review" },
  FAILED: { label: "Failed", icon: "×", className: "status-failed" },
};

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const isAbort = (e: unknown) => (e as Error)?.name === "AbortError";

export default function Home() {
  // Navigation
  const [activeTab, setActiveTab] = useState<"workflow" | "chat" | "settings">("workflow");

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
  const [isResolvingClarifications, setIsResolvingClarifications] = useState<boolean>(false);
  const [resolveSuccessMsg, setResolveSuccessMsg] = useState<string | null>(null);

  // Selected File for multi-format upload (.txt, .pdf, .docx)
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // Elapsed-time display while a (slow, local) analysis is running
  const [analysisStartedAt, setAnalysisStartedAt] = useState<number | null>(null);
  const [nowTs, setNowTs] = useState<number>(() => Date.now());
  const elapsedLabel = analysisStartedAt ? `(${formatElapsed(nowTs - analysisStartedAt)})` : "";

  // Cancellation handles for in-flight polling
  const pollAbortRef = useRef<AbortController | null>(null);
  const regenAbortRef = useRef<AbortController | null>(null);

  // Agent Creation
  const [agents, setAgents] = useState<CreatedAgent[]>([]);
  const [agentNameInput, setAgentNameInput] = useState("");
  const [createdAgentSuccess, setCreatedAgentSuccess] = useState<string | null>(null);

  // Dedicated Chat State - strictly isolated per agent/JD id
  const defaultWelcomeMessage = {
    id: "welcome",
    sender: "assistant" as const,
    text: "Hello! I am your JD AI Assistant. I answer questions about this job description: requirements, technical skills, experience, work policy, and responsibilities. Ask me anything!",
  };

  const [selectedAgentId, setSelectedAgentId] = useState<string>("current");
  const [chatHistories, setChatHistories] = useState<
    Record<string, Array<{ id: string; sender: "user" | "assistant"; text: string }>>
  >({});
  const [chatInput, setChatInput] = useState("");
  const [isChatLoading, setIsChatLoading] = useState(false);

  // Current active chat messages scoped to selectedAgentId
  const currentChatMessages = chatHistories[selectedAgentId] || [defaultWelcomeMessage];

  // Settings & Regeneration State
  const [selectedSettingAgentId, setSelectedSettingAgentId] = useState<string | null>(null);
  const [editCompany, setEditCompany] = useState<CompanyDetails>({ companyName: "", department: "", projectName: "" });
  const [editTitle, setEditTitle] = useState("");
  const [editJdText, setEditJdText] = useState("");
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [regenStatus, setRegenStatus] = useState<string | null>(null);
  const [regenSuccessMsg, setRegenSuccessMsg] = useState<string | null>(null);

  // Tick once per second only while an analysis is running
  useEffect(() => {
    if (analysisStartedAt === null) return;
    setNowTs(Date.now());
    const t = setInterval(() => setNowTs(Date.now()), 1000);
    return () => clearInterval(t);
  }, [analysisStartedAt]);

  // Stop any polling when the page unmounts
  useEffect(() => {
    return () => {
      pollAbortRef.current?.abort();
      regenAbortRef.current?.abort();
    };
  }, []);

  // Auto-fill edit form when selecting an agent for settings
  useEffect(() => {
    if (selectedSettingAgentId) {
      const target = agents.find((a) => a.id === selectedSettingAgentId);
      if (target) {
        setEditCompany({ ...target.companyDetails });
        setEditTitle(target.title);
        setEditJdText(target.jdText);
      }
    } else if (agents.length > 0 && !selectedSettingAgentId) {
      setSelectedSettingAgentId(agents[0].id);
    }
  }, [selectedSettingAgentId, agents]);

  // If "current" has no analysed context (e.g. after "New JD"), fall back to the newest agent
  useEffect(() => {
    if (selectedAgentId === "current" && !markdown && agents.length > 0) {
      setSelectedAgentId(agents[0].id);
    }
  }, [selectedAgentId, markdown, agents]);

  // Derived Workflow Progress Step (1 to 5)
  const isStep1Done = isCompanySaved || Boolean(companyDetails.companyName.trim());
  const isStep2Done = Boolean(jdText.trim()) || Boolean(selectedFile);
  const isStep3Done = status === "READY" && markdown !== null;
  const isStep4Done = isStep3Done;
  const isStep5Done = agents.length > 0;

  const currentStep = !isStep1Done ? 1 : !isStep2Done ? 2 : status !== "READY" ? 3 : !isStep5Done ? 4 : 5;

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
      const res = await getComparison(idToUse, base, target);
      setComparisonData(res);
      // Auto-adjust target if resolved is not yet available and target is resolved
      if (!res.has_resolved && target === "resolved" && res.has_enriched) {
        setComparisonTargetContext("enriched");
      }
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
    setResolveSuccessMsg(null);
    setResolveError(null);
    setAnalysisSuccessMsg(null);
    setAnalysisProgress({ percent: 0, stageLabel: "" });
    setResolveProgress({ percent: 0, stageLabel: "" });
    setComparisonData(null);
    setContextTab("markdown");
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
    setResolveProgress({ percent: 15, stageLabel: "Queueing ambiguity resolution..." });
    pollAbortRef.current?.abort();
    const controller = new AbortController();
    pollAbortRef.current = controller;
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
      setMarkdown(mdRes.markdown);
      setJsonData(jsonRes.json);
      setSpecVersion(mdRes.specification_version);
      setIsEnrichedView(Boolean(mdRes.is_enriched));
      setClarificationsData(clarRes);
      setResolveProgress({ percent: 100, stageLabel: "Ambiguities resolved!" });
      setResolveSuccessMsg("✓ Ambiguities resolved! Final specification generated.");
      // Refresh comparison if comparison tab is active or data exists
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
    setResolveSuccessMsg(null);
    setResolveError(null);
    setComparisonData(null);
    setAnalysisProgress({ percent: 10, stageLabel: "Uploading Job Description..." });

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

  // Step 5 Create Agent Handler
  function handleCreateAgent() {
    if (!markdown || !jdId) return;
    const name = agentNameInput.trim() || `${jobTitle || "JD"} Agent`;
    const stamp = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const newAgent: CreatedAgent = {
      id: `agent-${Date.now()}`,
      agentName: name,
      title: jobTitle,
      companyDetails: { ...companyDetails },
      jdId: jdId,
      jdText: jdText,
      markdown: markdown,
      jsonData: jsonData || {},
      specificationVersion: specVersion,
      status: "ACTIVE",
      createdAt: stamp,
      updatedAt: stamp,
    };

    setAgents((prev) => [newAgent, ...prev]);
    setSelectedAgentId(newAgent.id);
    setCreatedAgentSuccess(`Agent "${name}" successfully created!`);
    setAgentNameInput("");

    // Open the Chat tab after the agent has been created.
    setActiveTab("chat");
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

  // Dedicated Chat Send Handler with isolated conversation history per Agent/JD
  async function handleSendChatMessage(textToSend?: string) {
    const q = (textToSend ?? chatInput).trim();
    if (!q || isChatLoading) return;

    const targetKey = selectedAgentId;
    const userMsg = { id: Date.now().toString(), sender: "user" as const, text: q };

    // Last few real turns (no welcome text, no error bubbles) give the model follow-up context.
    const history: ChatTurn[] = (chatHistories[targetKey] || [])
      .filter((m) => m.id !== "welcome" && !m.text.startsWith("⚠️"))
      .slice(-6)
      .map((m) => ({ role: m.sender, content: m.text.slice(0, 1000) }));

    setChatHistories((prev) => ({
      ...prev,
      [targetKey]: [...(prev[targetKey] || [defaultWelcomeMessage]), userMsg],
    }));

    if (!textToSend) setChatInput("");
    setIsChatLoading(true);

    const pushAssistant = (text: string) =>
      setChatHistories((prev) => ({
        ...prev,
        [targetKey]: [...(prev[targetKey] || []), { id: (Date.now() + 1).toString(), sender: "assistant" as const, text }],
      }));

    try {
      let targetJdId: string | null = null;
      let contextToUse: string | null = null;

      if (targetKey !== "current") {
        const agent = agents.find((a) => a.id === targetKey);
        if (agent) {
          targetJdId = agent.jdId;
          contextToUse = agent.markdown;
        }
      } else {
        targetJdId = jdId;
        contextToUse = markdown || (jdText.trim() ? `# Job Description\n\n${jdText}` : null);
      }

      if (!targetJdId && !contextToUse) {
        pushAssistant("⚠️ **No JD context yet.** Analyse a job description (or create an agent) first, then ask me about it.");
        return;
      }

      const { answer } = await askJDChatbot(targetJdId, q, contextToUse, history);
      pushAssistant(answer);
    } catch (e) {
      pushAssistant(`⚠️ **Error:** ${(e as Error).message}`);
    } finally {
      setIsChatLoading(false);
    }
  }

  function handleClearChatHistory() {
    setChatHistories((prev) => ({
      ...prev,
      [selectedAgentId]: [],
    }));
  }

  // Agent Settings & Context Regeneration Handler
  async function handleRegenerateAgentContext() {
    if (!selectedSettingAgentId || isRegenerating) return;
    const target = agents.find((a) => a.id === selectedSettingAgentId);
    if (!target) return;

    if (!editJdText.trim()) {
      alert("JD Text cannot be empty.");
      return;
    }

    regenAbortRef.current?.abort();
    const controller = new AbortController();
    regenAbortRef.current = controller;

    setIsRegenerating(true);
    setRegenStatus("Uploading updated JD...");
    setRegenSuccessMsg(null);

    try {
      // FIX: uploadJD takes { text, file }, the old code passed a bare string here.
      const { jd_id } = await uploadJD(
        editCompany.projectName || target.companyDetails.projectName || "updated-project",
        { text: editJdText },
        editTitle.trim() || target.title
      );

      setRegenStatus("Analyzing updated context...");
      await analyzeJD(jd_id);

      const final = await pollUntilDone(jd_id, {
        signal: controller.signal,
        onStatus: (s) => setRegenStatus(`Status: ${statusConfig[s]?.label || s}`),
      });
      if (final.status === "FAILED") {
        alert(`Regeneration failed: ${final.error_message || "Unknown error"}`);
        return;
      }

      const [mdRes, jsonRes] = await Promise.all([getMarkdown(jd_id), getJson(jd_id)]);

      // Re-point existing agent in-place
      setAgents((prev) =>
        prev.map((a) =>
          a.id === selectedSettingAgentId
            ? {
                ...a,
                title: editTitle.trim() || a.title,
                companyDetails: { ...editCompany },
                jdId: jd_id,
                jdText: editJdText,
                markdown: mdRes.markdown,
                jsonData: jsonRes.json,
                specificationVersion: mdRes.specification_version || a.specificationVersion + 1,
                updatedAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
              }
            : a
        )
      );

      // Also update current workflow view state if it matches
      if (target.jdId === jdId) {
        setMarkdown(mdRes.markdown);
        setJsonData(jsonRes.json);
        setJdId(jd_id);
        setJdText(editJdText);
      }

      setRegenSuccessMsg(`Successfully regenerated context! Agent re-pointed to Specification v${mdRes.specification_version}`);
    } catch (e) {
      if (!isAbort(e)) alert(`Regeneration failed: ${(e as Error).message}`);
    } finally {
      setIsRegenerating(false);
      setRegenStatus(null);
    }
  }

  const activeAgentForChat = agents.find((a) => a.id === selectedAgentId);
  const hasReadyContext = isStep3Done || Boolean(activeAgentForChat);

  return (
    <>
      <style jsx global>{`
        :root {
          --bg: #f7f8fc;
          --surface: #ffffff;
          --surface-soft: #fbfcff;
          --surface-muted: #f1f3f8;
          --border: #e5e7eb;
          --border-strong: #d7dce5;
          --text: #101828;
          --text-soft: #475467;
          --text-muted: #667085;
          --primary: #5b5ce2;
          --primary-strong: #4b4dcc;
          --primary-soft: #eef0ff;
          --ink: #14141c;
          --success: #12b76a;
          --success-soft: #ecfdf3;
          --warning: #f79009;
          --warning-soft: #fffaeb;
          --danger: #f04438;
          --danger-soft: #fef3f2;
          --shadow-sm: 0 1px 2px rgba(16, 24, 40, 0.04);
          --shadow-md: 0 8px 24px rgba(16, 24, 40, 0.06);
          --shadow-lg: 0 18px 50px rgba(16, 24, 40, 0.08);
        }

        * { box-sizing: border-box; }

        html { scroll-behavior: smooth; }

        body {
          margin: 0;
          background:
            radial-gradient(circle at 10% 0%, rgba(91, 92, 226, 0.06), transparent 24%),
            radial-gradient(circle at 100% 12%, rgba(124, 92, 255, 0.05), transparent 28%),
            var(--bg);
          color: var(--text);
          font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          -webkit-font-smoothing: antialiased;
          text-rendering: optimizeLegibility;
        }

        button, input, textarea, select { font: inherit; }
        button { -webkit-tap-highlight-color: transparent; }

        ::selection { background: rgba(91, 92, 226, 0.16); color: var(--text); }

        .app-container {
          min-height: 100vh;
          background: transparent;
          display: flex;
          flex-direction: column;
        }

        /* Top Header — matches reference chrome: avatar, Ask Anything pill, AI mark, title, context button */
        .topbar {
          height: 74px;
          background: rgba(255, 255, 255, 0.9);
          backdrop-filter: blur(16px);
          -webkit-backdrop-filter: blur(16px);
          border-bottom: 1px solid rgba(229, 231, 235, 0.92);
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 32px;
          position: sticky;
          top: 0;
          z-index: 50;
          box-shadow: 0 1px 0 rgba(16, 24, 40, 0.02), 0 6px 20px rgba(16, 24, 40, 0.03);
          gap: 20px;
        }

        .topbar-left {
          display: flex;
          align-items: center;
          gap: 14px;
          flex: 1;
        }

        .user-avatar {
          width: 34px;
          height: 34px;
          border-radius: 50%;
          background: var(--ink);
          color: #fff;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          font-size: 0.92rem;
          flex: 0 0 auto;
        }

        .ask-anything-btn {
          display: inline-flex;
          align-items: center;
          gap: 9px;
          background: linear-gradient(135deg, #6668ed, #5153dd);
          color: #fff;
          border: none;
          padding: 8px 8px 8px 16px;
          border-radius: 999px;
          font-weight: 650;
          font-size: 0.85rem;
          cursor: pointer;
          box-shadow: 0 8px 18px rgba(81, 82, 221, 0.18);
          transition: transform 0.18s ease, box-shadow 0.18s ease;
        }

        .ask-anything-btn:hover {
          transform: translateY(-1px);
          box-shadow: 0 12px 22px rgba(81, 82, 221, 0.24);
        }

        .chatbot-badge {
          background: rgba(255, 255, 255, 0.2);
          padding: 4px 9px;
          border-radius: 999px;
          font-size: 0.64rem;
          letter-spacing: 0.03em;
          font-weight: 700;
        }

        .topbar-center {
          display: flex;
          align-items: center;
          gap: 12px;
          flex: 1.4;
          justify-content: center;
        }

        .ai-icon-box {
          width: 34px;
          height: 34px;
          border-radius: 10px;
          background: var(--ink);
          color: #fff;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          font-size: 0.76rem;
          letter-spacing: 0.02em;
          flex: 0 0 auto;
        }

        .brand-text {
          display: flex;
          flex-direction: column;
          line-height: 1.28;
        }

        .brand-title {
          font-weight: 750;
          font-size: 1.03rem;
          letter-spacing: -0.02em;
          color: var(--text);
          white-space: nowrap;
        }

        .brand-subtitle {
          font-size: 0.78rem;
          color: var(--text-muted);
          white-space: nowrap;
        }

        .topbar-right {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 10px;
          flex: 1;
        }

        .context-btn {
          background: var(--surface-muted);
          color: #344054;
          border: 1px solid #e3e5ec;
          padding: 9px 16px;
          border-radius: 10px;
          font-size: 0.83rem;
          font-weight: 650;
          cursor: pointer;
          transition: all 0.18s ease;
          white-space: nowrap;
        }

        .context-btn:hover {
          background: #e9eaf1;
          border-color: #d5d8e3;
          transform: translateY(-1px);
        }

        .sub-nav-wrap {
          display: flex;
          justify-content: center;
          padding: 10px 32px;
          background: rgba(255, 255, 255, 0.65);
          border-bottom: 1px solid rgba(229, 231, 235, 0.7);
          position: sticky;
          top: 74px;
          z-index: 49;
          backdrop-filter: blur(10px);
        }

        .nav-tabs {
          display: flex;
          gap: 4px;
          background: #f5f6fa;
          padding: 4px;
          border-radius: 13px;
          border: 1px solid #e7e9ef;
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.85);
        }

        .nav-btn {
          background: transparent;
          border: 1px solid transparent;
          color: var(--text-muted);
          padding: 9px 16px;
          border-radius: 9px;
          font-size: 0.86rem;
          font-weight: 600;
          cursor: pointer;
          transition: transform 0.18s ease, background 0.18s ease, color 0.18s ease, box-shadow 0.18s ease;
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .nav-btn:hover {
          color: var(--text);
          background: #ffffff;
          transform: translateY(-1px);
        }

        .nav-btn.active {
          background: linear-gradient(135deg, #6366f1, #5455df);
          color: #fff;
          box-shadow: 0 7px 16px rgba(91, 92, 226, 0.22);
        }

        /* Main Content */
        .main-content {
          flex: 1;
          max-width: 1320px;
          width: 100%;
          margin: 0 auto;
          padding: 38px 32px 64px;
          position: relative;
        }

        .main-content::before,
        .main-content::after {
          content: "";
          position: fixed;
          width: 220px;
          height: 220px;
          border-radius: 50%;
          pointer-events: none;
          filter: blur(44px);
          opacity: 0.35;
          z-index: -1;
        }

        .main-content::before {
          top: 160px;
          left: -80px;
          background: rgba(99, 102, 241, 0.08);
        }

        .main-content::after {
          bottom: 30px;
          right: -60px;
          background: rgba(124, 92, 255, 0.07);
        }

        /* Cards */
        .card {
          background: rgba(255, 255, 255, 0.94);
          border: 1px solid rgba(226, 229, 236, 0.95);
          border-radius: 18px;
          padding: 30px;
          box-shadow: var(--shadow-md);
          margin-bottom: 24px;
          position: relative;
          overflow: hidden;
          transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
        }

        .card::before {
          content: "";
          position: absolute;
          inset: 0 0 auto 0;
          height: 3px;
          background: linear-gradient(90deg, rgba(99,102,241,0.7), rgba(124,92,246,0.25), transparent);
        }

        .card:hover {
          border-color: #dfe2eb;
          box-shadow: var(--shadow-lg);
        }

        .card h2, .card h3, .card h4 {
          color: var(--text);
          letter-spacing: -0.025em;
        }

        /* Workflow Stepper */
        .stepper {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          position: relative;
          margin: 4px 2px 34px;
          padding: 0 10px;
        }

        .stepper::before {
          content: "";
          position: absolute;
          top: 19px;
          left: 9%;
          right: 9%;
          height: 2px;
          background: linear-gradient(90deg, #c9ccda, #e6e8ef);
          z-index: 1;
        }

        .step-item {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 9px;
          position: relative;
          z-index: 2;
          min-width: 118px;
        }

        .step-circle {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          background: #fff;
          border: 2px solid #d6d9e2;
          color: #7b8394;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          font-size: 0.9rem;
          transition: all 0.25s ease;
          box-shadow: 0 2px 8px rgba(16,24,40,0.04);
        }

        .step-item.active .step-circle {
          border-color: #6466ea;
          background: linear-gradient(135deg, #6869ec, #5658df);
          color: #fff;
          box-shadow: 0 0 0 5px rgba(99,102,241,0.10), 0 8px 18px rgba(99,102,241,0.18);
          transform: translateY(-1px);
        }

        .step-item.completed .step-circle {
          border-color: #17b26a;
          background: linear-gradient(135deg, #16b978, #11a965);
          color: #fff;
          box-shadow: 0 7px 15px rgba(18,183,106,0.17);
        }

        .step-label {
          font-size: 0.8rem;
          font-weight: 600;
          color: #7b8496;
          text-align: center;
        }

        .step-item.active .step-label { color: var(--text); font-weight: 700; }
        .step-item.completed .step-label { color: #079455; }

        /* Forms */
        .form-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
          gap: 20px;
        }

        .form-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .form-group label {
          font-size: 0.83rem;
          font-weight: 650;
          color: #344054;
          letter-spacing: -0.005em;
        }

        .input-text, .textarea, .select {
          width: 100%;
          background: #fff;
          border: 1px solid #d8dce5;
          border-radius: 11px;
          padding: 12px 14px;
          color: var(--text);
          font-size: 0.92rem;
          box-shadow: inset 0 1px 1px rgba(16,24,40,0.02);
          transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
        }

        .input-text::placeholder, .textarea::placeholder { color: #98a2b3; }

        .input-text:hover, .textarea:hover, .select:hover { border-color: #c5cad6; }

        .input-text:focus, .textarea:focus, .select:focus {
          outline: none;
          border-color: #7779ee;
          box-shadow: 0 0 0 4px rgba(99,102,241,0.10), 0 4px 10px rgba(16,24,40,0.04);
        }

        .textarea {
          min-height: 220px;
          resize: vertical;
          line-height: 1.6;
        }

        .select {
          appearance: none;
          background-image: linear-gradient(45deg, transparent 50%, #98a2b3 50%), linear-gradient(135deg, #98a2b3 50%, transparent 50%);
          background-position: calc(100% - 16px) 50%, calc(100% - 11px) 50%;
          background-size: 5px 5px, 5px 5px;
          background-repeat: no-repeat;
          padding-right: 34px;
        }

        .select option {
          background-color: #ffffff;
          color: #101828;
        }

        .select-on-dark {
          background-color: rgba(255,255,255,0.12);
          border: 1px solid rgba(255,255,255,0.22);
          color: #ffffff;
          box-shadow: none;
        }

        .select-on-dark option {
          background-color: #181c2e;
          color: #ffffff;
          padding: 8px 12px;
        }

        .select-on-dark:hover { border-color: rgba(255,255,255,0.4); }
        .select-on-dark:focus { border-color: rgba(255,255,255,0.6); box-shadow: 0 0 0 4px rgba(255,255,255,0.12); }

        /* Buttons */
        .btn-primary {
          background: linear-gradient(135deg, #6668ed, #5052dd);
          color: #fff;
          border: 1px solid rgba(81, 82, 221, 0.6);
          padding: 12px 20px;
          border-radius: 11px;
          font-weight: 700;
          font-size: 0.9rem;
          cursor: pointer;
          transition: transform 0.18s ease, box-shadow 0.18s ease, filter 0.18s ease;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          box-shadow: 0 8px 18px rgba(81,82,221,0.16);
        }

        .btn-primary:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 12px 24px rgba(81,82,221,0.22);
          filter: saturate(1.04);
        }

        .btn-primary:active:not(:disabled) { transform: translateY(0); }

        .btn-primary:disabled {
          opacity: 0.52;
          cursor: not-allowed;
          box-shadow: none;
        }

        .btn-secondary {
          background: #fff;
          color: #344054;
          border: 1px solid #d8dce5;
          padding: 10px 16px;
          border-radius: 10px;
          font-weight: 650;
          font-size: 0.86rem;
          cursor: pointer;
          transition: transform 0.18s ease, background 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
        }

        .btn-secondary:hover {
          background: #fafbff;
          color: #1d2939;
          border-color: #c8ccd6;
          transform: translateY(-1px);
          box-shadow: var(--shadow-sm);
        }

        .btn-ghost-dark {
          background: rgba(255,255,255,0.08);
          border: 1px solid rgba(255,255,255,0.18);
          color: #fff;
          padding: 7px 13px;
          border-radius: 9px;
          font-size: 0.78rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.18s ease;
          white-space: nowrap;
        }

        .btn-ghost-dark:hover { background: rgba(255,255,255,0.15); }

        .chat-close-btn {
          background: rgba(255,255,255,0.08);
          border: 1px solid rgba(255,255,255,0.18);
          color: #fff;
          width: 32px;
          height: 32px;
          border-radius: 9px;
          cursor: pointer;
          font-size: 0.85rem;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          transition: all 0.18s ease;
          flex: 0 0 auto;
        }

        .chat-close-btn:hover { background: rgba(255,255,255,0.18); }

        /* Status */
        .alert-success, .alert-error {
          padding: 13px 16px;
          border-radius: 11px;
          font-size: 0.88rem;
          display: flex;
          align-items: center;
          gap: 9px;
          margin-bottom: 18px;
        }

        .alert-success {
          background: var(--success-soft);
          border: 1px solid #abefc6;
          color: #067647;
        }

        .alert-error {
          background: var(--danger-soft);
          border: 1px solid #fecdca;
          color: #b42318;
        }

        .status-pill {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 6px 11px;
          border-radius: 999px;
          font-size: 0.76rem;
          font-weight: 700;
          border: 1px solid transparent;
          white-space: nowrap;
        }

        .status-uploaded { background: #eff8ff; color: #175cd3; border-color: #b2ddff; }
        .status-processing { background: #f4f3ff; color: #6938ef; border-color: #d9d6fe; }
        .status-ready { background: #ecfdf3; color: #067647; border-color: #abefc6; }
        .status-review { background: var(--warning-soft); color: #b54708; border-color: #fedf89; }
        .status-failed { background: #fef3f2; color: #b42318; border-color: #fecdca; }

        /* Preview */
        .preview-header {
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 20px;
          padding-bottom: 18px;
          margin-bottom: 20px;
          border-bottom: 1px solid #edf0f4;
        }

        .sub-tabs {
          display: flex;
          gap: 4px;
          background: #f6f7fa;
          padding: 4px;
          border: 1px solid #e7e9ef;
          border-radius: 10px;
        }

        .sub-tab-btn {
          background: transparent;
          border: none;
          color: #667085;
          padding: 7px 12px;
          border-radius: 7px;
          font-size: 0.82rem;
          cursor: pointer;
          font-weight: 600;
          transition: all 0.18s ease;
        }

        .sub-tab-btn:hover { color: #344054; }

        .sub-tab-btn.active {
          background: #fff;
          color: #344054;
          font-weight: 700;
          box-shadow: 0 2px 7px rgba(16,24,40,0.06);
        }

        .code-preview {
          background: #fbfcfe;
          border: 1px solid #e5e7eb;
          border-radius: 14px;
          padding: 24px;
          max-height: 520px;
          overflow-y: auto;
          font-size: 0.9rem;
          line-height: 1.7;
          color: #344054;
          box-shadow: inset 0 1px 1px rgba(16,24,40,0.02);
        }

        .code-preview pre {
          margin: 0;
          color: #344054 !important;
          white-space: pre-wrap;
          overflow-wrap: anywhere;
        }

        .code-preview h1, .code-preview h2, .code-preview h3, .code-preview h4 {
          color: #101828;
          letter-spacing: -0.02em;
        }

        .code-preview code {
          background: #f2f4f7;
          border: 1px solid #eaecf0;
          border-radius: 5px;
          padding: 2px 5px;
          color: #475467;
        }

        /* Chat */
        .chat-container {
          display: flex;
          flex-direction: column;
          height: calc(100vh - 200px);
          min-height: 650px;
          background: rgba(255,255,255,0.96);
          border: 1px solid #e3e6ed;
          border-radius: 20px;
          overflow: hidden;
          box-shadow: var(--shadow-lg);
        }

        .chat-topbar {
          padding: 18px 22px;
          background: linear-gradient(180deg, #1c1d27 0%, #14141c 100%);
          border-bottom: 1px solid #14141c;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 14px;
          color: #fff;
        }

        .context-status-row {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 12px 22px;
          background: #fbfcff;
          border-bottom: 1px solid #eef0f4;
          font-size: 0.82rem;
          color: #667085;
          font-weight: 600;
        }

        .context-status-badge {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          padding: 4px 10px;
          border-radius: 999px;
          font-size: 0.74rem;
          font-weight: 700;
          border: 1px solid transparent;
        }

        .context-status-badge.ready { background: var(--success-soft); color: #067647; border-color: #abefc6; }
        .context-status-badge.pending { background: var(--warning-soft); color: #b54708; border-color: #fedf89; }

        .chat-messages {
          flex: 1;
          padding: 26px;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 16px;
          background:
            radial-gradient(circle at 80% 10%, rgba(99,102,241,0.05), transparent 24%),
            #fafbfe;
        }

        .message-bubble {
          max-width: min(78%, 760px);
          padding: 14px 17px;
          border-radius: 16px;
          font-size: 0.92rem;
          line-height: 1.62;
          animation: messageIn 0.22s ease;
        }

        .message-user {
          align-self: flex-end;
          background: linear-gradient(135deg, #6668ed, #5153dd);
          color: #fff;
          border-bottom-right-radius: 5px;
          box-shadow: 0 9px 22px rgba(81,82,221,0.16);
        }

        .message-assistant {
          align-self: flex-start;
          background: #fff;
          border: 1px solid #e6e8ee;
          color: #344054;
          border-bottom-left-radius: 5px;
          box-shadow: 0 4px 14px rgba(16,24,40,0.05);
        }

        .message-bubble p:first-child { margin-top: 0; }
        .message-bubble p:last-child { margin-bottom: 0; }
        .message-bubble ul, .message-bubble ol { padding-left: 20px; }

        .chat-input-bar {
          padding: 16px 20px;
          background: #fff;
          border-top: 1px solid #eaecf0;
          display: flex;
          gap: 10px;
        }

        .chat-input-bar .input-text { height: 46px; }

        .prompt-chips {
          display: flex;
          gap: 8px;
          padding: 11px 20px 13px;
          background: #fff;
          border-top: 1px solid #f0f1f4;
          overflow-x: auto;
          scrollbar-width: thin;
        }

        .chip {
          background: #fff;
          border: 1px solid #dce0e8;
          color: #667085;
          padding: 7px 12px;
          border-radius: 999px;
          font-size: 0.78rem;
          cursor: pointer;
          white-space: nowrap;
          font-weight: 600;
          transition: all 0.18s ease;
        }

        .chip:hover {
          background: #f6f7ff;
          border-color: #b9bcfb;
          color: #4b4dcc;
          transform: translateY(-1px);
        }

        /* Agent Cards */
        .agent-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 16px;
        }

        .agent-card {
          background: #fff;
          border: 1px solid #e5e7eb;
          border-radius: 14px;
          padding: 20px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          transition: all 0.2s ease;
          box-shadow: var(--shadow-sm);
        }

        .agent-card:hover {
          border-color: #c7c9f7;
          transform: translateY(-2px);
          box-shadow: 0 10px 24px rgba(16,24,40,0.07);
        }

        .agent-card.selected {
          border-color: #9da0f6;
          box-shadow: 0 0 0 4px rgba(99,102,241,0.08), 0 10px 24px rgba(16,24,40,0.06);
        }

        /* Spinner */
        .spinner {
          width: 16px;
          height: 16px;
          border: 2px solid rgba(255,255,255,0.34);
          border-top-color: #fff;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
          flex: 0 0 auto;
        }

        .message-assistant .spinner {
          border-color: #e5e7eb;
          border-top-color: #6366f1;
        }

        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes messageIn {
          from { opacity: 0; transform: translateY(5px); }
          to { opacity: 1; transform: translateY(0); }
        }

        /* Scrollbars */
        .code-preview::-webkit-scrollbar,
        .chat-messages::-webkit-scrollbar,
        .prompt-chips::-webkit-scrollbar { width: 9px; height: 9px; }

        .code-preview::-webkit-scrollbar-thumb,
        .chat-messages::-webkit-scrollbar-thumb,
        .prompt-chips::-webkit-scrollbar-thumb {
          background: #d7dbe4;
          border-radius: 999px;
          border: 2px solid transparent;
          background-clip: padding-box;
        }

        /* Responsive */
        @media (max-width: 900px) {
          .topbar { padding: 0 18px; }
          .sub-nav-wrap { padding: 10px 18px; top: 70px; }
          .main-content { padding: 24px 18px 44px; }
          .card { padding: 22px; }
          .nav-btn { padding: 8px 11px; }
          .nav-btn span { display: none; }
          .preview-header { flex-direction: column; align-items: stretch; }
          .chat-topbar { flex-direction: column; align-items: stretch; }
          .brand-subtitle { display: none; }
        }

        @media (max-width: 680px) {
          .topbar { height: auto; min-height: 66px; gap: 10px; align-items: center; padding: 12px 14px; flex-wrap: wrap; }
          .topbar-left { flex: 1 1 auto; }
          .topbar-center { display: none; }
          .topbar-right { flex: 0 0 auto; }
          .ask-anything-btn span:not(.chatbot-badge) { display: none; }
          .sub-nav-wrap { top: 0; padding: 8px 14px; }
          .nav-tabs { width: 100%; justify-content: space-between; }
          .nav-btn { flex: 1; justify-content: center; }
          .stepper { overflow-x: auto; justify-content: flex-start; gap: 34px; padding-bottom: 8px; }
          .stepper::before { left: 58px; right: 58px; min-width: 520px; }
          .step-item { min-width: 100px; }
          .card { border-radius: 14px; padding: 18px; }
          .form-grid { grid-template-columns: 1fr; }
          .message-bubble { max-width: 90%; }
          .chat-container { min-height: 560px; height: calc(100vh - 150px); border-radius: 14px; }
          .chat-messages { padding: 18px; }
          .chat-input-bar { padding: 12px; }
          .prompt-chips { padding-inline: 12px; }
        }

        /* Progress Card & Stage Indicators */
        .progress-card {
          background: #f8fafc;
          border: 1px solid #e0e7ff;
          border-radius: 12px;
          padding: 16px;
          box-shadow: 0 1px 3px rgba(16, 24, 40, 0.05);
        }

        .progress-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 10px;
        }

        .progress-stage-title {
          font-size: 0.9rem;
          font-weight: 650;
          color: #3730a3;
        }

        .progress-pct {
          font-size: 0.82rem;
          font-weight: 700;
          padding: 2px 8px;
          border-radius: 12px;
          background: #e0e7ff;
          color: #4338ca;
        }

        .progress-track {
          width: 100%;
          height: 8px;
          background: #e2e8f0;
          border-radius: 999px;
          overflow: hidden;
          margin-bottom: 10px;
        }

        .progress-fill {
          height: 100%;
          border-radius: 999px;
          background: linear-gradient(90deg, #6366f1, #4f46e5);
          transition: width 0.35s ease;
        }

        .progress-footer {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .progress-elapsed {
          font-size: 0.8rem;
          color: #64748b;
          font-weight: 500;
        }

        .btn-cancel {
          background: #fff;
          border: 1px solid #cbd5e1;
          color: #64748b;
          padding: 3px 10px;
          border-radius: 6px;
          font-size: 0.76rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .btn-cancel:hover {
          background: #fef2f2;
          color: #b91c1c;
          border-color: #fca5a5;
        }

        .btn-retry {
          background: #fff;
          border: 1px solid #fecdca;
          color: #b42318;
          padding: 3px 10px;
          border-radius: 6px;
          font-size: 0.78rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .btn-retry:hover {
          background: #fee4e2;
        }

        .btn-dismiss {
          background: transparent;
          border: none;
          color: inherit;
          cursor: pointer;
          font-size: 0.9rem;
          padding: 0 4px;
          opacity: 0.7;
          line-height: 1;
        }

        .btn-dismiss:hover {
          opacity: 1;
        }

        /* KPI Cards in Comparison View */
        .kpi-card {
          padding: 12px;
          border-radius: 10px;
          border: 1px solid #eaecf0;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .kpi-label {
          font-size: 0.75rem;
          font-weight: 600;
        }

        .kpi-value {
          font-size: 1.35rem;
          font-weight: 750;
          line-height: 1.1;
        }

        /* Filter Buttons */
        .filter-btn {
          background: #f8fafc;
          border: 1px solid #e2e8f0;
          color: #475569;
          padding: 5px 12px;
          border-radius: 8px;
          font-size: 0.78rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .filter-btn:hover {
          background: #f1f5f9;
          color: #1e293b;
        }

        .filter-btn.active {
          background: #4f46e5;
          color: #ffffff;
          border-color: #4338ca;
          box-shadow: 0 1px 3px rgba(79, 70, 229, 0.2);
        }

        .active-chip {
          background: #e0e7ff !important;
          color: #3730a3 !important;
          border-color: #a5b4fc !important;
          font-weight: 700 !important;
        }

        /* Diff Badges */
        .diff-badge-added {
          background: #ecfdf3;
          color: #027a48;
          border: 1px solid #a6f4c5;
        }

        .diff-badge-modified {
          background: #fffaeb;
          color: #b54708;
          border: 1px solid #fedf89;
        }

        .diff-badge-removed {
          background: #fef3f2;
          color: #b42318;
          border: 1px solid #fecdca;
        }

        .diff-badge-unchanged {
          background: #f8fafc;
          color: #475569;
          border: 1px solid #e2e8f0;
        }

        /* Provenance Badges */
        .provenance-badge-source_evidence {
          background: #eff8ff;
          color: #175cd3;
          border: 1px solid #b2ddff;
        }

        .provenance-badge-ta_confirmed {
          background: #fdf4ff;
          color: #86198f;
          border: 1px solid #f5d0fe;
        }

        .provenance-badge-llm_hypothesis {
          background: #f0fdf4;
          color: #15803d;
          border: 1px solid #bbf7d0;
        }

        .provenance-badge-ekg_derived {
          background: #faf5ff;
          color: #6b21a8;
          border: 1px solid #e9d5ff;
        }
      `}</style>

      <div className="app-container">
        {/* Top Navbar — avatar, Ask Anything pill, AI mark + title, evaluation context button */}
        <header className="topbar">
          <div className="topbar-left">
            <span className="user-avatar">N</span>
          </div>

          <div className="topbar-center">
            <span className="ai-icon-box">AI</span>
            <div className="brand-text">
              <span className="brand-title">JD Understanding Agent</span>
              <span className="brand-subtitle">Intelligent job description analysis</span>
            </div>
          </div>

          <div className="topbar-right">
            <button className="context-btn" onClick={() => setActiveTab("workflow")}>
              AI Evaluation Context
            </button>
          </div>
        </header>

        <div className="sub-nav-wrap">
          <nav className="nav-tabs">
            <button
              className={`nav-btn ${activeTab === "workflow" ? "active" : ""}`}
              onClick={() => setActiveTab("workflow")}
            >
              <span>📋</span> Workflow
            </button>
            <button
              className={`nav-btn ${activeTab === "chat" ? "active" : ""}`}
              onClick={() => setActiveTab("chat")}
            >
              <span>💬</span> Chat
            </button>
            <button
              className={`nav-btn ${activeTab === "settings" ? "active" : ""}`}
              onClick={() => setActiveTab("settings")}
            >
              <span>⚙️</span> Settings
            </button>
          </nav>
        </div>

        <main className="main-content">
          {/* ========================================================================= */}
          {/* TAB 1: LINEAR JD WORKFLOW (Company -> Upload -> Analyse -> View -> Agent)  */}
          {/* ========================================================================= */}
          {activeTab === "workflow" && (
            <div>
              {/* Stepper Progress Indicator */}
              <div className="stepper">
                <div className={`step-item ${isStep1Done ? "completed" : "active"}`}>
                  <div className="step-circle">{isStep1Done ? "✓" : "1"}</div>
                  <span className="step-label">Company Details</span>
                </div>
                <div className={`step-item ${isStep2Done ? "completed" : currentStep === 2 ? "active" : ""}`}>
                  <div className="step-circle">{isStep2Done ? "✓" : "2"}</div>
                  <span className="step-label">Enter JD</span>
                </div>
                <div className={`step-item ${isStep3Done ? "completed" : currentStep === 3 ? "active" : ""}`}>
                  <div className="step-circle">{isStep3Done ? "✓" : "3"}</div>
                  <span className="step-label">Analyse</span>
                </div>
                <div className={`step-item ${isStep4Done ? "completed" : currentStep === 4 ? "active" : ""}`}>
                  <div className="step-circle">{isStep4Done ? "✓" : "4"}</div>
                  <span className="step-label">View / Download</span>
                </div>
                <div className={`step-item ${isStep5Done ? "completed" : currentStep === 5 ? "active" : ""}`}>
                  <div className="step-circle">{isStep5Done ? "✓" : "5"}</div>
                  <span className="step-label">Create Agent</span>
                </div>
              </div>

              {/* Step 1: Company Details */}
              <div className="card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                  <h3 style={{ margin: 0, fontSize: "1.1rem" }}>Step 1: Company & Project Details</h3>
                  {isStep1Done && <span className="status-pill status-ready">✓ Saved</span>}
                </div>
                <form onSubmit={handleSaveCompanyDetails} className="form-grid">
                  <div className="form-group">
                    <label>Company Name *</label>
                    <input
                      type="text"
                      className="input-text"
                      value={companyDetails.companyName}
                      onChange={(e) => setCompanyDetails({ ...companyDetails, companyName: e.target.value })}
                      placeholder="e.g. Acme Corp"
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label>Department / Team</label>
                    <input
                      type="text"
                      className="input-text"
                      value={companyDetails.department}
                      onChange={(e) => setCompanyDetails({ ...companyDetails, department: e.target.value })}
                      placeholder="e.g. Engineering"
                    />
                  </div>
                  <div className="form-group">
                    <label>Project / Hiring Campaign</label>
                    <input
                      type="text"
                      className="input-text"
                      value={companyDetails.projectName}
                      onChange={(e) => setCompanyDetails({ ...companyDetails, projectName: e.target.value })}
                      placeholder="e.g. Q3 Hiring Drive"
                    />
                  </div>
                  <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "flex-end" }}>
                    <button type="submit" className="btn-primary">
                      Save & Continue to JD →
                    </button>
                  </div>
                </form>
              </div>

              {/* Step 2 & 3: Enter / Upload JD & Analyse */}
              <div className="card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                  <h3 style={{ margin: 0, fontSize: "1.1rem" }}>Step 2 & 3: Enter Job Description & Run Analysis</h3>
                  <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                    {agents.length > 0 && (
                      <button
                        type="button"
                        className="btn-secondary"
                        style={{ fontSize: "0.8rem", padding: "4px 10px" }}
                        onClick={handleResetForNewJD}
                      >
                        ➕ New JD / Agent
                      </button>
                    )}
                    {status && (
                      <span className={`status-pill ${statusConfig[status]?.className}`}>
                        {statusConfig[status]?.icon} {statusConfig[status]?.label}
                      </span>
                    )}
                  </div>
                </div>

                <div className="form-group" style={{ marginBottom: "16px" }}>
                  <label>Target Job Title</label>
                  <input
                    type="text"
                    className="input-text"
                    value={jobTitle}
                    onChange={(e) => setJobTitle(e.target.value)}
                    placeholder="e.g. Senior Backend Engineer"
                  />
                </div>

                <div className="form-group" style={{ marginBottom: "16px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <label>Job Description Content (Paste or Upload file) *</label>
                    <label className="btn-secondary" style={{ cursor: "pointer", fontSize: "0.8rem", padding: "4px 10px" }}>
                      📁 Upload File (.txt, .pdf, .docx)
                      <input type="file" accept=".txt,.pdf,.docx" onChange={handleFileUpload} style={{ display: "none" }} />
                    </label>
                  </div>
                  <textarea
                    className="textarea"
                    value={jdText}
                    onChange={(e) => {
                      setJdText(e.target.value);
                      setSelectedFile(null);
                    }}
                    placeholder="Paste the complete Job Description text here, or upload a .txt, .pdf, or .docx file..."
                  />
                  {selectedFile && (
                    <div style={{ marginTop: "6px", fontSize: "0.82rem", color: "#5b5ce2", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <span>📄 Ready to parse: <strong>{selectedFile.name}</strong> ({(selectedFile.size / 1024).toFixed(1)} KB)</span>
                      <button
                        type="button"
                        className="btn-ghost-dark"
                        style={{ fontSize: "0.75rem", color: "#f04438", border: "none", padding: "2px 6px" }}
                        onClick={() => {
                          setSelectedFile(null);
                          setJdText("");
                        }}
                      >
                        ✕ Remove File
                      </button>
                    </div>
                  )}
                </div>

                {/* Initial JD Analysis Progress Bar & Stage Indicator */}
                {status !== null && !TERMINAL_STATUSES.includes(status) && (
                  <div className="progress-card" style={{ marginBottom: "16px" }}>
                    <div className="progress-header">
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span className="spinner" style={{ borderColor: "#6366f1", borderTopColor: "transparent" }}></span>
                        <span className="progress-stage-title">
                          {analysisProgress.stageLabel || "Analyzing Job Description..."}
                        </span>
                      </div>
                      <span className="progress-pct">{analysisProgress.percent}%</span>
                    </div>
                    <div className="progress-track">
                      <div
                        className="progress-fill"
                        style={{ width: `${Math.min(100, Math.max(8, analysisProgress.percent))}%` }}
                      />
                    </div>
                    <div className="progress-footer">
                      <span className="progress-elapsed">⏱ Elapsed: {formatElapsed(nowTs - (analysisStartedAt || nowTs))}</span>
                      <button
                        type="button"
                        className="btn-cancel"
                        onClick={handleCancelAnalysis}
                        title="Cancel this analysis task"
                      >
                        ✕ Cancel Analysis
                      </button>
                    </div>
                  </div>
                )}

                {/* Notifications */}
                {analysisSuccessMsg && (
                  <div className="alert-success" style={{ marginBottom: "16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span>{analysisSuccessMsg}</span>
                    <button
                      type="button"
                      className="btn-dismiss"
                      onClick={() => setAnalysisSuccessMsg(null)}
                      title="Dismiss notification"
                    >
                      ✕
                    </button>
                  </div>
                )}

                {error && (
                  <div className="alert-error" style={{ marginBottom: "16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <span>❌ {error}</span>
                    </div>
                    <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                      <button
                        type="button"
                        className="btn-retry"
                        onClick={handleAnalyseJD}
                        title="Retry analysis"
                      >
                        🔄 Retry Analysis
                      </button>
                      <button
                        type="button"
                        className="btn-dismiss"
                        onClick={() => setError(null)}
                        title="Dismiss error"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                )}

                <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
                  <button
                    onClick={handleAnalyseJD}
                    disabled={(!jdText.trim() && !selectedFile) || (status !== null && !TERMINAL_STATUSES.includes(status))}
                    className="btn-primary"
                  >
                    {status !== null && !TERMINAL_STATUSES.includes(status) ? (
                      <>
                        <span className="spinner"></span> Analyzing JD ({analysisProgress.percent}%)...
                      </>
                    ) : (
                      "🚀 Analyse Job Description"
                    )}
                  </button>
                </div>
              </div>

              {/* Step 4: View / Download JD Context */}
              {isStep3Done && markdown && (
                <div className="card">
                  <div className="preview-header">
                    <div>
                      <h3 style={{ margin: 0, fontSize: "1.1rem" }}>Step 4: Generated JD Context (Specification v{specVersion})</h3>
                      <span style={{ fontSize: "0.82rem", color: "#667085" }}>
                        Analysis complete. Crisp Markdown and canonical JSON available below.
                      </span>
                    </div>
                    <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                      <div className="sub-tabs">
                        <button
                          className={`sub-tab-btn ${contextTab === "markdown" ? "active" : ""}`}
                          onClick={() => setContextTab("markdown")}
                        >
                          Markdown View {isEnrichedView && "(Enriched)"}
                        </button>
                        <button
                          className={`sub-tab-btn ${contextTab === "json" ? "active" : ""}`}
                          onClick={() => setContextTab("json")}
                        >
                          JSON Source of Truth
                        </button>
                        <button
                          className={`sub-tab-btn ${contextTab === "compare" ? "active" : ""}`}
                          onClick={() => {
                            setContextTab("compare");
                            fetchComparison(comparisonBaseContext, comparisonTargetContext);
                          }}
                        >
                          ⚡ Context Comparison
                        </button>
                      </div>
                      {isEnrichedView ? (
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span
                            style={{
                              fontSize: "0.78rem",
                              fontWeight: 600,
                              padding: "4px 10px",
                              borderRadius: "16px",
                              background: "#e0e7ff",
                              color: "#4338ca",
                              border: "1px solid #c7d2fe",
                            }}
                          >
                            ✨ Enriched TA Guidance (Ollama)
                          </span>
                          <button
                            type="button"
                            className="btn-secondary"
                            style={{ fontSize: "0.75rem", padding: "3px 8px" }}
                            onClick={() => handleToggleEnrichment(false)}
                            title="View original deterministic baseline markdown"
                          >
                            Show Baseline
                          </button>
                        </div>
                      ) : (
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span
                            style={{
                              fontSize: "0.78rem",
                              fontWeight: 600,
                              padding: "4px 10px",
                              borderRadius: "16px",
                              background: "#f1f5f9",
                              color: "#475569",
                              border: "1px solid #e2e8f0",
                            }}
                          >
                            ⚙ Deterministic Rule Engine
                          </span>
                          <button
                            type="button"
                            className="btn-secondary"
                            style={{ fontSize: "0.75rem", padding: "3px 8px" }}
                            onClick={() => handleToggleEnrichment(true)}
                            title="Switch back to Ollama enriched markdown"
                          >
                            Show Enriched
                          </button>
                        </div>
                      )}
                      <button
                        className="btn-secondary"
                        onClick={() =>
                          contextTab === "markdown"
                            ? downloadFile("job_specification.md", markdown, "text/markdown")
                            : downloadFile("job_specification.json", JSON.stringify(jsonData, null, 2), "application/json")
                        }
                      >
                        ⬇ Download {contextTab.toUpperCase()}
                      </button>
                    </div>
                  </div>

                  {contextTab === "compare" ? (
                    <div className="comparison-container" style={{ padding: "20px", background: "#fcfcfd" }}>
                      {/* Comparison Toolbar & Context Selector */}
                      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: "12px", marginBottom: "20px", paddingBottom: "16px", borderBottom: "1px solid #eaecf0" }}>
                        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px" }}>
                          <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "#344054" }}>Compare:</span>
                          <button
                            type="button"
                            className={`btn-secondary ${comparisonBaseContext === "baseline" && comparisonTargetContext === "resolved" ? "active-chip" : ""}`}
                            style={{ fontSize: "0.78rem", padding: "4px 10px" }}
                            onClick={() => {
                              setComparisonBaseContext("baseline");
                              setComparisonTargetContext("resolved");
                              fetchComparison("baseline", "resolved");
                            }}
                          >
                            Baseline vs Ambiguity-Resolved
                          </button>
                          <button
                            type="button"
                            className={`btn-secondary ${comparisonBaseContext === "baseline" && comparisonTargetContext === "enriched" ? "active-chip" : ""}`}
                            style={{ fontSize: "0.78rem", padding: "4px 10px" }}
                            onClick={() => {
                              setComparisonBaseContext("baseline");
                              setComparisonTargetContext("enriched");
                              fetchComparison("baseline", "enriched");
                            }}
                          >
                            Baseline vs Enriched Guidance
                          </button>
                          <button
                            type="button"
                            className={`btn-secondary ${comparisonBaseContext === "enriched" && comparisonTargetContext === "resolved" ? "active-chip" : ""}`}
                            style={{ fontSize: "0.78rem", padding: "4px 10px" }}
                            onClick={() => {
                              setComparisonBaseContext("enriched");
                              setComparisonTargetContext("resolved");
                              fetchComparison("enriched", "resolved");
                            }}
                          >
                            Enriched Guidance vs Ambiguity-Resolved
                          </button>
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                          <span style={{ fontSize: "0.82rem", color: "#667085" }}>
                            {comparisonData?.has_resolved
                              ? "✓ Ambiguity-Resolved v" + (comparisonData?.contexts.resolved?.version || 2) + " active"
                              : "⚠️ Resolved context pending TA clarification"}
                          </span>
                          <button
                            type="button"
                            className="btn-secondary"
                            style={{ fontSize: "0.78rem", padding: "4px 10px" }}
                            onClick={() => fetchComparison(comparisonBaseContext, comparisonTargetContext)}
                            disabled={isLoadingComparison}
                          >
                            {isLoadingComparison ? "Refreshing..." : "🔄 Refresh"}
                          </button>
                        </div>
                      </div>

                      {/* Summary KPI Counters */}
                      {comparisonData && (
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "12px", marginBottom: "20px" }}>
                          <div className="kpi-card" style={{ borderColor: "#a6f4c5", background: "#f6fef9" }}>
                            <span className="kpi-label" style={{ color: "#027a48" }}>+ Added Reqs</span>
                            <span className="kpi-value" style={{ color: "#027a48" }}>{comparisonData.diff.counts.added}</span>
                          </div>
                          <div className="kpi-card" style={{ borderColor: "#fedf89", background: "#fffaeb" }}>
                            <span className="kpi-label" style={{ color: "#b54708" }}>~ Modified Reqs</span>
                            <span className="kpi-value" style={{ color: "#b54708" }}>{comparisonData.diff.counts.modified}</span>
                          </div>
                          <div className="kpi-card" style={{ borderColor: "#fecdca", background: "#fef3f2" }}>
                            <span className="kpi-label" style={{ color: "#b42318" }}>- Removed Reqs</span>
                            <span className="kpi-value" style={{ color: "#b42318" }}>{comparisonData.diff.counts.removed}</span>
                          </div>
                          <div className="kpi-card" style={{ borderColor: "#e2e8f0", background: "#f8fafc" }}>
                            <span className="kpi-label" style={{ color: "#475569" }}>= Unchanged Reqs</span>
                            <span className="kpi-value" style={{ color: "#475569" }}>{comparisonData.diff.counts.unchanged}</span>
                          </div>
                          <div className="kpi-card" style={{ borderColor: "#c7d2fe", background: "#eef2ff" }}>
                            <span className="kpi-label" style={{ color: "#3730a3" }}>✓ Resolved Ambiguities</span>
                            <span className="kpi-value" style={{ color: "#3730a3" }}>{comparisonData.ambiguities.counts.resolved}</span>
                          </div>
                          <div className="kpi-card" style={{ borderColor: "#fed7aa", background: "#fff7ed" }}>
                            <span className="kpi-label" style={{ color: "#c2410c" }}>! Open Ambiguities</span>
                            <span className="kpi-value" style={{ color: "#c2410c" }}>{comparisonData.ambiguities.counts.unresolved}</span>
                          </div>
                        </div>
                      )}

                      {/* Filter Bar & View Mode Toggle */}
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "8px" }}>
                        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                          {(["all", "added", "modified", "removed", "unchanged"] as const).map((filterKey) => (
                            <button
                              key={filterKey}
                              type="button"
                              className={`filter-btn ${comparisonFilter === filterKey ? "active" : ""}`}
                              onClick={() => setComparisonFilter(filterKey)}
                            >
                              {filterKey === "all" ? "All Requirements" : filterKey.charAt(0).toUpperCase() + filterKey.slice(1)}
                              {comparisonData && filterKey !== "all" ? ` (${comparisonData.diff.counts[filterKey]})` : ""}
                            </button>
                          ))}
                        </div>
                        <div style={{ display: "flex", gap: "6px" }}>
                          <button
                            type="button"
                            className={`filter-btn ${comparisonViewMode === "unified" ? "active" : ""}`}
                            onClick={() => setComparisonViewMode("unified")}
                          >
                            Unified Diff
                          </button>
                          <button
                            type="button"
                            className={`filter-btn ${comparisonViewMode === "side_by_side" ? "active" : ""}`}
                            onClick={() => setComparisonViewMode("side_by_side")}
                          >
                            Side-by-Side
                          </button>
                        </div>
                      </div>

                      {/* Diff Requirements List */}
                      {isLoadingComparison ? (
                        <div style={{ textAlign: "center", padding: "40px", color: "#667085" }}>
                          <span className="spinner"></span> Loading context comparison...
                        </div>
                      ) : !comparisonData ? (
                        <div style={{ textAlign: "center", padding: "40px", color: "#667085" }}>
                          No comparison data available yet.
                        </div>
                      ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "28px" }}>
                          {/* Filtered Requirements */}
                          {(() => {
                            const { added, modified, removed, unchanged } = comparisonData.diff;
                            let items: RequirementDiffItem[] = [];
                            if (comparisonFilter === "all") items = [...added, ...modified, ...removed, ...unchanged];
                            else if (comparisonFilter === "added") items = added;
                            else if (comparisonFilter === "modified") items = modified;
                            else if (comparisonFilter === "removed") items = removed;
                            else if (comparisonFilter === "unchanged") items = unchanged;

                            if (items.length === 0) {
                              return (
                                <div style={{ textAlign: "center", padding: "30px", background: "#f8fafc", borderRadius: "10px", color: "#667085" }}>
                                  No requirements matching filter "{comparisonFilter}".
                                </div>
                              );
                            }

                            return items.map((req, rIdx) => {
                              const isAdded = req.diff_status === "added";
                              const isModified = req.diff_status === "modified";
                              const isRemoved = req.diff_status === "removed";
                              const isTAConfirmed = req.provenance_type === "ta_confirmed";

                              const cardBorderColor = isAdded
                                ? "#a6f4c5"
                                : isModified
                                ? "#fedf89"
                                : isRemoved
                                ? "#fecdca"
                                : "#e2e8f0";

                              const cardBg = isAdded
                                ? "#f6fef9"
                                : isModified
                                ? "#fffdf5"
                                : isRemoved
                                ? "#fef3f2"
                                : "#ffffff";

                              return (
                                <div
                                  key={`diff_req_${rIdx}`}
                                  style={{
                                    padding: "16px",
                                    borderRadius: "10px",
                                    border: `1px solid ${cardBorderColor}`,
                                    background: cardBg,
                                  }}
                                >
                                  {/* Header Badges */}
                                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px", gap: "8px", flexWrap: "wrap" }}>
                                    <div style={{ display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap" }}>
                                      {/* Diff Badge */}
                                      <span
                                        className={`diff-badge diff-badge-${req.diff_status}`}
                                        style={{ fontSize: "0.74rem", fontWeight: 700, padding: "2px 8px", borderRadius: "4px" }}
                                      >
                                        {req.diff_badge}
                                      </span>

                                      {/* Priority Badge */}
                                      <span
                                        style={{
                                          fontSize: "0.74rem",
                                          fontWeight: 600,
                                          padding: "2px 8px",
                                          borderRadius: "4px",
                                          background: req.priority === "MUST_HAVE" ? "#ecfdf3" : req.priority === "PREFERRED" ? "#eff8ff" : "#fffaeb",
                                          color: req.priority === "MUST_HAVE" ? "#027a48" : req.priority === "PREFERRED" ? "#175cd3" : "#b54708",
                                          border: `1px solid ${req.priority === "MUST_HAVE" ? "#a6f4c5" : req.priority === "PREFERRED" ? "#b2ddff" : "#fedf89"}`,
                                        }}
                                      >
                                        {req.priority}
                                      </span>

                                      {/* Provenance Badge */}
                                      <span
                                        className={`provenance-badge provenance-badge-${req.provenance_type}`}
                                        style={{ fontSize: "0.74rem", fontWeight: 600, padding: "2px 8px", borderRadius: "4px" }}
                                      >
                                        {req.provenance_badge}
                                      </span>
                                    </div>

                                    {/* Author / Timestamp */}
                                    {req.author && (
                                      <span style={{ fontSize: "0.75rem", color: "#667085" }}>
                                        TA: <strong>{req.author}</strong>
                                      </span>
                                    )}
                                  </div>

                                  {/* Requirement Text */}
                                  <div style={{ fontSize: "0.94rem", fontWeight: 550, color: isRemoved ? "#b42318" : "#1e293b", marginBottom: "8px", textDecoration: isRemoved ? "line-through" : "none" }}>
                                    {req.text}
                                  </div>

                                  {/* Modified Changes breakdown */}
                                  {isModified && req.changes && req.changes.length > 0 && (
                                    <div style={{ marginBottom: "8px", padding: "8px 12px", background: "#fef3c7", borderRadius: "6px", fontSize: "0.82rem", color: "#92400e" }}>
                                      <strong>Changes:</strong>
                                      <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
                                        {req.changes.map((chg, cIdx) => (
                                          <li key={cIdx}>{chg}</li>
                                        ))}
                                      </ul>
                                    </div>
                                  )}

                                  {/* Source Evidence Quote */}
                                  {req.source_text && (
                                    <div style={{ fontSize: "0.8rem", color: "#475569", background: "rgba(0,0,0,0.02)", padding: "6px 10px", borderRadius: "6px", marginBottom: "6px" }}>
                                      <strong style={{ color: "#334155" }}>Source Evidence ({req.source_section || "JD"}):</strong>{" "}
                                      <em>"{req.source_text}"</em>
                                    </div>
                                  )}

                                  {/* TA Confirmed note */}
                                  {isTAConfirmed && (
                                    <div style={{ fontSize: "0.8rem", color: "#86198f", background: "#fdf4ff", padding: "6px 10px", borderRadius: "6px", border: "1px solid #f5d0fe" }}>
                                      <strong>TA-Confirmed Fact:</strong> Confirmed by {req.author || "TA Lead"}
                                      {req.timestamp ? ` at ${new Date(req.timestamp).toLocaleString()}` : ""}
                                    </div>
                                  )}

                                  {/* Enriched Guidance Signals if present */}
                                  {req.enriched_guidance && (
                                    <div style={{ marginTop: "10px", padding: "10px", background: "#f0fdf4", borderRadius: "6px", border: "1px solid #bbf7d0", fontSize: "0.82rem" }}>
                                      <div style={{ fontWeight: 600, color: "#166534", marginBottom: "4px" }}>
                                        ✨ Grounded TA Guidance (Ollama):
                                      </div>
                                      {req.enriched_guidance.technical_concept_summary && (
                                        <div style={{ color: "#1e293b", marginBottom: "4px" }}>
                                          <strong>Concept:</strong> {req.enriched_guidance.technical_concept_summary}
                                        </div>
                                      )}
                                      {req.enriched_guidance.screening_question && (
                                        <div style={{ color: "#1e293b", marginBottom: "4px" }}>
                                          <strong>Screening Question:</strong> {req.enriched_guidance.screening_question}
                                        </div>
                                      )}
                                      {req.enriched_guidance.strong_evidence_signals && req.enriched_guidance.strong_evidence_signals.length > 0 && (
                                        <div style={{ color: "#166534" }}>
                                          <strong>Strong Signals:</strong> {req.enriched_guidance.strong_evidence_signals.join(" • ")}
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                              );
                            });
                          })()}
                        </div>
                      )}

                      {/* Ambiguities & Clarifications Resolution Status */}
                      {comparisonData && (
                        <div style={{ marginTop: "24px", paddingTop: "20px", borderTop: "1px solid #eaecf0" }}>
                          <h4 style={{ margin: "0 0 14px 0", fontSize: "1.05rem", color: "#101828", display: "flex", alignItems: "center", gap: "8px" }}>
                            <span>Ambiguities Status (Resolved vs Unresolved)</span>
                          </h4>

                          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "16px" }}>
                            {/* Resolved Ambiguities */}
                            <div style={{ background: "#ffffff", border: "1px solid #a6f4c5", borderRadius: "10px", padding: "16px" }}>
                              <h5 style={{ margin: "0 0 10px 0", color: "#027a48", display: "flex", alignItems: "center", gap: "6px" }}>
                                <span>✓ Resolved Ambiguities ({comparisonData.ambiguities.counts.resolved})</span>
                              </h5>
                              {comparisonData.ambiguities.resolved.length === 0 ? (
                                <p style={{ fontSize: "0.82rem", color: "#667085", margin: 0 }}>No resolved ambiguities yet.</p>
                              ) : (
                                <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                                  {comparisonData.ambiguities.resolved.map((amb, aIdx) => (
                                    <div key={aIdx} style={{ padding: "10px", background: "#f6fef9", borderRadius: "6px", border: "1px solid #d1fadf", fontSize: "0.83rem" }}>
                                      <div style={{ fontWeight: 600, color: "#1e293b", marginBottom: "4px" }}>
                                        {amb.question_text}
                                      </div>
                                      <div style={{ color: "#027a48", marginBottom: "2px" }}>
                                        <strong>TA Answer:</strong> {amb.answer_text}
                                      </div>
                                      <div style={{ fontSize: "0.75rem", color: "#667085" }}>
                                        Confirmed by: <strong>{amb.answered_by || "TA"}</strong>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>

                            {/* Unresolved Ambiguities */}
                            <div style={{ background: "#ffffff", border: "1px solid #fedf89", borderRadius: "10px", padding: "16px" }}>
                              <h5 style={{ margin: "0 0 10px 0", color: "#b54708", display: "flex", alignItems: "center", gap: "6px" }}>
                                <span>⚠️ Unresolved Ambiguities ({comparisonData.ambiguities.counts.unresolved})</span>
                              </h5>
                              {comparisonData.ambiguities.unresolved.length === 0 ? (
                                <p style={{ fontSize: "0.82rem", color: "#027a48", margin: 0 }}>✓ All detected ambiguities have been confirmed and resolved.</p>
                              ) : (
                                <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                                  {comparisonData.ambiguities.unresolved.map((amb, aIdx) => (
                                    <div key={aIdx} style={{ padding: "10px", background: "#fffdf5", borderRadius: "6px", border: "1px solid #fef08a", fontSize: "0.83rem" }}>
                                      <div style={{ fontWeight: 600, color: "#1e293b", marginBottom: "4px" }}>
                                        {amb.question_text}
                                      </div>
                                      {amb.why_ambiguous && (
                                        <div style={{ color: "#64748b", marginBottom: "4px" }}>
                                          <strong>Context:</strong> {amb.why_ambiguous}
                                        </div>
                                      )}
                                      <div style={{ display: "flex", gap: "6px", marginTop: "4px" }}>
                                        <span style={{ fontSize: "0.72rem", padding: "2px 6px", borderRadius: "4px", background: amb.is_blocking ? "#fee2e2" : "#fef3c7", color: amb.is_blocking ? "#991b1b" : "#92400e", fontWeight: 600 }}>
                                          {amb.priority || "RECOMMENDED"}
                                        </span>
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="code-preview">
                      {contextTab === "markdown" ? (
                        <ReactMarkdown>{markdown}</ReactMarkdown>
                      ) : (
                        <pre style={{ margin: 0, fontFamily: "monospace", color: "#344054" }}>
                          {JSON.stringify(jsonData, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Ambiguities & Clarifications Requiring TA Input */}
              {isStep3Done && clarificationsData?.has_ambiguities && (
                <div className="card" style={{ borderLeft: "4px solid #f59e0b" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
                    <div>
                      <h3 style={{ margin: "0 0 4px 0", fontSize: "1.1rem", display: "flex", alignItems: "center", gap: "8px" }}>
                        <span>🔍 Ambiguities Requiring TA Clarification</span>
                        {clarificationsData.lifecycle_status === "FINALIZED" ? (
                          <span style={{ background: "#dcfce7", color: "#166534", fontSize: "0.75rem", padding: "2px 8px", borderRadius: "12px", fontWeight: 600 }}>
                            ✓ Finalized
                          </span>
                        ) : (
                          <span style={{ background: "#fef3c7", color: "#92400e", fontSize: "0.75rem", padding: "2px 8px", borderRadius: "12px", fontWeight: 600 }}>
                            Action Required
                          </span>
                        )}
                      </h3>
                      <p style={{ margin: 0, fontSize: "0.85rem", color: "#667085" }}>
                        The deterministic engine flagged the following ambiguous statements or missing parameters. Answer below to generate the final disambiguated specification.
                      </p>
                    </div>
                  </div>

                  {/* Progress Indicator during Ambiguity Resolution */}
                  {isResolvingClarifications && (
                    <div className="progress-card" style={{ marginBottom: "16px", borderColor: "#f59e0b" }}>
                      <div className="progress-header">
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <span className="spinner" style={{ borderColor: "#f59e0b", borderTopColor: "transparent" }}></span>
                          <span className="progress-stage-title" style={{ color: "#b45309" }}>
                            {resolveProgress.stageLabel || "Resolving clarifications..."}
                          </span>
                        </div>
                        <span className="progress-pct" style={{ background: "#fef3c7", color: "#92400e" }}>
                          {resolveProgress.percent}%
                        </span>
                      </div>
                      <div className="progress-track">
                        <div
                          className="progress-fill"
                          style={{
                            width: `${Math.min(100, Math.max(10, resolveProgress.percent))}%`,
                            background: "linear-gradient(90deg, #f59e0b, #d97706)",
                          }}
                        />
                      </div>
                      <div className="progress-footer">
                        <span style={{ fontSize: "0.8rem", color: "#667085" }}>Updating master domain context and generating final specification v2+</span>
                        <button
                          type="button"
                          className="btn-cancel"
                          onClick={handleCancelResolve}
                          title="Cancel ambiguity resolution"
                        >
                          ✕ Cancel
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Success Banner */}
                  {resolveSuccessMsg && (
                    <div className="alert-success" style={{ marginBottom: "14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span>{resolveSuccessMsg}</span>
                      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ fontSize: "0.78rem", padding: "3px 8px" }}
                          onClick={() => {
                            setContextTab("compare");
                            fetchComparison("baseline", "resolved");
                          }}
                        >
                          ⚡ View Comparison Diff
                        </button>
                        <button
                          type="button"
                          className="btn-dismiss"
                          onClick={() => setResolveSuccessMsg(null)}
                          title="Dismiss notification"
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Error Banner with Retry */}
                  {resolveError && (
                    <div className="alert-error" style={{ marginBottom: "14px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span>❌ {resolveError}</span>
                      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                        <button
                          type="button"
                          className="btn-retry"
                          onClick={handleResolveClarifications}
                          title="Retry resolving clarifications"
                        >
                          🔄 Retry Resolution
                        </button>
                        <button
                          type="button"
                          className="btn-dismiss"
                          onClick={() => setResolveError(null)}
                          title="Dismiss error"
                        >
                          ✕
                        </button>
                      </div>
                    </div>
                  )}

                  {/* List of Ambiguities / Questions */}
                  <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "16px" }}>
                    {/* 1. First-class Clarification Questions (includes JD technical ambiguities, contextual phrasing, & metadata) */}
                    {clarificationsData.questions && clarificationsData.questions.length > 0 && (
                      clarificationsData.questions.map((q) => (
                        <div
                          key={q.question_key}
                          style={{
                            padding: "14px",
                            background: "#f8fafc",
                            borderRadius: "8px",
                            border: "1px solid #e2e8f0",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "6px", gap: "8px" }}>
                            <span style={{ fontWeight: 600, fontSize: "0.92rem", color: "#1e293b", flex: 1 }}>
                              {q.question_text}
                            </span>
                            <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                              <span
                                style={{
                                  fontSize: "0.72rem",
                                  fontWeight: 600,
                                  padding: "2px 8px",
                                  borderRadius: "4px",
                                  background: "#f1f5f9",
                                  color: "#475569",
                                  textTransform: "capitalize",
                                }}
                              >
                                {q.category.replace(/_/g, " ")}
                              </span>
                              <span
                                style={{
                                  fontSize: "0.72rem",
                                  fontWeight: 600,
                                  padding: "2px 8px",
                                  borderRadius: "4px",
                                  background: q.priority === "BLOCKING" ? "#fee2e2" : "#fef3c7",
                                  color: q.priority === "BLOCKING" ? "#991b1b" : "#92400e",
                                }}
                              >
                                {q.priority}
                              </span>
                            </div>
                          </div>

                          {q.rationale && (
                            <div style={{ fontSize: "0.82rem", color: "#64748b", marginBottom: "8px" }}>
                              <strong>Context:</strong> {q.rationale}
                            </div>
                          )}

                          {/* Quick-select chips if suggested_options are provided */}
                          {q.suggested_options && q.suggested_options.length > 0 && (
                            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "8px" }}>
                              {q.suggested_options.map((opt, oIdx) => (
                                <button
                                  key={oIdx}
                                  type="button"
                                  onClick={() =>
                                    setClarificationAnswers((prev) => ({
                                      ...prev,
                                      [q.question_key]: opt,
                                    }))
                                  }
                                  style={{
                                    fontSize: "0.75rem",
                                    padding: "3px 8px",
                                    borderRadius: "12px",
                                    border: clarificationAnswers[q.question_key] === opt ? "1px solid #4f46e5" : "1px solid #cbd5e1",
                                    background: clarificationAnswers[q.question_key] === opt ? "#e0e7ff" : "#fff",
                                    color: clarificationAnswers[q.question_key] === opt ? "#4338ca" : "#334155",
                                    cursor: "pointer",
                                  }}
                                >
                                  {opt}
                                </button>
                              ))}
                            </div>
                          )}

                          <input
                            type="text"
                            className="input-text"
                            style={{ width: "100%" }}
                            placeholder={q.answer || "Enter TA clarification or select an option above..."}
                            value={clarificationAnswers[q.question_key] || ""}
                            onChange={(e) =>
                              setClarificationAnswers((prev) => ({
                                ...prev,
                                [q.question_key]: e.target.value,
                              }))
                            }
                          />
                        </div>
                      ))
                    )}

                    {/* 2. Any additional standalone ambiguities from JD not already covered */}
                    {clarificationsData.ambiguities && clarificationsData.ambiguities.length > 0 && (
                      clarificationsData.ambiguities
                        .filter((a: any) => {
                          const statement = (a.statement || "").trim().toLowerCase();
                          return !(clarificationsData.questions || []).some((q) =>
                            q.question_text.toLowerCase().includes(statement.slice(0, 30))
                          );
                        })
                        .map((a: any, idx: number) => (
                          <div key={`amb_${idx}`} style={{ padding: "14px", background: "#f8fafc", borderRadius: "8px", border: "1px solid #e2e8f0" }}>
                            <div style={{ fontWeight: 600, fontSize: "0.92rem", color: "#1e293b", marginBottom: "4px" }}>
                              "{a.statement}"
                            </div>
                            <div style={{ fontSize: "0.82rem", color: "#64748b", marginBottom: "8px" }}>
                              <strong>Why ambiguous:</strong> {a.why_ambiguous}
                            </div>
                            <input
                              type="text"
                              className="input-text"
                              style={{ width: "100%" }}
                              placeholder="Provide clarification (e.g. Mandatory, Preferred, or specific range)..."
                              value={clarificationAnswers[`amb_${idx}`] || ""}
                              onChange={(e) =>
                                setClarificationAnswers((prev) => ({
                                  ...prev,
                                  [`amb_${idx}`]: e.target.value,
                                }))
                              }
                            />
                          </div>
                        ))
                    )}
                  </div>

                  <div style={{ display: "flex", justifyContent: "flex-end" }}>
                    <button
                      className="btn-primary"
                      disabled={isResolvingClarifications}
                      onClick={handleResolveClarifications}
                      style={{ background: "#d97706", borderColor: "#b45309" }}
                    >
                      {isResolvingClarifications
                        ? "⏳ Resolving & Generating Final Markdown..."
                        : "✓ Confirm Answers & Generate Final Specification"}
                    </button>
                  </div>
                </div>
              )}

              {/* Step 5: Create Agent */}
              {isStep3Done && (
                <div className="card" style={{ borderColor: "#6366f1" }}>
                  <h3 style={{ margin: "0 0 8px 0", fontSize: "1.1rem" }}>Step 5: Create JD Agent</h3>
                  <p style={{ margin: "0 0 16px 0", fontSize: "0.88rem", color: "#667085" }}>
                    Finalize your configuration to register this JD agent.
                  </p>

                  {createdAgentSuccess && <div className="alert-success">✓ {createdAgentSuccess}</div>}

                  <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
                    <input
                      type="text"
                      className="input-text"
                      style={{ flex: 1 }}
                      placeholder="Agent Name (e.g. Senior Backend Screener)"
                      value={agentNameInput}
                      onChange={(e) => setAgentNameInput(e.target.value)}
                    />
                    <button className="btn-primary" onClick={handleCreateAgent}>
                      ✨ Launch the agent
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB 2: DEDICATED JD CHAT PAGE — styled as the "Ask Anything about JD" panel */}
          {/* ========================================================================= */}
          {activeTab === "chat" && (
            <div className="chat-container">
              {/* Dark Chat Header */}
              <div className="chat-topbar">
                <div style={{ display: "flex", alignItems: "center", gap: "12px", minWidth: 0 }}>
                  <span style={{ fontSize: "1.3rem" }}>✨</span>
                  <div style={{ minWidth: 0 }}>
                    <h4 style={{ margin: 0, fontSize: "1rem", color: "#fff", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {activeAgentForChat ? activeAgentForChat.agentName : "Ask Anything about JD"}
                    </h4>
                    <span style={{ fontSize: "0.76rem", color: "rgba(255,255,255,0.6)" }}>
                      {activeAgentForChat
                        ? `${activeAgentForChat.companyDetails.companyName} • Spec v${activeAgentForChat.specificationVersion}`
                        : "Scans converted .md context to answer questions"}
                    </span>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <select
                    className="select select-on-dark"
                    style={{ width: "auto", minWidth: "180px" }}
                    value={selectedAgentId}
                    onChange={(e) => setSelectedAgentId(e.target.value)}
                  >
                    {markdown && <option value="current">Current Active JD Context</option>}
                    {agents.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.agentName} ({a.companyDetails.companyName})
                      </option>
                    ))}
                    {!markdown && agents.length === 0 && <option value="none">No Agent Created Yet</option>}
                  </select>
                  <button className="btn-ghost-dark" onClick={handleClearChatHistory}>
                    Clear History
                  </button>
                  <button className="chat-close-btn" onClick={() => setActiveTab("workflow")} title="Close">
                    ✕
                  </button>
                </div>
              </div>

              {/* Context Status */}
              <div className="context-status-row">
                <span>Context Status:</span>
                {hasReadyContext ? (
                  <span className="context-status-badge ready">✓ Markdown Ready</span>
                ) : (
                  <span className="context-status-badge pending">○ Pending Analysis</span>
                )}
              </div>

              {/* Message Thread */}
              <div className="chat-messages">
                {currentChatMessages.map((msg) => (
                  <div key={msg.id} className={`message-bubble ${msg.sender === "user" ? "message-user" : "message-assistant"}`}>
                    <ReactMarkdown>{msg.text}</ReactMarkdown>
                  </div>
                ))}
                {isChatLoading && (
                  <div className="message-bubble message-assistant" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span className="spinner"></span> Generating response...
                  </div>
                )}
              </div>

              {/* Suggested Questions */}
              <div className="prompt-chips">
                <button className="chip" onClick={() => handleSendChatMessage("What technical skills and tools are required?")}>
                  Technical Skills
                </button>
                <button className="chip" onClick={() => handleSendChatMessage("What is the required experience level?")}>
                  Experience Level
                </button>
                <button className="chip" onClick={() => handleSendChatMessage("What is the remote work policy for this role?")}>
                  Remote Policy
                </button>
                <button className="chip" onClick={() => handleSendChatMessage("What responsibilities are outlined?")}>
                  Responsibilities
                </button>
              </div>

              {/* Input Bar */}
              <div className="chat-input-bar">
                <input
                  type="text"
                  className="input-text"
                  style={{ flex: 1 }}
                  placeholder="Ask anything about the JD..."
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSendChatMessage()}
                />
                <button className="btn-primary" onClick={() => handleSendChatMessage()} disabled={isChatLoading || !chatInput.trim()}>
                  Send
                </button>
              </div>
            </div>
          )}

          {/* ========================================================================= */}
          {/* TAB 3: AGENT SETTINGS & CONTEXT REGENERATION                              */}
          {/* ========================================================================= */}
          {activeTab === "settings" && (
            <div>
              <h2 style={{ marginTop: 0, marginBottom: "20px" }}>Agent Management & Context Regeneration</h2>

              {agents.length === 0 ? (
                <div className="card" style={{ textAlign: "center", padding: "40px" }}>
                  <p style={{ color: "#667085", fontSize: "1rem", margin: "0 0 16px 0" }}>
                    No agents created yet. Complete the <strong>Linear Setup Workflow</strong> to create your first JD agent.
                  </p>
                  <button className="btn-primary" onClick={() => setActiveTab("workflow")}>
                    Go to Workflow Setup →
                  </button>
                </div>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: "24px" }}>
                  {/* Left Column: Created Agents List */}
                  <div>
                    <h4 style={{ margin: "0 0 12px 0", color: "#344054" }}>Created Agents ({agents.length})</h4>
                    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                      {agents.map((a) => (
                        <div
                          key={a.id}
                          className={`agent-card ${selectedSettingAgentId === a.id ? "selected" : ""}`}
                          onClick={() => setSelectedSettingAgentId(a.id)}
                          style={{ cursor: "pointer" }}
                        >
                          <div>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                              <h4 style={{ margin: "0 0 4px 0", fontSize: "0.98rem" }}>{a.agentName}</h4>
                              <span className="status-pill status-ready">v{a.specificationVersion}</span>
                            </div>
                            <p style={{ margin: 0, fontSize: "0.82rem", color: "#667085" }}>{a.title}</p>
                            <p style={{ margin: "4px 0 0 0", fontSize: "0.78rem", color: "#667085" }}>
                              {a.companyDetails.companyName} • Updated {a.updatedAt}
                            </p>
                          </div>
                          <div style={{ marginTop: "12px", display: "flex", gap: "8px" }}>
                            <button
                              className="btn-secondary"
                              style={{ padding: "4px 10px", fontSize: "0.78rem" }}
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedAgentId(a.id);
                                setActiveTab("chat");
                              }}
                            >
                              💬 Chat
                            </button>
                            <button className="btn-secondary" style={{ padding: "4px 10px", fontSize: "0.78rem" }}>
                              ⚙️ Edit Settings
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Right Column: Settings & Context Regeneration Form */}
                  {selectedSettingAgentId && (
                    <div className="card">
                      <h3 style={{ margin: "0 0 8px 0" }}>Agent Settings & Context Regeneration</h3>
                      <p style={{ margin: "0 0 20px 0", fontSize: "0.85rem", color: "#667085" }}>
                        Update company details or JD text below. Clicking <strong>Generate Updated Context</strong> will re-analyze the JD, update the specification version, and re-point this existing agent without creating duplicates.
                      </p>

                      {regenSuccessMsg && <div className="alert-success">✓ {regenSuccessMsg}</div>}
                      {regenStatus && <div className="alert-success" style={{ color: "#6941c6", borderColor: "rgba(105,65,198,0.18)" }}>◌ {regenStatus}</div>}

                      <div className="form-grid" style={{ marginBottom: "20px" }}>
                        <div className="form-group">
                          <label>Job Title</label>
                          <input
                            type="text"
                            className="input-text"
                            value={editTitle}
                            onChange={(e) => setEditTitle(e.target.value)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Company Name</label>
                          <input
                            type="text"
                            className="input-text"
                            value={editCompany.companyName}
                            onChange={(e) => setEditCompany({ ...editCompany, companyName: e.target.value })}
                          />
                        </div>
                        <div className="form-group">
                          <label>Department</label>
                          <input
                            type="text"
                            className="input-text"
                            value={editCompany.department}
                            onChange={(e) => setEditCompany({ ...editCompany, department: e.target.value })}
                          />
                        </div>
                      </div>

                      <div className="form-group" style={{ marginBottom: "24px" }}>
                        <label>Job Description Text</label>
                        <textarea
                          className="textarea"
                          value={editJdText}
                          onChange={(e) => setEditJdText(e.target.value)}
                          style={{ minHeight: "240px" }}
                        />
                      </div>

                      <div style={{ display: "flex", justifyContent: "flex-end" }}>
                        <button
                          className="btn-primary"
                          onClick={handleRegenerateAgentContext}
                          disabled={isRegenerating || !editJdText.trim()}
                        >
                          {isRegenerating ? (
                            <>
                              <span className="spinner"></span> Regenerating Context...
                            </>
                          ) : (
                            "🔄 Generate Updated Context & Re-point Agent"
                          )}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </>
  );
}