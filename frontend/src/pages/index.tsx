"use client";

import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import {
  uploadJD,
  analyzeJD,
  getAnalysisStatus,
  getMarkdown,
  getJson,
  askJDChatbot,
  ProcessingStatus,
  CompanyDetails,
  CreatedAgent,
} from "@/lib/api";

const POLL_INTERVAL_MS = 1500;
const TERMINAL_STATUSES: ProcessingStatus[] = ["READY", "NEEDS_REVIEW", "FAILED"];

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

export default function Home() {
  // Navigation
  const [activeTab, setActiveTab] = useState<"workflow" | "chat" | "settings">("workflow");

  // Linear Workflow State (Step 1 -> 5)
  const [companyDetails, setCompanyDetails] = useState<CompanyDetails>({
    companyName: "Acme Corp",
    department: "Engineering",
    projectName: "Backend Hiring Q3",
  });
  const [isCompanySaved, setIsCompanySaved] = useState(false);

  const [jobTitle, setJobTitle] = useState("Senior Backend Engineer");
  const [jdText, setJdText] = useState("");
  const [jdId, setJdId] = useState<string | null>(null);
  const [status, setStatus] = useState<ProcessingStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [jsonData, setJsonData] = useState<Record<string, unknown> | null>(null);
  const [specVersion, setSpecVersion] = useState<number>(1);
  const [contextTab, setContextTab] = useState<"markdown" | "json">("markdown");

  // Agent Creation
  const [agents, setAgents] = useState<CreatedAgent[]>([]);
  const [agentNameInput, setAgentNameInput] = useState("");
  const [createdAgentSuccess, setCreatedAgentSuccess] = useState<string | null>(null);

  // Dedicated Chat State
  const [selectedAgentId, setSelectedAgentId] = useState<string>("current");
  const [chatMessages, setChatMessages] = useState<Array<{ id: string; sender: "user" | "assistant"; text: string }>>([
    {
      id: "welcome",
      sender: "assistant",
      text: "Hello! I am your JD AI Assistant. I scan your Job Description Markdown context to answer any queries about requirements, technical skills, experience, remote policies, and role responsibilities. Ask me anything!",
    },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [isChatLoading, setIsChatLoading] = useState(false);

  // Settings & Regeneration State
  const [selectedSettingAgentId, setSelectedSettingAgentId] = useState<string | null>(null);
  const [editCompany, setEditCompany] = useState<CompanyDetails>({ companyName: "", department: "", projectName: "" });
  const [editTitle, setEditTitle] = useState("");
  const [editJdText, setEditJdText] = useState("");
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [regenStatus, setRegenStatus] = useState<string | null>(null);
  const [regenSuccessMsg, setRegenSuccessMsg] = useState<string | null>(null);

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

  // Derived Workflow Progress Step (1 to 5)
  const isStep1Done = isCompanySaved || Boolean(companyDetails.companyName.trim());
  const isStep2Done = Boolean(jdText.trim());
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

  // Step 3 Analyse Handler
  async function handleAnalyseJD() {
    if (!jdText.trim()) return;
    setError(null);
    setMarkdown(null);
    setJsonData(null);
    setCreatedAgentSuccess(null);

    try {
      const { jd_id } = await uploadJD(
        companyDetails.projectName.trim() || "default-project",
        jdText,
        jobTitle.trim() || "Untitled JD"
      );
      setJdId(jd_id);
      setStatus("UPLOADED");
      await analyzeJD(jd_id);
      pollStatus(jd_id);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function pollStatus(id: string) {
    const interval = setInterval(async () => {
      try {
        const { status: s, error_message } = await getAnalysisStatus(id);
        setStatus(s);
        if (TERMINAL_STATUSES.includes(s)) {
          clearInterval(interval);
          if (s === "FAILED") {
            setError(error_message || "Processing failed.");
            return;
          }
          const [mdRes, jsonRes] = await Promise.all([getMarkdown(id), getJson(id)]);
          setMarkdown(mdRes.markdown);
          setJsonData(jsonRes.json);
          setSpecVersion(mdRes.specification_version || 1);
        }
      } catch (e) {
        clearInterval(interval);
        setError((e as Error).message);
      }
    }, POLL_INTERVAL_MS);
  }

  // Step 5 Create Agent Handler
  function handleCreateAgent() {
    if (!markdown || !jdId) return;
    const name = agentNameInput.trim() || `${jobTitle} Agent`;
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
      createdAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      updatedAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setAgents((prev) => [newAgent, ...prev]);
    setSelectedAgentId(newAgent.id);
    setCreatedAgentSuccess(`Agent "${name}" successfully created!`);
    setAgentNameInput("");
  }

  // File Upload Handler
  function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
      const text = evt.target?.result as string;
      if (text) {
        setJdText(text);
        if (!jobTitle || jobTitle === "Senior Backend Engineer") {
          setJobTitle(file.name.replace(/\.[^/.]+$/, "").replace(/_/g, " "));
        }
      }
    };
    reader.readAsText(file);
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

  // Dedicated Chat Send Handler
  async function handleSendChatMessage(textToSend?: string) {
    const q = (textToSend ?? chatInput).trim();
    if (!q || isChatLoading) return;

    const userMsgId = Date.now().toString();
    setChatMessages((prev) => [...prev, { id: userMsgId, sender: "user", text: q }]);
    if (!textToSend) setChatInput("");
    setIsChatLoading(true);

    try {
      let targetJdId: string | null = null;
      let contextToUse: string | null = null;

      if (selectedAgentId !== "current") {
        const agent = agents.find((a) => a.id === selectedAgentId);
        if (agent) {
          targetJdId = agent.jdId;
          contextToUse = agent.markdown;
        }
      } else {
        targetJdId = jdId;
        contextToUse = markdown || (jdText.trim() ? `# Job Description\n\n${jdText}` : null);
      }

      const { answer } = await askJDChatbot(targetJdId, q, contextToUse);
      setChatMessages((prev) => [
        ...prev,
        { id: (Date.now() + 1).toString(), sender: "assistant", text: answer },
      ]);
    } catch (e) {
      setChatMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: "assistant",
          text: `⚠️ **Error:** ${(e as Error).message}`,
        },
      ]);
    } finally {
      setIsChatLoading(false);
    }
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

    setIsRegenerating(true);
    setRegenStatus("Uploading updated JD...");
    setRegenSuccessMsg(null);

    try {
      const { jd_id } = await uploadJD(
        editCompany.projectName || target.companyDetails.projectName || "updated-project",
        editJdText,
        editTitle.trim() || target.title
      );

      setRegenStatus("Analyzing updated context...");
      await analyzeJD(jd_id);

      // Poll until ready
      const interval = setInterval(async () => {
        try {
          const { status: s, error_message } = await getAnalysisStatus(jd_id);
          setRegenStatus(`Status: ${statusConfig[s]?.label || s}`);

          if (TERMINAL_STATUSES.includes(s)) {
            clearInterval(interval);
            if (s === "FAILED") {
              alert(`Regeneration failed: ${error_message || "Unknown error"}`);
              setIsRegenerating(false);
              return;
            }

            const [mdRes, jsonRes] = await Promise.all([getMarkdown(jd_id), getJson(jd_id)]);

            // Re-point existing agent in-place
            setAgents((prev) =>
              prev.map((a) => {
                if (a.id === selectedSettingAgentId) {
                  return {
                    ...a,
                    title: editTitle.trim() || a.title,
                    companyDetails: { ...editCompany },
                    jdId: jd_id,
                    jdText: editJdText,
                    markdown: mdRes.markdown,
                    jsonData: jsonRes.json,
                    specificationVersion: mdRes.specification_version || a.specificationVersion + 1,
                    updatedAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                  };
                }
                return a;
              })
            );

            // Also update current workflow view state if it matches
            if (target.jdId === jdId) {
              setMarkdown(mdRes.markdown);
              setJsonData(jsonRes.json);
              setJdId(jd_id);
              setJdText(editJdText);
            }

            setRegenSuccessMsg(`Successfully regenerated context! Agent re-pointed to Specification v${mdRes.specification_version}`);
            setIsRegenerating(false);
            setRegenStatus(null);
          }
        } catch (err) {
          clearInterval(interval);
          alert(`Error polling regeneration: ${(err as Error).message}`);
          setIsRegenerating(false);
          setRegenStatus(null);
        }
      }, POLL_INTERVAL_MS);
    } catch (e) {
      alert(`Regeneration failed: ${(e as Error).message}`);
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
                <div style={{ display: "flex", justifyContent: "space-between", alignContent: "center", marginBottom: "16px" }}>
                  <h3 style={{ margin: 0, fontSize: "1.1rem" }}>Step 2 & 3: Enter Job Description & Run Analysis</h3>
                  {status && (
                    <span className={`status-pill ${statusConfig[status]?.className}`}>
                      {statusConfig[status]?.icon} {statusConfig[status]?.label}
                    </span>
                  )}
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
                      📁 Upload .txt File
                      <input type="file" accept=".txt,.md" onChange={handleFileUpload} style={{ display: "none" }} />
                    </label>
                  </div>
                  <textarea
                    className="textarea"
                    value={jdText}
                    onChange={(e) => setJdText(e.target.value)}
                    placeholder="Paste the complete Job Description text here..."
                  />
                </div>

                {error && <div className="alert-error">❌ {error}</div>}

                <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
                  <button
                    onClick={handleAnalyseJD}
                    disabled={!jdText.trim() || (status !== null && !TERMINAL_STATUSES.includes(status))}
                    className="btn-primary"
                  >
                    {status !== null && !TERMINAL_STATUSES.includes(status) ? (
                      <>
                        <span className="spinner"></span> Analyzing JD...
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
                    <div style={{ display: "flex", gap: "10px" }}>
                      <div className="sub-tabs">
                        <button
                          className={`sub-tab-btn ${contextTab === "markdown" ? "active" : ""}`}
                          onClick={() => setContextTab("markdown")}
                        >
                          Markdown View
                        </button>
                        <button
                          className={`sub-tab-btn ${contextTab === "json" ? "active" : ""}`}
                          onClick={() => setContextTab("json")}
                        >
                          JSON Source of Truth
                        </button>
                      </div>
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

                  <div className="code-preview">
                    {contextTab === "markdown" ? (
                      <ReactMarkdown>{markdown}</ReactMarkdown>
                    ) : (
                      <pre style={{ margin: 0, fontFamily: "monospace", color: "#344054" }}>
                        {JSON.stringify(jsonData, null, 2)}
                      </pre>
                    )}
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
                      ✨ Create Agent & Enable Chat
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
                  <button className="btn-ghost-dark" onClick={() => setChatMessages([])}>
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
                {chatMessages.map((msg) => (
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