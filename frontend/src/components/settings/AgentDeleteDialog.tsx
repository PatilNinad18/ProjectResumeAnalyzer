
import React from "react";
import type { CreatedAgent } from "@/lib/api";
import styles from "./AgentDeleteDialog.module.css";

interface AgentDeleteDialogProps {
  agentToDelete: CreatedAgent | null;
  isDeletingAgent: boolean;
  setAgentToDelete: React.Dispatch<React.SetStateAction<CreatedAgent | null>>;
  jdId: string | null;
  deleteError: string | null;
  handleDeleteAgent: (agentId: string, cancelActive?: boolean) => Promise<void>;
}

export default function AgentDeleteDialog({
    agentToDelete,
    isDeletingAgent,
    setAgentToDelete,
    jdId,
    deleteError,
    handleDeleteAgent,
}: AgentDeleteDialogProps) {
  return (
    <>
    {agentToDelete && (
            <div className={styles.agentDeleteDialog}
              style={{
                position: "fixed",
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                backgroundColor: "rgba(16, 24, 40, 0.6)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                zIndex: 9999,
                padding: "20px",
              }}
              onClick={() => !isDeletingAgent && setAgentToDelete(null)}
            >
              <div
                className="card"
                style={{
                  maxWidth: "500px",
                  width: "100%",
                  backgroundColor: "#ffffff",
                  borderRadius: "12px",
                  padding: "24px",
                  boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px" }}>
                  <div
                    style={{
                      width: "40px",
                      height: "40px",
                      borderRadius: "50%",
                      backgroundColor: "#fee4e2",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "1.2rem",
                    }}
                  >
                    ⚠️
                  </div>
                  <div>
                    <h3 style={{ margin: 0, fontSize: "1.1rem", color: "#101828" }}>Delete Agent Confirmation</h3>
                    <p style={{ margin: "2px 0 0 0", fontSize: "0.82rem", color: "#667085" }}>
                      Explicit confirmation required
                    </p>
                  </div>
                </div>

                <p style={{ fontSize: "0.9rem", color: "#344054", lineHeight: 1.5, margin: "0 0 12px 0" }}>
                  Are you sure you want to delete <strong>{agentToDelete.agentName}</strong> ({agentToDelete.title || "JD Agent"})?
                </p>

                <div
                  style={{
                    backgroundColor: "#f9fafb",
                    border: "1px solid #eaecf0",
                    borderRadius: "8px",
                    padding: "12px",
                    marginBottom: "16px",
                    fontSize: "0.82rem",
                    color: "#475467",
                  }}
                >
                  <div><strong>Agent ID:</strong> {agentToDelete.id}</div>
                  <div><strong>Job Description ID:</strong> {agentToDelete.jdId}</div>
                  <div style={{ marginTop: "6px", color: "#027a48", fontWeight: 500 }}>
                    🛡️ <strong>Data Retention Guarantee:</strong> The underlying job description, specifications, and clarification records will be preserved in the compliance audit trail.
                  </div>
                </div>

                {deleteError && (
                  <div className="alert-error" style={{ marginBottom: "16px", fontSize: "0.85rem" }}>
                    ⚠️ {deleteError}
                  </div>
                )}

                <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={isDeletingAgent}
                    onClick={() => setAgentToDelete(null)}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    style={{
                      backgroundColor: "#d92d20",
                      color: "#ffffff",
                      border: "none",
                      borderRadius: "6px",
                      padding: "8px 16px",
                      fontSize: "0.9rem",
                      fontWeight: 600,
                      cursor: isDeletingAgent ? "not-allowed" : "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                    }}
                    disabled={isDeletingAgent}
                    onClick={() => handleDeleteAgent(agentToDelete.id, true)}
                  >
                    {isDeletingAgent ? (
                      <>
                        <span className="spinner"></span> Deleting...
                      </>
                    ) : (
                      "Yes, Delete Agent"
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}
    </>
  );
}
