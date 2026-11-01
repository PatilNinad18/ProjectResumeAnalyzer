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
  const analysisRunning = status !== null && !TERMINAL_STATUSES.includes(status);
  const batchFiles = batchState.files;
  const batchUploadSelected = batchFiles.length > 0;

  function handleJobDescriptionFiles(event: React.ChangeEvent<HTMLInputElement>) {
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
  }

  function handleAnalyzeClick() {
    if (batchUploadSelected) {
      void batchState.submitBatch();
      return;
    }
    void handleAnalyseJD();
  }

  return (
    <div className={`${styles.jdInputSection} card`}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <h3 style={{ margin: 0, fontSize: "1.1rem" }}>Step 2 &amp; 3: Enter Job Description &amp; Run Analysis</h3>
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
          onChange={(event) => setJobTitle(event.target.value)}
          placeholder="e.g. Senior Backend Engineer"
        />
      </div>

      <div className="form-group" style={{ marginBottom: "16px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <label>Job Description Content (Paste or Upload JD files) *</label>
          <label className="btn-secondary" style={{ cursor: "pointer", fontSize: "0.8rem", padding: "4px 10px" }}>
          📁 Add JD file(s) to batch
            <input
              type="file"
              multiple
              accept=".txt,.pdf,.docx"
              onChange={handleJobDescriptionFiles}
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
            batchState.setFiles([]);
          }}
          placeholder="Paste one JD here, or use Add JD file(s) to select multiple files (you can add files more than once)..."
        />
        {batchUploadSelected && (
          <div className={styles.batchSelection}>
            <div className={styles.batchSelectionHeader}>
              <strong>{batchFiles.length} job descriptions selected for parallel processing</strong>
              <button
                type="button"
                className="btn-ghost-dark"
                onClick={() => batchState.setFiles([])}
              >
                Clear selection
              </button>
            </div>
            <ul className={styles.batchFileList}>
              {batchFiles.map((file) => (
                <li key={`${file.name}-${file.lastModified}`}>
                  <span>{file.name}</span>
                  <span>{(file.size / 1024).toFixed(1)} KB</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {batchState.error && !batchState.batch && (
          <div className="alert-error" role="alert">{batchState.error}</div>
        )}
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
          <div><span>❌ {error}</span></div>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <button type="button" className="btn-retry" onClick={handleAnalyseJD} title="Retry analysis">
              🔄 Retry Analysis
            </button>
            <button type="button" className="btn-dismiss" onClick={() => setError(null)} title="Dismiss error">
              ✕
            </button>
          </div>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
        <button
          onClick={handleAnalyzeClick}
          disabled={batchUploadSelected
            ? batchState.isSubmitting || analysisRunning
            : (!jdText.trim() && !selectedFile) || analysisRunning}
          className="btn-primary"
        >
          {batchUploadSelected ? (
            batchState.isSubmitting ? (
              <>
                <span className="spinner"></span> Starting {batchFiles.length} JD analyses...
              </>
            ) : (
              `🚀 Analyze ${batchFiles.length} Job Description${batchFiles.length === 1 ? "" : "s"}`
            )
          ) : analysisRunning ? (
            <>
              <span className="spinner"></span> Analyzing JD ({analysisProgress.percent}%)...
            </>
          ) : (
            "🚀 Analyse Job Description"
          )}
        </button>
      </div>

      {batchState.batch && (
        <BatchUploadSection
          state={batchState}
          onLaunchAgent={handleLaunchBatchAgent}
        />
      )}
    </div>
  );
}
