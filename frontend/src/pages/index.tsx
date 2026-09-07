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
      text: "Hello! I am your JD AI Assistant. Ask me anything about role requirements, responsibilities, technical skills, or evaluation criteria.",
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

  return (
    <>
      <style jsx global>{`
        * { box-sizing: border-box; }
        body {
          margin: 0;
          background: #0f172a;
          color: #f8fafc;
          font-family: Inter, system-ui, -apple-system, sans-serif;
        }
        button, input, textarea, select { font-family: inherit; }

        .app-container {
          min-height: 100vh;
          background: radial-gradient(circle at 80% 0%, rgba(99, 102, 241, 0.12), transparent 40%), #0f172a;
          display: flex;
          flex-direction: column;
        }

        /* Top Header */
        .topbar {
          height: 70px;
          background: rgba(15, 23, 42, 0.85);
          backdrop-filter: blur(12px);
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 32px;
          position: sticky;
          top: 0;
          z-index: 50;
        }
        .brand {
          display: flex;
          align-items: center;
          gap: 12px;
          font-weight: 700;
          font-size: 1.15rem;
          color: #ffffff;
        }
        .brand-badge {
          background: linear-gradient(135deg, #6366f1, #8b5cf6);
          padding: 4px 10px;
          border-radius: 6px;
          font-size: 0.75rem;
          letter-spacing: 0.5px;
        }
        .nav-tabs {
          display: flex;
          gap: 8px;
          background: rgba(255, 255, 255, 0.05);
          padding: 4px;
          border-radius: 10px;
          border: 1px solid rgba(255, 255, 255, 0.08);
        }
        .nav-btn {
          background: transparent;
          border: none;
          color: #94a3b8;
          padding: 8px 18px;
          border-radius: 8px;
          font-size: 0.88rem;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .nav-btn:hover { color: #ffffff; background: rgba(255, 255, 255, 0.05); }
        .nav-btn.active {
          background: #6366f1;
          color: #ffffff;
          box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
        }

        /* Main Content Container */
        .main-content {
          flex: 1;
          max-width: 1280px;
          width: 100%;
          margin: 0 auto;
          padding: 32px;
        }

        /* Card Styles */
        .card {
          background: rgba(30, 41, 59, 0.7);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          padding: 28px;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
          backdrop-filter: blur(8px);
          margin-bottom: 24px;
        }

        /* Workflow Stepper */
        .stepper {
          display: flex;
          align-items: center;
          justify-content: space-between;
          position: relative;
          margin-bottom: 36px;
          padding: 0 12px;
        }
        .stepper::before {
          content: "";
          position: absolute;
          top: 20px;
          left: 40px;
          right: 40px;
          height: 2px;
          background: rgba(255, 255, 255, 0.1);
          z-index: 1;
        }
        .step-item {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 8px;
          position: relative;
          z-index: 2;
          cursor: pointer;
        }
        .step-circle {
          width: 42px;
          height: 42px;
          border-radius: 50%;
          background: #1e293b;
          border: 2px solid #334155;
          color: #94a3b8;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 600;
          font-size: 0.95rem;
          transition: all 0.3s ease;
        }
        .step-item.active .step-circle {
          border-color: #6366f1;
          background: #6366f1;
          color: #ffffff;
          box-shadow: 0 0 16px rgba(99, 102, 241, 0.5);
        }
        .step-item.completed .step-circle {
          border-color: #10b981;
          background: #10b981;
          color: #ffffff;
        }
        .step-label {
          font-size: 0.8rem;
          font-weight: 500;
          color: #94a3b8;
        }
        .step-item.active .step-label { color: #ffffff; font-weight: 600; }
        .step-item.completed .step-label { color: #10b981; }

        /* Form Inputs */
        .form-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 20px;
        }
        .form-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .form-group label {
          font-size: 0.85rem;
          font-weight: 600;
          color: #cbd5e1;
        }
        .input-text, .textarea, .select {
          background: #0f172a;
          border: 1px solid rgba(255, 255, 255, 0.12);
          border-radius: 10px;
          padding: 12px 16px;
          color: #f8fafc;
          font-size: 0.92rem;
          transition: border-color 0.2s;
        }
        .input-text:focus, .textarea:focus, .select:focus {
          outline: none;
          border-color: #6366f1;
          box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
        }
        .textarea {
          min-height: 220px;
          resize: vertical;
          line-height: 1.5;
        }

        /* Buttons */
        .btn-primary {
          background: linear-gradient(135deg, #6366f1, #4f46e5);
          color: #ffffff;
          border: none;
          padding: 12px 24px;
          border-radius: 10px;
          font-weight: 600;
          font-size: 0.92rem;
          cursor: pointer;
          transition: all 0.2s;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }
        .btn-primary:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
        }
        .btn-primary:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .btn-secondary {
          background: rgba(255, 255, 255, 0.08);
          color: #cbd5e1;
          border: 1px solid rgba(255, 255, 255, 0.1);
          padding: 10px 18px;
          border-radius: 8px;
          font-weight: 500;
          font-size: 0.88rem;
          cursor: pointer;
          transition: all 0.2s;
        }
        .btn-secondary:hover { background: rgba(255, 255, 255, 0.14); color: #fff; }

        /* Status & Alert Badges */
        .alert-success {
          background: rgba(16, 185, 129, 0.12);
          border: 1px solid rgba(16, 185, 129, 0.3);
          color: #34d399;
          padding: 14px 20px;
          border-radius: 10px;
          font-size: 0.9rem;
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 20px;
        }
        .alert-error {
          background: rgba(239, 68, 68, 0.12);
          border: 1px solid rgba(239, 68, 68, 0.3);
          color: #f87171;
          padding: 14px 20px;
          border-radius: 10px;
          font-size: 0.9rem;
          margin-bottom: 20px;
        }

        /* Status Pills */
        .status-pill {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 6px 14px;
          border-radius: 20px;
          font-size: 0.8rem;
          font-weight: 600;
        }
        .status-uploaded { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
        .status-processing { background: rgba(168, 85, 247, 0.15); color: #c084fc; }
        .status-ready { background: rgba(16, 185, 129, 0.15); color: #34d399; }
        .status-failed { background: rgba(239, 68, 68, 0.15); color: #f87171; }

        /* Preview Tabs */
        .preview-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          padding-bottom: 16px;
          margin-bottom: 20px;
        }
        .sub-tabs {
          display: flex;
          gap: 8px;
        }
        .sub-tab-btn {
          background: transparent;
          border: none;
          color: #94a3b8;
          padding: 6px 14px;
          border-radius: 6px;
          font-size: 0.85rem;
          cursor: pointer;
        }
        .sub-tab-btn.active {
          background: rgba(255, 255, 255, 0.1);
          color: #ffffff;
          font-weight: 600;
        }

        .code-preview {
          background: #090d16;
          border: 1px solid rgba(255, 255, 255, 0.06);
          border-radius: 12px;
          padding: 24px;
          max-height: 520px;
          overflow-y: auto;
          font-size: 0.9rem;
          line-height: 1.6;
        }

        /* Dedicated Chat Styles */
        .chat-container {
          display: flex;
          flex-direction: column;
          height: calc(100vh - 160px);
          background: rgba(30, 41, 59, 0.7);
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 16px;
          overflow: hidden;
        }
        .chat-topbar {
          padding: 16px 24px;
          background: rgba(15, 23, 42, 0.6);
          border-bottom: 1px solid rgba(255, 255, 255, 0.08);
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .chat-messages {
          flex: 1;
          padding: 24px;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .message-bubble {
          max-width: 80%;
          padding: 16px 20px;
          border-radius: 14px;
          font-size: 0.92rem;
          line-height: 1.5;
        }
        .message-user {
          align-self: flex-end;
          background: linear-gradient(135deg, #6366f1, #4f46e5);
          color: #ffffff;
          border-bottom-right-radius: 4px;
        }
        .message-assistant {
          align-self: flex-start;
          background: #1e293b;
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: #e2e8f0;
          border-bottom-left-radius: 4px;
        }
        .chat-input-bar {
          padding: 16px 24px;
          background: rgba(15, 23, 42, 0.6);
          border-top: 1px solid rgba(255, 255, 255, 0.08);
          display: flex;
          gap: 12px;
        }
        .prompt-chips {
          display: flex;
          gap: 8px;
          padding: 12px 24px;
          background: rgba(15, 23, 42, 0.3);
          border-top: 1px solid rgba(255, 255, 255, 0.04);
          overflow-x: auto;
        }
        .chip {
          background: rgba(255, 255, 255, 0.06);
          border: 1px solid rgba(255, 255, 255, 0.08);
          color: #94a3b8;
          padding: 6px 12px;
          border-radius: 20px;
          font-size: 0.78rem;
          cursor: pointer;
          white-space: nowrap;
        }
        .chip:hover { background: rgba(99, 102, 241, 0.2); color: #6366f1; }

        /* Agent Cards */
        .agent-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
          gap: 20px;
        }
        .agent-card {
          background: #1e293b;
          border: 1px solid rgba(255, 255, 255, 0.08);
          border-radius: 14px;
          padding: 20px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          transition: all 0.2s;
        }
        .agent-card:hover { border-color: #6366f1; transform: translateY(-2px); }
        .agent-card.selected { border-color: #6366f1; box-shadow: 0 0 16px rgba(99, 102, 241, 0.3); }

        .spinner {
          width: 16px;
          height: 16px;
          border: 2px solid rgba(255, 255, 255, 0.3);
          border-top-color: #ffffff;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>

      <div className="app-container">
        {/* Top Navbar */}
        <header className="topbar">
          <div className="brand">
            <span style={{ fontSize: "1.3rem" }}>⚡</span>
            <span>JD Understanding Agent</span>
            <span className="brand-badge">PRO v2.0</span>
          </div>

          <nav className="nav-tabs">
            <button
              className={`nav-btn ${activeTab === "workflow" ? "active" : ""}`}
              onClick={() => setActiveTab("workflow")}
            >
              <span>📋</span> Linear Setup
            </button>
            <button
              className={`nav-btn ${activeTab === "chat" ? "active" : ""}`}
              onClick={() => setActiveTab("chat")}
            >
              <span>💬</span> Dedicated Chat
            </button>
            <button
              className={`nav-btn ${activeTab === "settings" ? "active" : ""}`}
              onClick={() => setActiveTab("settings")}
            >
              <span>⚙️</span> Agent Settings
            </button>
          </nav>
        </header>

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
                      <span style={{ fontSize: "0.82rem", color: "#94a3b8" }}>
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
                      <pre style={{ margin: 0, fontFamily: "monospace", color: "#a5f3fc" }}>
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
                  <p style={{ margin: "0 0 16px 0", fontSize: "0.88rem", color: "#94a3b8" }}>
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
          {/* TAB 2: DEDICATED JD CHAT PAGE (No floating popup widget)                 */}
          {/* ========================================================================= */}
          {activeTab === "chat" && (
            <div className="chat-container">
              {/* Chat Header */}
              <div className="chat-topbar">
                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <span style={{ fontSize: "1.4rem" }}>🤖</span>
                  <div>
                    <h4 style={{ margin: 0, fontSize: "1rem" }}>
                      {activeAgentForChat ? activeAgentForChat.agentName : "JD AI Assistant"}
                    </h4>
                    <span style={{ fontSize: "0.78rem", color: "#94a3b8" }}>
                      {activeAgentForChat
                        ? `${activeAgentForChat.companyDetails.companyName} • Spec v${activeAgentForChat.specificationVersion}`
                        : "Conversational context interface"}
                    </span>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <label style={{ fontSize: "0.82rem", color: "#94a3b8" }}>Select Agent / Context:</label>
                  <select
                    className="select"
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
                  <button className="btn-secondary" onClick={() => setChatMessages([])} style={{ padding: "6px 12px" }}>
                    Clear History
                  </button>
                </div>
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

              {/* Actionable Prompt Suggestions */}
              <div className="prompt-chips">
                <button className="chip" onClick={() => handleSendChatMessage("What are the must-have requirements for this role?")}>
                  💡 Must-have requirements?
                </button>
                <button className="chip" onClick={() => handleSendChatMessage("What technical skills and tools are required?")}>
                  🛠 Technical stack?
                </button>
                <button className="chip" onClick={() => handleSendChatMessage("What responsibilities are outlined?")}>
                  📋 Role duties?
                </button>
                <button className="chip" onClick={() => handleSendChatMessage("Are there any missing information fields or ambiguities?")}>
                  ❓ Missing information?
                </button>
              </div>

              {/* Input Bar */}
              <div className="chat-input-bar">
                <input
                  type="text"
                  className="input-text"
                  style={{ flex: 1 }}
                  placeholder="Ask any question about the JD requirements..."
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSendChatMessage()}
                />
                <button className="btn-primary" onClick={() => handleSendChatMessage()} disabled={isChatLoading || !chatInput.trim()}>
                  Send ➔
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
                  <p style={{ color: "#94a3b8", fontSize: "1rem", margin: "0 0 16px 0" }}>
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
                    <h4 style={{ margin: "0 0 12px 0", color: "#cbd5e1" }}>Created Agents ({agents.length})</h4>
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
                            <p style={{ margin: 0, fontSize: "0.82rem", color: "#94a3b8" }}>{a.title}</p>
                            <p style={{ margin: "4px 0 0 0", fontSize: "0.78rem", color: "#64748b" }}>
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
                      <p style={{ margin: "0 0 20px 0", fontSize: "0.85rem", color: "#94a3b8" }}>
                        Update company details or JD text below. Clicking <strong>Generate Updated Context</strong> will re-analyze the JD, update the specification version, and re-point this existing agent without creating duplicates.
                      </p>

                      {regenSuccessMsg && <div className="alert-success">✓ {regenSuccessMsg}</div>}
                      {regenStatus && <div className="alert-success" style={{ color: "#c084fc", borderColor: "rgba(168,85,247,0.3)" }}>◌ {regenStatus}</div>}

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