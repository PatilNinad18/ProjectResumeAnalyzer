import ReactMarkdown from "react-markdown";
import type { RequirementDiffItem } from "@/lib/api";
import type { WorkflowPageProps } from "./WorkflowPage";
import styles from "./SpecificationViewer.module.css";

type SpecificationViewerProps = Pick<WorkflowPageProps, "isStep3Done" | "markdown" | "step4Ref" | "specVersion" | "contextTab" | "setContextTab" | "isEnrichedView" | "fetchComparison" | "comparisonBaseContext" | "comparisonTargetContext" | "isDiffActive" | "setShowDiffHighlights" | "showDiffHighlights" | "diffChangedCount" | "handleToggleEnrichment" | "downloadFile" | "jsonData" | "setComparisonBaseContext" | "setComparisonTargetContext" | "comparisonData" | "isLoadingComparison" | "comparisonFilter" | "setComparisonFilter" | "comparisonViewMode" | "setComparisonViewMode" | "setMarkdownDiff" | "markdownDiff">;

export default function SpecificationViewer({
    isStep3Done,
    markdown,
    step4Ref,
    specVersion,
    contextTab,
    setContextTab,
    isEnrichedView,
    fetchComparison,
    comparisonBaseContext,
    comparisonTargetContext,
    isDiffActive,
    setShowDiffHighlights,
    showDiffHighlights,
    diffChangedCount,
    handleToggleEnrichment,
    downloadFile,
    jsonData,
    setComparisonBaseContext,
    setComparisonTargetContext,
    comparisonData,
    isLoadingComparison,
    comparisonFilter,
    setComparisonFilter,
    comparisonViewMode,
    setComparisonViewMode,
    setMarkdownDiff,
    markdownDiff,
}: SpecificationViewerProps) {
  return (
    <>
      {isStep3Done && markdown && (
                <div className={`${styles.specificationViewer} card`} ref={step4Ref}>
                  <div className="preview-header">
                    <div>
                      <h3 style={{ margin: 0, fontSize: "1.1rem" }}>Step 5: Final Specification (v{specVersion})</h3>
                      <span style={{ fontSize: "0.82rem", color: "#667085" }}>
                        {specVersion > 1 ? "Disambiguated specification reflecting confirmed TA clarifications." : "Deterministic baseline specification extracted from job description."}
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
                      {/* Highlight Changes Toggle — only shown when a valid diff is active for this spec version */}
                      {isDiffActive && contextTab === "markdown" && (
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
                          }}
                        >
                          <span>{showDiffHighlights ? "✦" : "○"}</span>
                          Highlight Changes ({diffChangedCount})
                        </button>
                      )}
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
                        <>
                          {/* What Changed Banner (shown after ambiguity resolution with diffs) */}
                          {isDiffActive && (
                            <div style={{
                              background: "linear-gradient(135deg, #ecfdf5 0%, #f0fdf4 100%)",
                              border: "1px solid #a7f3d0",
                              borderRadius: "10px",
                              padding: "14px 18px",
                              marginBottom: "16px",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                              gap: "12px",
                              flexWrap: "wrap",
                            }}>
                              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                                <span style={{ fontSize: "1.25rem" }}>✨</span>
                                <div>
                                  <div style={{ fontWeight: 700, fontSize: "0.95rem", color: "#065f46" }}>
                                    Specification v{specVersion} Generated with Your Clarifications
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

                          {/* Diff-highlighted markdown or plain markdown */}
                          {isDiffActive && markdownDiff ? (
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
                                          marginLeft: "-13px",
                                          borderRadius: "0 4px 4px 0",
                                          position: "relative",
                                        }
                                      : {}
                                  }
                                >
                                  {seg.changed && (
                                    <span style={{
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
                                    }}>
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
                        </>
                      ) : (
                        <pre style={{ margin: 0, fontFamily: "monospace", color: "#344054" }}>
                          {JSON.stringify(jsonData, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              )}
    </>
  );
}
