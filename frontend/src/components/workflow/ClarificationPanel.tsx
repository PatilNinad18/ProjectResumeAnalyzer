import type { WorkflowPageProps } from "./WorkflowPage";
import styles from "./ClarificationPanel.module.css";

type ClarificationPanelProps = Pick<WorkflowPageProps, "isStep3Done" | "clarificationsData" | "allClarificationItems" | "setClarificationViewMode" | "clarificationViewMode" | "isResolvingClarifications" | "resolveProgress" | "handleCancelResolve" | "resolveSuccessMsg" | "setContextTab" | "fetchComparison" | "setResolveSuccessMsg" | "resolveError" | "handleResolveClarifications" | "setResolveError" | "activeClarificationIndex" | "setActiveClarificationIndex" | "setClarificationAnswers">;

export default function ClarificationPanel({
    isStep3Done,
    clarificationsData,
    allClarificationItems,
    setClarificationViewMode,
    clarificationViewMode,
    isResolvingClarifications,
    resolveProgress,
    handleCancelResolve,
    resolveSuccessMsg,
    setContextTab,
    fetchComparison,
    setResolveSuccessMsg,
    resolveError,
    handleResolveClarifications,
    setResolveError,
    activeClarificationIndex,
    setActiveClarificationIndex,
    setClarificationAnswers,
}: ClarificationPanelProps) {
  return (
    <>
      {isStep3Done && allClarificationItems.length === 0 && (
        <div className={`${styles.clarificationPanel} card`} style={{ borderLeft: "4px solid #10b981", padding: "18px 20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{ background: "#dcfce7", color: "#166534", borderRadius: "50%", width: "36px", height: "36px", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: "1.2rem", flexShrink: 0 }}>
              ✓
            </div>
            <div>
              <h4 style={{ margin: "0 0 3px 0", fontSize: "1.05rem", color: "#065f46", display: "flex", alignItems: "center", gap: "8px" }}>
                <span>Step 4: Role Requirements Fully Explicit</span>
                <span style={{ background: "#dcfce7", color: "#166534", fontSize: "0.75rem", padding: "2px 8px", borderRadius: "12px", fontWeight: 600 }}>
                  0 Ambiguities Detected
                </span>
              </h4>
              <p style={{ margin: 0, fontSize: "0.85rem", color: "#667085" }}>
                All role requirements, qualifications, and parameters are clear and unambiguous. Proceed to final specification review and agent creation below.
              </p>
            </div>
          </div>
        </div>
      )}
      {isStep3Done && allClarificationItems.length > 0 && (
                <div className={`${styles.clarificationPanel} card`} style={{ borderLeft: "4px solid #f59e0b", padding: "20px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
                    <div>
                      <h3 style={{ margin: "0 0 4px 0", fontSize: "1.15rem", display: "flex", alignItems: "center", gap: "8px" }}>
                        <span>Step 4: Resolve Ambiguities & Trade-offs</span>
                        {clarificationsData?.lifecycle_status === "FINALIZED" ? (
                          <span style={{ background: "#dcfce7", color: "#166534", fontSize: "0.75rem", padding: "2px 8px", borderRadius: "12px", fontWeight: 600 }}>
                            ✓ Finalized
                          </span>
                        ) : (
                          <span style={{ background: "#fef3c7", color: "#92400e", fontSize: "0.75rem", padding: "2px 8px", borderRadius: "12px", fontWeight: 600 }}>
                            Action Required
                          </span>
                        )}
                        <span style={{
                          background: "#e0e7ff",
                          color: "#4338ca",
                          fontSize: "0.75rem",
                          padding: "2px 8px",
                          borderRadius: "12px",
                          fontWeight: 600,
                        }}>
                          {allClarificationItems.filter(i => i.isResolved).length} / {allClarificationItems.length} Resolved
                        </span>
                      </h3>
                      <p style={{ margin: 0, fontSize: "0.85rem", color: "#667085" }}>
                        Select domain options below or provide custom notes. Answering these trade-offs generates the final disambiguated specification.
                      </p>
                    </div>

                    {/* View mode toggle */}
                    <div style={{ display: "flex", gap: "4px", background: "#f1f5f9", padding: "3px", borderRadius: "8px" }}>
                      <button
                        type="button"
                        onClick={() => setClarificationViewMode("wizard")}
                        style={{
                          fontSize: "0.76rem",
                          fontWeight: clarificationViewMode === "wizard" ? 700 : 500,
                          padding: "4px 10px",
                          borderRadius: "6px",
                          border: "none",
                          background: clarificationViewMode === "wizard" ? "#ffffff" : "transparent",
                          color: clarificationViewMode === "wizard" ? "#1e293b" : "#64748b",
                          cursor: "pointer",
                          boxShadow: clarificationViewMode === "wizard" ? "0 1px 2px rgba(0,0,0,0.06)" : "none",
                        }}
                      >
                        🎯 Step-by-Step
                      </button>
                      <button
                        type="button"
                        onClick={() => setClarificationViewMode("all")}
                        style={{
                          fontSize: "0.76rem",
                          fontWeight: clarificationViewMode === "all" ? 700 : 500,
                          padding: "4px 10px",
                          borderRadius: "6px",
                          border: "none",
                          background: clarificationViewMode === "all" ? "#ffffff" : "transparent",
                          color: clarificationViewMode === "all" ? "#1e293b" : "#64748b",
                          cursor: "pointer",
                          boxShadow: clarificationViewMode === "all" ? "0 1px 2px rgba(0,0,0,0.06)" : "none",
                        }}
                      >
                        📄 View All
                      </button>
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

                  {/* Horizontal Topic Tab Bar (Claude Stepper) */}
                  <div style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    overflowX: "auto",
                    paddingBottom: "8px",
                    marginBottom: "16px",
                    borderBottom: "1px solid #e2e8f0",
                  }}>
                    {allClarificationItems.map((item, idx) => {
                      const isActive = activeClarificationIndex === idx && clarificationViewMode === "wizard";
                      const isDone = item.isResolved;
                      return (
                        <button
                          key={item.key}
                          type="button"
                          onClick={() => {
                            setActiveClarificationIndex(idx);
                            if (clarificationViewMode !== "wizard") setClarificationViewMode("wizard");
                          }}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "5px",
                            padding: "6px 12px",
                            borderRadius: "16px",
                            fontSize: "0.80rem",
                            fontWeight: isActive ? 700 : 500,
                            whiteSpace: "nowrap",
                            border: isActive
                              ? "1.5px solid #4f46e5"
                              : isDone
                              ? "1px solid #86efac"
                              : "1px solid #cbd5e1",
                            background: isActive
                              ? "#4f46e5"
                              : isDone
                              ? "#f0fdf4"
                              : "#ffffff",
                            color: isActive
                              ? "#ffffff"
                              : isDone
                              ? "#166534"
                              : "#334155",
                            cursor: "pointer",
                            transition: "all 0.12s ease",
                          }}
                        >
                          <span>{isDone ? "✓" : "○"}</span>
                          <span>{item.topic}</span>
                        </button>
                      );
                    })}

                    {/* Submit / Review Tab */}
                    <button
                      type="button"
                      onClick={() => {
                        setActiveClarificationIndex(allClarificationItems.length);
                        if (clarificationViewMode !== "wizard") setClarificationViewMode("wizard");
                      }}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "5px",
                        padding: "6px 14px",
                        borderRadius: "16px",
                        fontSize: "0.80rem",
                        fontWeight: activeClarificationIndex === allClarificationItems.length ? 700 : 600,
                        whiteSpace: "nowrap",
                        border: activeClarificationIndex === allClarificationItems.length
                          ? "1.5px solid #d97706"
                          : "1px solid #fcd34d",
                        background: activeClarificationIndex === allClarificationItems.length
                          ? "#d97706"
                          : "#fffbeb",
                        color: activeClarificationIndex === allClarificationItems.length
                          ? "#ffffff"
                          : "#92400e",
                        cursor: "pointer",
                        transition: "all 0.12s ease",
                      }}
                    >
                      <span>✓</span>
                      <span>Submit →</span>
                    </button>
                  </div>

                  {/* Mode 1: Step-by-Step Wizard */}
                  {clarificationViewMode === "wizard" && (
                    <>
                      {activeClarificationIndex < allClarificationItems.length ? (
                        (() => {
                          const item = allClarificationItems[activeClarificationIndex];
                          const hasStructured = item.structuredOptions.length > 0;
                          const currentVal = item.currentValue;

                          // Check if current value matches any predefined option
                          const matchingPredefinedIndex = hasStructured
                            ? item.structuredOptions.findIndex((opt) => {
                                const optVal = opt.description ? `${opt.label}: ${opt.description}` : opt.label;
                                return (
                                  currentVal === optVal ||
                                  currentVal === opt.label ||
                                  (opt.label.length > 4 && currentVal.toLowerCase().startsWith(opt.label.toLowerCase()))
                                );
                              })
                            : -1;

                          const isCustomActive = currentVal && matchingPredefinedIndex === -1;

                          return (
                            <div
                              style={{
                                background: "#ffffff",
                                border: "1px solid #e2e8f0",
                                borderRadius: "10px",
                                padding: "20px",
                                marginBottom: "16px",
                                boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                              }}
                            >
                              {/* Header Meta */}
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                                <span style={{ fontSize: "0.78rem", fontWeight: 700, color: "#6366f1", letterSpacing: "0.03em" }}>
                                  TOPIC {activeClarificationIndex + 1} OF {allClarificationItems.length}: {item.topic.toUpperCase()}
                                </span>
                                <div style={{ display: "flex", gap: "6px" }}>
                                  {item.isResolved && (
                                    <span style={{ fontSize: "0.72rem", fontWeight: 700, padding: "2px 8px", borderRadius: "12px", background: "#dcfce7", color: "#166534" }}>
                                      ✓ ANSWERED
                                    </span>
                                  )}
                                  <span style={{
                                    fontSize: "0.72rem",
                                    fontWeight: 600,
                                    padding: "2px 8px",
                                    borderRadius: "12px",
                                    background: item.priority === "BLOCKING" ? "#fee2e2" : "#fef3c7",
                                    color: item.priority === "BLOCKING" ? "#991b1b" : "#92400e",
                                  }}>
                                    {item.priority || "RECOMMENDED"}
                                  </span>
                                </div>
                              </div>

                              {/* Conversational Question Headline */}
                              <h4 style={{ margin: "4px 0 10px 0", fontSize: "1.08rem", fontWeight: 600, color: "#0f172a", lineHeight: 1.45 }}>
                                {item.questionText}
                              </h4>

                              {/* Rationale hint */}
                              {item.rationale && (
                                <div style={{ fontSize: "0.82rem", color: "#64748b", marginBottom: "16px", padding: "8px 12px", background: "#f8fafc", borderRadius: "6px", borderLeft: "3px solid #cbd5e1" }}>
                                  <strong>Context:</strong> {item.rationale}
                                </div>
                              )}

                              {/* Structured Options (Claude Style numbered cards) */}
                              <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginBottom: "18px" }}>
                                {item.structuredOptions.map((opt, optIdx) => {
                                  const isSelected = matchingPredefinedIndex === optIdx;
                                  return (
                                    <div
                                      key={optIdx}
                                      onClick={() => {
                                        const answerPayload = opt.description ? `${opt.label}: ${opt.description}` : opt.label;
                                        setClarificationAnswers((prev) => ({
                                          ...prev,
                                          [item.key]: answerPayload,
                                        }));
                                      }}
                                      style={{
                                        display: "flex",
                                        alignItems: "flex-start",
                                        gap: "12px",
                                        padding: "12px 14px",
                                        borderRadius: "8px",
                                        border: isSelected ? "1.5px solid #4f46e5" : "1px solid #e2e8f0",
                                        background: isSelected ? "#f5f3ff" : "#ffffff",
                                        cursor: "pointer",
                                        transition: "all 0.15s ease",
                                      }}
                                    >
                                      {/* Radio indicator */}
                                      <div
                                        style={{
                                          width: "18px",
                                          height: "18px",
                                          borderRadius: "50%",
                                          border: isSelected ? "5px solid #4f46e5" : "1.5px solid #94a3b8",
                                          background: "#ffffff",
                                          marginTop: "2px",
                                          flexShrink: 0,
                                        }}
                                      />
                                      <div style={{ flex: 1 }}>
                                        <div style={{ fontSize: "0.92rem", fontWeight: 700, color: isSelected ? "#3730a3" : "#1e293b", marginBottom: "2px" }}>
                                          {optIdx + 1}. {opt.label}
                                        </div>
                                        {opt.description && (
                                          <div style={{ fontSize: "0.83rem", color: isSelected ? "#4338ca" : "#64748b", lineHeight: 1.4 }}>
                                            {opt.description}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  );
                                })}

                                {/* Freeform Custom Option: 'Type something.' */}
                                <div
                                  style={{
                                    display: "flex",
                                    flexDirection: "column",
                                    padding: "12px 14px",
                                    borderRadius: "8px",
                                    border: isCustomActive ? "1.5px solid #4f46e5" : "1px solid #e2e8f0",
                                    background: isCustomActive ? "#f5f3ff" : "#ffffff",
                                    transition: "all 0.15s ease",
                                  }}
                                >
                                  <div
                                    onClick={() => {
                                      if (!isCustomActive) {
                                        setClarificationAnswers((prev) => ({
                                          ...prev,
                                          [item.key]: prev[item.key] && matchingPredefinedIndex === -1 ? prev[item.key] : "",
                                        }));
                                      }
                                    }}
                                    style={{ display: "flex", alignItems: "center", gap: "12px", cursor: "pointer", marginBottom: isCustomActive ? "10px" : "0" }}
                                  >
                                    <div
                                      style={{
                                        width: "18px",
                                        height: "18px",
                                        borderRadius: "50%",
                                        border: isCustomActive ? "5px solid #4f46e5" : "1.5px solid #94a3b8",
                                        background: "#ffffff",
                                        flexShrink: 0,
                                      }}
                                    />
                                    <span style={{ fontSize: "0.92rem", fontWeight: 700, color: isCustomActive ? "#3730a3" : "#334155" }}>
                                      {item.structuredOptions.length + 1}. Type something...
                                    </span>
                                  </div>

                                  {/* Custom input textarea */}
                                  <textarea
                                    className="input-text"
                                    rows={2}
                                    style={{
                                      width: "100%",
                                      marginTop: "4px",
                                      background: "#ffffff",
                                      borderColor: isCustomActive ? "#4f46e5" : "#cbd5e1",
                                      fontSize: "0.85rem",
                                      lineHeight: 1.4,
                                    }}
                                    placeholder="Write your custom TA clarification or specific screening instructions..."
                                    value={isCustomActive ? currentVal : ""}
                                    onChange={(e) => {
                                      setClarificationAnswers((prev) => ({
                                        ...prev,
                                        [item.key]: e.target.value,
                                      }));
                                    }}
                                  />
                                </div>
                              </div>

                              {/* Stepper Footer Controls */}
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: "12px", borderTop: "1px solid #f1f5f9" }}>
                                <button
                                  type="button"
                                  className="btn-secondary"
                                  disabled={activeClarificationIndex === 0}
                                  onClick={() => setActiveClarificationIndex(Math.max(0, activeClarificationIndex - 1))}
                                  style={{ fontSize: "0.84rem", padding: "6px 14px" }}
                                >
                                  ← Previous
                                </button>
                                <span style={{ fontSize: "0.80rem", color: "#64748b", fontWeight: 500 }}>
                                  Question {activeClarificationIndex + 1} of {allClarificationItems.length}
                                </span>
                                {activeClarificationIndex < allClarificationItems.length - 1 ? (
                                  <button
                                    type="button"
                                    className="btn-primary"
                                    onClick={() => setActiveClarificationIndex(activeClarificationIndex + 1)}
                                    style={{ fontSize: "0.84rem", padding: "6px 16px" }}
                                  >
                                    Next →
                                  </button>
                                ) : (
                                  <button
                                    type="button"
                                    className="btn-primary"
                                    onClick={() => setActiveClarificationIndex(allClarificationItems.length)}
                                    style={{ fontSize: "0.84rem", padding: "6px 16px", background: "#d97706", borderColor: "#b45309" }}
                                  >
                                    Review & Submit →
                                  </button>
                                )}
                              </div>
                            </div>
                          );
                        })()
                      ) : (
                        /* Submission & Review Screen (Submit Tab) */
                        <div
                          style={{
                            background: "#ffffff",
                            border: "1px solid #e2e8f0",
                            borderRadius: "10px",
                            padding: "24px",
                            marginBottom: "16px",
                          }}
                        >
                          <h4 style={{ margin: "0 0 8px 0", fontSize: "1.1rem", fontWeight: 700, color: "#0f172a" }}>
                            📋 Review Your Clarification Answers
                          </h4>
                          <p style={{ margin: "0 0 16px 0", fontSize: "0.86rem", color: "#64748b" }}>
                            You have resolved {allClarificationItems.filter(i => i.isResolved).length} of {allClarificationItems.length} items. Review your selections below before finalizing the specification.
                          </p>

                          <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginBottom: "20px" }}>
                            {allClarificationItems.map((item, idx) => (
                              <div
                                key={item.key}
                                onClick={() => setActiveClarificationIndex(idx)}
                                style={{
                                  display: "flex",
                                  justifyContent: "space-between",
                                  alignItems: "center",
                                  padding: "10px 14px",
                                  borderRadius: "6px",
                                  background: item.isResolved ? "#f0fdf4" : "#fef2f2",
                                  border: item.isResolved ? "1px solid #bbf7d0" : "1px solid #fecaca",
                                  cursor: "pointer",
                                }}
                              >
                                <div style={{ display: "flex", alignItems: "center", gap: "8px", flex: 1, marginRight: "12px" }}>
                                  <span style={{ fontWeight: 700, color: item.isResolved ? "#166534" : "#991b1b" }}>
                                    {item.isResolved ? "✓" : "!"}
                                  </span>
                                  <div style={{ fontSize: "0.86rem" }}>
                                    <strong>{item.topic}:</strong>{" "}
                                    <span style={{ color: item.isResolved ? "#1e293b" : "#991b1b" }}>
                                      {item.currentValue ? item.currentValue.slice(0, 85) + (item.currentValue.length > 85 ? "..." : "") : "Unanswered (Click to answer)"}
                                    </span>
                                  </div>
                                </div>
                                <span style={{ fontSize: "0.75rem", color: "#6366f1", fontWeight: 600 }}>Edit ✎</span>
                              </div>
                            ))}
                          </div>

                          <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
                            <button
                              type="button"
                              className="btn-secondary"
                              onClick={() => setActiveClarificationIndex(0)}
                              style={{ fontSize: "0.85rem", padding: "8px 16px" }}
                            >
                              ← Back to First Question
                            </button>
                            <button
                              type="button"
                              className="btn-primary"
                              disabled={isResolvingClarifications}
                              onClick={handleResolveClarifications}
                              style={{ background: "#d97706", borderColor: "#b45309", fontSize: "0.88rem", padding: "8px 20px" }}
                            >
                              {isResolvingClarifications
                                ? "⏳ Resolving & Generating Final Markdown..."
                                : "✓ Confirm Answers & Generate Final Specification"}
                            </button>
                          </div>
                        </div>
                      )}
                    </>
                  )}

                  {/* Mode 2: View All (Stacked) */}
                  {clarificationViewMode === "all" && (
                    <div style={{ display: "flex", flexDirection: "column", gap: "16px", marginBottom: "20px" }}>
                      {allClarificationItems.map((item, idx) => {
                        const hasStructured = item.structuredOptions.length > 0;
                        const currentVal = item.currentValue;

                        const matchingPredefinedIndex = hasStructured
                          ? item.structuredOptions.findIndex((opt) => {
                              const optVal = opt.description ? `${opt.label}: ${opt.description}` : opt.label;
                              return (
                                currentVal === optVal ||
                                currentVal === opt.label ||
                                (opt.label.length > 4 && currentVal.toLowerCase().startsWith(opt.label.toLowerCase()))
                              );
                            })
                          : -1;

                        const isCustomActive = currentVal && matchingPredefinedIndex === -1;

                        return (
                          <div
                            key={item.key}
                            style={{
                              background: item.isResolved ? "#faf5ff" : "#ffffff",
                              border: item.isResolved ? "1px solid #ddd6fe" : "1px solid #e2e8f0",
                              borderRadius: "8px",
                              padding: "16px",
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
                              <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "#1e293b", flex: 1 }}>
                                {idx + 1}. {item.questionText}
                              </span>
                              <div style={{ display: "flex", gap: "6px" }}>
                                {item.isResolved && (
                                  <span style={{ fontSize: "0.72rem", fontWeight: 700, padding: "2px 8px", borderRadius: "12px", background: "#dcfce7", color: "#166534" }}>
                                    ✓ ANSWERED
                                  </span>
                                )}
                                <span style={{ fontSize: "0.72rem", fontWeight: 600, padding: "2px 8px", borderRadius: "12px", background: "#f1f5f9", color: "#475569" }}>
                                  {item.topic}
                                </span>
                              </div>
                            </div>

                            {item.rationale && (
                              <div style={{ fontSize: "0.82rem", color: "#64748b", marginBottom: "12px" }}>
                                <strong>Context:</strong> {item.rationale}
                              </div>
                            )}

                            {/* Options cards */}
                            <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginBottom: "12px" }}>
                              {item.structuredOptions.map((opt, optIdx) => {
                                const isSelected = matchingPredefinedIndex === optIdx;
                                return (
                                  <div
                                    key={optIdx}
                                    onClick={() => {
                                      const answerPayload = opt.description ? `${opt.label}: ${opt.description}` : opt.label;
                                      setClarificationAnswers((prev) => ({
                                        ...prev,
                                        [item.key]: answerPayload,
                                      }));
                                    }}
                                    style={{
                                      display: "flex",
                                      alignItems: "flex-start",
                                      gap: "10px",
                                      padding: "10px 12px",
                                      borderRadius: "6px",
                                      border: isSelected ? "1.5px solid #4f46e5" : "1px solid #e2e8f0",
                                      background: isSelected ? "#f5f3ff" : "#ffffff",
                                      cursor: "pointer",
                                    }}
                                  >
                                    <div
                                      style={{
                                        width: "16px",
                                        height: "16px",
                                        borderRadius: "50%",
                                        border: isSelected ? "5px solid #4f46e5" : "1.5px solid #94a3b8",
                                        background: "#ffffff",
                                        marginTop: "2px",
                                        flexShrink: 0,
                                      }}
                                    />
                                    <div>
                                      <span style={{ fontSize: "0.88rem", fontWeight: 700, color: isSelected ? "#3730a3" : "#1e293b" }}>
                                        {opt.label}
                                      </span>
                                      {opt.description && (
                                        <span style={{ fontSize: "0.82rem", color: "#64748b", marginLeft: "6px" }}>
                                          — {opt.description}
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}

                              {/* Custom input */}
                              <textarea
                                className="input-text"
                                rows={2}
                                style={{
                                  width: "100%",
                                  background: "#ffffff",
                                  borderColor: isCustomActive ? "#4f46e5" : "#cbd5e1",
                                  fontSize: "0.85rem",
                                }}
                                placeholder="Type custom clarification or notes..."
                                value={isCustomActive ? currentVal : ""}
                                onChange={(e) => {
                                  setClarificationAnswers((prev) => ({
                                    ...prev,
                                    [item.key]: e.target.value,
                                  }));
                                }}
                              />
                            </div>
                          </div>
                        );
                      })}

                      <div style={{ display: "flex", justifyContent: "flex-end" }}>
                        <button
                          className="btn-primary"
                          disabled={isResolvingClarifications}
                          onClick={handleResolveClarifications}
                          style={{ background: "#d97706", borderColor: "#b45309", padding: "8px 22px" }}
                        >
                          {isResolvingClarifications
                            ? "⏳ Resolving & Generating Final Markdown..."
                            : "✓ Confirm Answers & Generate Final Specification"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
    </>
  );
}
