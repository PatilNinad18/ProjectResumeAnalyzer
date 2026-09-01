"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  analyzeJD,
  getAnalysisStatus,
  getJson,
  getMarkdown,
  uploadJD,
  ProcessingStatus,
} from "@/lib/api";

const POLL_INTERVAL_MS = 1500;
const TERMINAL_STATUSES: ProcessingStatus[] = [
  "READY",
  "NEEDS_REVIEW",
  "FAILED",
];

const statusConfig: Record<
  ProcessingStatus,
  { label: string; icon: string; className: string }
> = {
  UPLOADED: {
    label: "Uploaded",
    icon: "↑",
    className: "status-uploaded",
  },
  PARSING: {
    label: "Parsing JD",
    icon: "◌",
    className: "status-processing",
  },
  UNDERSTANDING: {
    label: "Understanding JD",
    icon: "◌",
    className: "status-processing",
  },
  VALIDATING: {
    label: "Validating",
    icon: "◌",
    className: "status-processing",
  },
  GENERATING: {
    label: "Generating",
    icon: "◌",
    className: "status-processing",
  },
  READY: {
    label: "Analysis Ready",
    icon: "✓",
    className: "status-ready",
  },
  NEEDS_REVIEW: {
    label: "Needs Review",
    icon: "!",
    className: "status-review",
  },
  FAILED: {
    label: "Failed",
    icon: "×",
    className: "status-failed",
  },
};

