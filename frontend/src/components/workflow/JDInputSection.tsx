import { useState } from "react";
import { TERMINAL_STATUSES } from "@/lib/api";
import { statusConfig, formatElapsed } from "@/lib/ui";
import type { WorkflowPageProps } from "./WorkflowPage";
import styles from "./JDInputSection.module.css";
import BatchUploadSection from "./BatchUploadSection";
import type { useJDBatch } from "@/hooks/useJDBatch";

type JDInputSectionProps = Pick<
  WorkflowPageProps,
  | "agents"
  | "handleResetForNewJD"
  | "status"
  | "jobTitle"
  | "setJobTitle"
  | "handleFileUpload"
  | "jdText"
  | "setJdText"
  | "setSelectedFile"
  | "selectedFile"
  | "analysisProgress"
  | "nowTs"
  | "analysisStartedAt"
  | "handleCancelAnalysis"
  | "analysisSuccessMsg"
  | "setAnalysisSuccessMsg"
  | "error"
  | "handleAnalyseJD"
  | "setError"
>;

type JDInputSectionPropsWithBatch = JDInputSectionProps & {
  batchState: ReturnType<typeof useJDBatch>;
  handleLaunchBatchAgent: WorkflowPageProps["handleLaunchBatchAgent"];
};

export default function JDInputSection({
  batchState,
  handleLaunchBatchAgent,
  agents,
  handleResetForNewJD,
  status,
  jobTitle,
  setJobTitle,
  handleFileUpload,
  jdText,
  setJdText,
  setSelectedFile,
  selectedFile,
  analysisProgress,
  nowTs,
  analysisStartedAt,
  handleCancelAnalysis,
  analysisSuccessMsg,
  setAnalysisSuccessMsg,
  error,
  handleAnalyseJD,
  setError,
}: JDInputSectionPropsWithBatch) {
  // ── Mode toggle: "single" = one JD textarea/file, "multi" = batch parallel upload ──
  const [mode, setMode] = useState<"single" | "multi">("single");

  const analysisRunning = status !== null && !TERMINAL_STATUSES.includes(status);
  const batchFiles = batchState.files;
  const batchUploadSelected = batchFiles.length > 0;

  // Switch to multi mode and append files
  function handleAddMultipleFiles(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.currentTarget.files ?? []);
    event.currentTarget.value = "";
    if (!files.length) return;

    batchState.setFiles((current) => {
      const currentKeys = new Set(current.map((file) => `${file.name}:${file.size}:${file.lastModified}`));
      const additions = files.filter(
        (file) => !currentKeys.has(`${file.name}:${file.size}:${file.lastModified}`)
      );
      return [...current, ...additions];
    });
    setSelectedFile(null);
    setJdText("");
    setMode("multi");
  }

  function handleAnalyzeClick() {
    if (mode === "multi") {
      void batchState.submitBatch();
      return;
    }
    void handleAnalyseJD();
  }

  return (
    <div className={`${styles.jdInputSection} card`}>
      {/* ── Card Header ──────────────────────────────────────────────── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <h3 style={{ margin: 0, fontSize: "1.1rem" }}>Step 2 &amp; 3: Enter Job Description &amp; Run Analysis</h3>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>

          {/* Single / Multi toggle pill */}
          <div className={styles.modeToggle}>
            <button
              type="button"
              className={`${styles.modeBtn} ${mode === "single" ? styles.modeBtnActive : ""}`}
              onClick={() => {
                setMode("single");
                batchState.setFiles([]);
              }}
            >
              Single JD
            </button>
            <button
              type="button"
              className={`${styles.modeBtn} ${mode === "multi" ? styles.modeBtnActive : ""}`}
              onClick={() => setMode("multi")}
            >
              ⚡ Multi JD
            </button>
          </div>

          {/* New JD / Agent reset — only in single mode */}
          {mode === "single" && agents.length > 0 && (
            <button
              type="button"
              className="btn-secondary"
              style={{ fontSize: "0.8rem", padding: "4px 10px" }}
              onClick={handleResetForNewJD}
            >
              ➕ New JD / Agent
            </button>
          )}

          {/* Single-JD status pill */}
          {mode === "single" && status && (
            <span className={`status-pill ${statusConfig[status]?.className}`}>
              {statusConfig[status]?.icon} {statusConfig[status]?.label}
            </span>
          )}
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════════ */}
      {/* SINGLE JD MODE                                                */}
      {/* ══════════════════════════════════════════════════════════════ */}
      {mode === "single" && (
        <>
          <div className="form-group" style={{ marginBottom: "16px" }}>
            <label>Target Job Title</label>
            <input
              type="text"
              className="input-text"
              value={jobTitle}
              onChange={(event) => setJobTitle(event.target.value)}
              placeholder="e.g. Senior Backend Engineer"
            />
          </div>

          <div className="form-group" style={{ marginBottom: "16px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <label>Job Description Content (Paste or Upload file) *</label>
              <label className="btn-secondary" style={{ cursor: "pointer", fontSize: "0.8rem", padding: "4px 10px" }}>
                📁 Upload File (.txt, .pdf, .docx)
                <input
                  type="file"
                  accept=".txt,.pdf,.docx"
                  onChange={handleFileUpload}
                  style={{ display: "none" }}
                />
              </label>
            </div>
            <textarea
              className="textarea"
              value={jdText}
              onChange={(event) => {
                setJdText(event.target.value);
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

          {/* Analysis progress bar */}
          {analysisRunning && (
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

          {analysisSuccessMsg && (
            <div className="alert-success" style={{ marginBottom: "16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>{analysisSuccessMsg}</span>
              <button type="button" className="btn-dismiss" onClick={() => setAnalysisSuccessMsg(null)} title="Dismiss notification">✕</button>
            </div>
          )}

          {error && (
            <div className="alert-error" style={{ marginBottom: "16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div><span>❌ {error}</span></div>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <button type="button" className="btn-retry" onClick={handleAnalyseJD} title="Retry analysis">🔄 Retry Analysis</button>
                <button type="button" className="btn-dismiss" onClick={() => setError(null)} title="Dismiss error">✕</button>
              </div>
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
            <button
              onClick={handleAnalyzeClick}
              disabled={(!jdText.trim() && !selectedFile) || analysisRunning}
              className="btn-primary"
            >
              {analysisRunning ? (
                <><span className="spinner"></span> Analyzing JD ({analysisProgress.percent}%)...</>
              ) : (
                "🚀 Analyse Job Description"
              )}
            </button>
          </div>
        </>
      )}

      {/* ══════════════════════════════════════════════════════════════ */}
      {/* MULTI JD MODE — parallel upload & simultaneous MD generation  */}
      {/* ══════════════════════════════════════════════════════════════ */}
      {mode === "multi" && (
        <div>
          <p style={{ margin: "0 0 14px", color: "#667085", fontSize: "0.85rem" }}>
            Upload multiple PDF, DOCX, or TXT job descriptions. Each JD is analysed using Ollama
            (qwen3:4b) in parallel and a Markdown specification is generated for every file independently.
          </p>

          {/* File picker row */}
          <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            <label className="btn-secondary" style={{ cursor: "pointer", fontSize: "0.84rem" }}>
              📁 Add JD file(s) to batch
              <input
                type="file"
                multiple
                accept=".txt,.pdf,.docx"
                onChange={handleAddMultipleFiles}
                style={{ display: "none" }}
              />
            </label>
            <span style={{ fontSize: "0.84rem", color: "#667085" }}>
              {batchFiles.length
                ? `${batchFiles.length} file${batchFiles.length === 1 ? "" : "s"} selected`
                : "Each file may be up to 5 MB"}
            </span>
            {batchFiles.length > 0 && (
              <button
                type="button"
                className="btn-ghost-dark"
                style={{ fontSize: "0.78rem" }}
                onClick={() => batchState.setFiles([])}
              >
                Clear selection
              </button>
            )}
          </div>

          {/* Selected file chips */}
          {batchFiles.length > 0 && (
            <ul className={styles.batchFileList} style={{ marginTop: "10px" }}>
              {batchFiles.map((file) => (
                <li key={`${file.name}-${file.lastModified}`}>
                  <span>{file.name}</span>
                  <span>{(file.size / 1024).toFixed(1)} KB</span>
                </li>
              ))}
            </ul>
          )}

          {batchState.error && !batchState.batch && (
            <div className="alert-error" role="alert" style={{ marginTop: "10px" }}>{batchState.error}</div>
          )}

          {/* Analyse button */}
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "14px" }}>
            <button
              type="button"
              className="btn-primary"
              onClick={handleAnalyzeClick}
              disabled={batchFiles.length === 0 || batchState.isSubmitting}
            >
              {batchState.isSubmitting ? (
                <><span className="spinner"></span> Starting {batchFiles.length} JD analyses...</>
              ) : (
                `🚀 Analyse ${batchFiles.length || ""} Job Description${batchFiles.length === 1 ? "" : "s"} in Parallel`
              )}
            </button>
          </div>

          {/* BatchUploadSection: progress, per-JD tabs, Markdown preview, clarifications */}
          {batchState.batch && (
            <BatchUploadSection
              state={batchState}
              onLaunchAgent={handleLaunchBatchAgent}
            />
          )}
        </div>
      )}
    </div>
  );
}
