import React from "react";
import type { SettingsPageProps } from "./SettingsPage";
import styles from "./AgentEditor.module.css";

type AgentEditorProps = Pick<
  SettingsPageProps,
  | "regenSuccessMsg"
  | "regenStatus"
  | "editTitle"
  | "setEditTitle"
  | "editCompany"
  | "setEditCompany"
  | "editJdText"
  | "setEditJdText"
  | "handleRegenerateAgentContext"
  | "isRegenerating"
  | "selectedSettingAgentId"
  | "agents"
  | "setDeleteError"
  | "setAgentToDelete"
>;

export default function AgentEditor({
    regenSuccessMsg,
    regenStatus,
    editTitle,
    setEditTitle,
    editCompany,
    setEditCompany,
    editJdText,
    setEditJdText,
    handleRegenerateAgentContext,
    isRegenerating,
    selectedSettingAgentId,
    agents,
    setDeleteError,
    setAgentToDelete,
}: AgentEditorProps) {
  return (
    <>
    {selectedSettingAgentId && (
                    <div className={`card ${styles.agentEditor}`}>
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

                      {/* Danger Zone: Delete Agent */}
                      <div
                        style={{
                          marginTop: "32px",
                          paddingTop: "20px",
                          borderTop: "1px solid #fee4e2",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          flexWrap: "wrap",
                          gap: "12px",
                        }}
                      >
                        <div>
                          <h4 style={{ margin: "0 0 4px 0", color: "#b42318", fontSize: "0.95rem" }}>Danger Zone: Delete Agent</h4>
                          <p style={{ margin: 0, fontSize: "0.8rem", color: "#667085" }}>
                            Remove this agent configuration and active chat sessions. Underlying Job Description specifications are permanently retained.
                          </p>
                        </div>
                        <button
                          type="button"
                          style={{
                            backgroundColor: "#d92d20",
                            color: "#ffffff",
                            border: "none",
                            borderRadius: "6px",
                            padding: "8px 14px",
                            fontSize: "0.84rem",
                            fontWeight: 600,
                            cursor: "pointer",
                            whiteSpace: "nowrap",
                          }}
                          onClick={() => {
                            const target = agents.find((a) => a.id === selectedSettingAgentId);
                            if (target) {
                              setDeleteError(null);
                              setAgentToDelete(target);
                            }
                          }}
                        >
                          🗑️ Delete Agent
                        </button>
                      </div>
                    </div>
                  )}
                  </>
  );
}