export default function Home() {
  const [jdText, setJdText] = useState("");
  const [jdId, setJdId] = useState<string | null>(null);
  const [status, setStatus] = useState<ProcessingStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [jsonData, setJsonData] = useState<Record<string, unknown> | null>(
    null
  );
  const [tab, setTab] = useState<"markdown" | "json">("markdown");

  async function handleSubmit() {
    if (!jdText.trim()) return;

    setError(null);
    setMarkdown(null);
    setJsonData(null);

    try {
      const { jd_id } = await uploadJD(
        "demo-project",
        jdText,
        "Untitled JD"
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
        const { status: s, error_message } =
          await getAnalysisStatus(id);

        setStatus(s);

        if (TERMINAL_STATUSES.includes(s)) {
          clearInterval(interval);

          if (s === "FAILED") {
            setError(error_message || "Processing failed.");
            return;
          }

          const [mdRes, jsonRes] = await Promise.all([
            getMarkdown(id),
            getJson(id),
          ]);

          setMarkdown(mdRes.markdown);
          setJsonData(jsonRes.json);
        }
      } catch (e) {
        clearInterval(interval);
        setError((e as Error).message);
      }
    }, POLL_INTERVAL_MS);
  }

  function download(
    filename: string,
    content: string,
    mime: string
  ) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();

    URL.revokeObjectURL(url);
  }

  const isProcessing =
    status !== null && !TERMINAL_STATUSES.includes(status);

  const currentStatus = status
    ? statusConfig[status]
    : null;

  return (
    <>
      <style jsx global>{`
        * {
          box-sizing: border-box;
        }

        body {
          margin: 0;
          background: #f6f7f9;
          color: #111827;
          font-family:
            Inter,
            ui-sans-serif,
            system-ui,
            -apple-system,
            BlinkMacSystemFont,
            "Segoe UI",
            sans-serif;
        }

        button {
          font-family: inherit;
        }

        .app-shell {
          min-height: 100vh;
          background:
            radial-gradient(
              circle at 80% 0%,
              rgba(99, 102, 241, 0.08),
              transparent 30%
            ),
            #f6f7f9;
        }

        .topbar {
          height: 68px;
          background: rgba(255, 255, 255, 0.92);
          backdrop-filter: blur(12px);
          border-bottom: 1px solid #e5e7eb;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 36px;
          position: sticky;
          top: 0;
          z-index: 10;
        }

        .brand {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .brand-icon {
          width: 34px;
          height: 34px;
          border-radius: 10px;
          background: #111827;
          color: white;
          display: grid;
          place-items: center;
          font-weight: 800;
          font-size: 15px;
        }

        .brand-title {
          font-weight: 750;
          font-size: 15px;
          letter-spacing: -0.2px;
        }

        .brand-subtitle {
          color: #9ca3af;
          font-size: 12px;
          margin-top: 2px;
        }

        .topbar-badge {
          border: 1px solid #e5e7eb;
          background: #fafafa;
          border-radius: 999px;
          padding: 7px 12px;
          color: #6b7280;
          font-size: 12px;
          font-weight: 600;
        }

        .page {
          max-width: 1380px;
          margin: 0 auto;
          padding: 42px 32px 60px;
        }

        .hero {
          margin-bottom: 30px;
        }

        .eyebrow {
          color: #6366f1;
          font-size: 12px;
          font-weight: 750;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          margin-bottom: 9px;
        }

        .hero h1 {
          margin: 0;
          font-size: 34px;
          line-height: 1.1;
          letter-spacing: -1.2px;
          font-weight: 800;
        }

        .hero p {
          margin: 10px 0 0;
          max-width: 720px;
          color: #6b7280;
          font-size: 15px;
          line-height: 1.65;
        }

        .workspace {
          display: grid;
          grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
          gap: 22px;
          align-items: start;
        }

        .card {
          background: white;
          border: 1px solid #e5e7eb;
          border-radius: 16px;
          box-shadow:
            0 1px 2px rgba(0, 0, 0, 0.03),
            0 8px 30px rgba(15, 23, 42, 0.035);
        }

        .card-header {
          padding: 20px 22px;
          border-bottom: 1px solid #edf0f3;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .card-title {
          font-size: 14px;
          font-weight: 750;
        }

        .card-description {
          font-size: 12px;
          color: #9ca3af;
          margin-top: 4px;
        }

        .input-card {
          overflow: hidden;
        }

        .input-body {
          padding: 20px;
        }

        .input-label {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 12px;
          font-weight: 700;
          color: #374151;
          margin-bottom: 9px;
        }

        .character-count {
          color: #9ca3af;
          font-weight: 500;
        }

        .jd-input {
          width: 100%;
          min-height: 430px;
          resize: vertical;
          border: 1px solid #dfe3e8;
          border-radius: 12px;
          background: #fbfcfd;
          padding: 16px;
          outline: none;
          color: #1f2937;
          font-size: 13px;
          line-height: 1.65;
          font-family:
            "SFMono-Regular",
            Consolas,
            "Liberation Mono",
            monospace;
          transition: 0.2s ease;
        }

        .jd-input:focus {
          border-color: #818cf8;
          background: white;
          box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }

        .jd-input::placeholder {
          color: #adb5bd;
        }

        .input-footer {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 14px;
        }

        .hint {
          color: #9ca3af;
          font-size: 11px;
        }

        .analyze-button {
          border: 0;
          border-radius: 10px;
          padding: 10px 18px;
          background: #111827;
          color: white;
          font-size: 13px;
          font-weight: 700;
          cursor: pointer;
          transition: all 0.18s ease;
        }

        .analyze-button:hover:not(:disabled) {
          background: #1f2937;
          transform: translateY(-1px);
          box-shadow: 0 5px 15px rgba(17, 24, 39, 0.15);
        }

        .analyze-button:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }

        .status-card {
          min-height: 530px;
        }

        .status-content {
          padding: 22px;
        }

        .status-overview {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px;
          border: 1px solid #edf0f3;
          border-radius: 12px;
          background: #fafbfc;
          margin-bottom: 20px;
        }

        .status-left {
          display: flex;
          align-items: center;
          gap: 12px;
        }

        .status-dot {
          width: 36px;
          height: 36px;
          border-radius: 10px;
          display: grid;
          place-items: center;
          font-weight: 800;
        }

        .status-uploaded {
          color: #2563eb;
          background: #eff6ff;
        }

        .status-processing {
          color: #6366f1;
          background: #eef2ff;
        }

        .status-ready {
          color: #059669;
          background: #ecfdf5;
        }

        .status-review {
          color: #d97706;
          background: #fffbeb;
        }

        .status-failed {
          color: #dc2626;
          background: #fef2f2;
        }

        .status-name {
          font-size: 13px;
          font-weight: 750;
        }

        .status-detail {
          font-size: 11px;
          color: #9ca3af;
          margin-top: 3px;
        }

        .processing-animation {
          animation: pulse 1.4s infinite;
        }

        @keyframes pulse {
          0%,
          100% {
            opacity: 1;
          }
          50% {
            opacity: 0.4;
          }
        }

        .id-label {
          font-size: 10px;
          color: #9ca3af;
          text-transform: uppercase;
          letter-spacing: 0.06em;
        }

        .id-value {
          margin-top: 5px;
          font-family: monospace;
          font-size: 10px;
          color: #6b7280;
          word-break: break-all;
        }

        .empty-state {
          min-height: 330px;
          display: flex;
          align-items: center;
          justify-content: center;
          text-align: center;
          border: 1px dashed #dfe3e8;
          border-radius: 14px;
          background: #fbfcfd;
        }

        .empty-icon {
          width: 48px;
          height: 48px;
          border-radius: 14px;
          background: #f1f3f5;
          display: grid;
          place-items: center;
          margin: 0 auto 14px;
          font-size: 20px;
        }

        .empty-title {
          font-weight: 750;
          font-size: 14px;
        }

        .empty-text {
          max-width: 300px;
          margin: 7px auto 0;
          font-size: 12px;
          line-height: 1.6;
          color: #9ca3af;
        }

        .error {
          margin-top: 15px;
          padding: 12px 14px;
          background: #fef2f2;
          border: 1px solid #fecaca;
          border-radius: 10px;
          color: #b91c1c;
          font-size: 12px;
        }

        .review-message {
          margin-bottom: 16px;
          padding: 12px 14px;
          background: #fffbeb;
          border: 1px solid #fde68a;
          border-radius: 10px;
          color: #92400e;
          font-size: 12px;
          line-height: 1.5;
        }

        .result-section {
          margin-top: 22px;
        }

        .result-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 12px;
        }

        .result-title {
          font-size: 14px;
          font-weight: 750;
        }

        .result-actions {
          display: flex;
          gap: 7px;
        }

        .secondary-button {
          border: 1px solid #e1e5ea;
          background: white;
          color: #374151;
          border-radius: 8px;
          padding: 7px 11px;
          font-size: 11px;
          font-weight: 650;
          cursor: pointer;
        }

        .secondary-button:hover {
          background: #f9fafb;
          border-color: #cfd4dc;
        }

        .tabs {
          display: flex;
          align-items: center;
          gap: 4px;
          background: #f1f3f5;
          padding: 4px;
          border-radius: 10px;
          width: fit-content;
          margin-bottom: 12px;
        }

        .tab {
          border: 0;
          background: transparent;
          padding: 8px 15px;
          border-radius: 7px;
          color: #6b7280;
          font-size: 12px;
          font-weight: 650;
          cursor: pointer;
        }

        .tab.active {
          background: white;
          color: #111827;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        }

        .viewer {
          background: white;
          border: 1px solid #e1e5ea;
          border-radius: 14px;
          overflow: hidden;
        }

        .viewer-toolbar {
          height: 38px;
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 0 12px;
          border-bottom: 1px solid #edf0f3;
          background: #fafbfc;
        }

        .traffic-dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: #d1d5db;
        }

        .viewer-label {
          margin-left: 7px;
          color: #9ca3af;
          font-family: monospace;
          font-size: 10px;
        }

        .viewer-body {
          max-height: 620px;
          overflow: auto;
          padding: 24px;
        }

        .markdown-content {
          font-size: 13px;
          line-height: 1.7;
          color: #374151;
        }

        .markdown-content h1 {
          font-size: 25px;
          color: #111827;
          margin-top: 0;
        }

        .markdown-content h2 {
          font-size: 19px;
          color: #111827;
          margin-top: 28px;
          padding-bottom: 7px;
          border-bottom: 1px solid #edf0f3;
        }

        .markdown-content h3 {
          font-size: 15px;
          color: #111827;
          margin-top: 20px;
        }

        .markdown-content strong {
          color: #111827;
        }

        .markdown-content code {
          background: #f3f4f6;
          padding: 2px 5px;
          border-radius: 4px;
          font-size: 11px;
        }

        .markdown-content li {
          margin-bottom: 5px;
        }

        .json-viewer {
          margin: 0;
          font-family:
            "SFMono-Regular",
            Consolas,
            monospace;
          font-size: 11px;
          line-height: 1.65;
          color: #374151;
          white-space: pre-wrap;
          word-break: break-word;
        }

        @media (max-width: 1000px) {
          .workspace {
            grid-template-columns: 1fr;
          }

          .status-card {
            min-height: auto;
          }
        }

        @media (max-width: 640px) {
          .topbar {
            padding: 0 18px;
          }

          .topbar-badge {
            display: none;
          }

          .page {
            padding: 28px 16px 40px;
          }

          .hero h1 {
            font-size: 28px;
          }

          .input-footer {
            align-items: flex-start;
            flex-direction: column;
            gap: 12px;
          }

          .analyze-button {
            width: 100%;
          }

          .result-header {
            align-items: flex-start;
            flex-direction: column;
            gap: 10px;
          }

          .viewer-body {
            padding: 16px;
          }
        }
      `}</style>

      <div className="app-shell">
        {/* HEADER */}
        <header className="topbar">
          <div className="brand">
            <div className="brand-icon">AI</div>

            <div>
              <div className="brand-title">
                JD Understanding Agent
              </div>
              <div className="brand-subtitle">
                Intelligent job description analysis
              </div>
            </div>
          </div>

          <div className="topbar-badge">
            AI Evaluation Context
          </div>
        </header>

        <main className="page">
          {/* HERO */}
          <section className="hero">
            <div className="eyebrow">
              Job Intelligence
            </div>

            <h1>
              Turn a JD into
              <br />
              actionable AI context.
            </h1>

            <p>
              Analyze a job description end-to-end and generate a
              structured evaluation specification for downstream
              candidate analysis.
            </p>
          </section>

          {/* MAIN WORKSPACE */}
          <div className="workspace">
            {/* LEFT: INPUT */}
            <section className="card input-card">
              <div className="card-header">
                <div>
                  <div className="card-title">
                    Job Description
                  </div>

                  <div className="card-description">
                    Provide the raw JD for analysis
                  </div>
                </div>

                <span
                  style={{
                    fontSize: 18,
                    color: "#9ca3af",
                  }}
                >
                  ✦
                </span>
              </div>

              <div className="input-body">
                <div className="input-label">
                  <span>Raw JD content</span>

                  <span className="character-count">
                    {jdText.length.toLocaleString()} chars
                  </span>
                </div>

                <textarea
                  className="jd-input"
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                  placeholder={`Paste the complete Job Description here...

The agent will identify:
• Conventional requirements
• Must-have vs preferred criteria
• Responsibilities
• Experience & technical requirements
• Location and work constraints
• Non-conventional candidate parameters
• Evidence and evaluation rules
• Ambiguities and compliance concerns`}
                />

                <div className="input-footer">
                  <span className="hint">
                    The complete JD produces better context.
                  </span>

                  <button
                    className="analyze-button"
                    onClick={handleSubmit}
                    disabled={
                      !jdText.trim() || isProcessing
                    }
                  >
                    {isProcessing
                      ? "Analyzing..."
                      : "Analyze JD  →"}
                  </button>
                </div>
              </div>
            </section>

            {/* RIGHT: STATUS */}
            <section className="card status-card">
              <div className="card-header">
                <div>
                  <div className="card-title">
                    Analysis Workspace
                  </div>

                  <div className="card-description">
                    Canonical JD understanding
                  </div>
                </div>

                {currentStatus && (
                  <div
                    className={`status-dot ${currentStatus.className}`}
                  >
                    {currentStatus.icon}
                  </div>
                )}
              </div>

              <div className="status-content">
                {status && currentStatus && (
                  <div className="status-overview">
                    <div className="status-left">
                      <div
                        className={`status-dot ${currentStatus.className} ${
                          isProcessing
                            ? "processing-animation"
                            : ""
                        }`}
                      >
                        {currentStatus.icon}
                      </div>

                      <div>
                        <div className="status-name">
                          {currentStatus.label}
                        </div>

                        <div className="status-detail">
                          {isProcessing
                            ? "The agent is processing the job description..."
                            : status === "READY"
                              ? "Specification generated successfully."
                              : status === "NEEDS_REVIEW"
                                ? "Human review is recommended."
                                : "Processing could not be completed."}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {jdId && (
                  <div style={{ marginBottom: 20 }}>
                    <div className="id-label">
                      Job Description ID
                    </div>

                    <div className="id-value">
                      {jdId}
                    </div>
                  </div>
                )}

                {error && (
                  <div className="error">
                    <strong>Processing error:</strong>{" "}
                    {error}
                  </div>
                )}

                {status === "NEEDS_REVIEW" && (
                  <div className="review-message">
                    <strong>TA review recommended.</strong>{" "}
                    The generated specification contains
                    ambiguities or compliance-related items that
                    should be reviewed before candidate evaluation.
                  </div>
                )}

                {!markdown && !jsonData && !error && (
                  <div className="empty-state">
                    <div>
                      <div className="empty-icon">
                        ✦
                      </div>

                      <div className="empty-title">
                        No specification yet
                      </div>

                      <div className="empty-text">
                        Paste a job description on the left and
                        run the analysis to generate Markdown
                        and JSON evaluation context.
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </section>
          </div>

          {/* RESULTS */}
          {(markdown || jsonData) && (
            <section className="result-section">
              <div className="result-header">
                <div>
                  <div className="result-title">
                    Generated Specification
                  </div>

                  <div
                    style={{
                      fontSize: 11,
                      color: "#9ca3af",
                      marginTop: 4,
                    }}
                  >
                    Canonical candidate evaluation context
                  </div>
                </div>

                <div className="result-actions">
                  {markdown && (
                    <button
                      className="secondary-button"
                      onClick={() =>
                        download(
                          "job_specification.md",
                          markdown,
                          "text/markdown"
                        )
                      }
                    >
                      ↓ Markdown
                    </button>
                  )}

                  {jsonData && (
                    <button
                      className="secondary-button"
                      onClick={() =>
                        download(
                          "job_specification.json",
                          JSON.stringify(
                            jsonData,
                            null,
                            2
                          ),
                          "application/json"
                        )
                      }
                    >
                      ↓ JSON
                    </button>
                  )}
                </div>
              </div>

              <div className="tabs">
                <button
                  className={`tab ${
                    tab === "markdown"
                      ? "active"
                      : ""
                  }`}
                  onClick={() => setTab("markdown")}
                >
                  Markdown
                </button>

                <button
                  className={`tab ${
                    tab === "json" ? "active" : ""
                  }`}
                  onClick={() => setTab("json")}
                >
                  JSON
                </button>
              </div>

              <div className="viewer">
                <div className="viewer-toolbar">
                  <span className="traffic-dot" />
                  <span className="traffic-dot" />
                  <span className="traffic-dot" />

                  <span className="viewer-label">
                    {tab === "markdown"
                      ? "job_specification.md"
                      : "job_specification.json"}
                  </span>
                </div>

                <div className="viewer-body">
                  {tab === "markdown" && markdown && (
                    <div className="markdown-content">
                      <ReactMarkdown>
                        {markdown}
                      </ReactMarkdown>
                    </div>
                  )}

                  {tab === "json" && jsonData && (
                    <pre className="json-viewer">
                      {JSON.stringify(
                        jsonData,
                        null,
                        2
                      )}
                    </pre>
                  )}
                </div>
              </div>
            </section>
          )}
        </main>
      </div>
    </>
  );
}