import React, { useState } from "react";
import type { SettingsPageProps } from "./SettingsPage";
import { cleanupTestAgentsApi } from "@/lib/api";
import styles from "./AgentList.module.css";

type AgentListProps = Pick<
  SettingsPageProps,
  | "agents"
  | "selectedSettingAgentId"
  | "setSelectedSettingAgentId"
  | "setSelectedAgentId"
  | "setActiveTab"
  | "setDeleteError"
  | "setAgentToDelete"
  | "handleCleanupTestAgents"
  | "isCleaningTestAgents"
>;

export default function AgentList({
  agents,
  selectedSettingAgentId,
  setSelectedSettingAgentId,
  setSelectedAgentId,
  setActiveTab,
  setDeleteError,
  setAgentToDelete,
  handleCleanupTestAgents,
  isCleaningTestAgents,
}: AgentListProps) {
  const [showCleanupModal, setShowCleanupModal] = useState(false);
  const [previewTestAgents, setPreviewTestAgents] = useState<
    Array<{ id: string; name: string; project_name?: string }>
  >([]);
  const [isChecking, setIsChecking] = useState(false);

  async function handleCheckTestAgents() {
    setIsChecking(true);
    try {
      const res = await cleanupTestAgentsApi(true);
      setPreviewTestAgents(res.test_agents || []);
      setShowCleanupModal(true);
    } catch (err) {
      alert("Could not scan for test agents: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setIsChecking(false);
    }
  }

  async function handleConfirmCleanup() {
    if (!handleCleanupTestAgents) return;
    try {
      await handleCleanupTestAgents(false);
      setShowCleanupModal(false);
      setPreviewTestAgents([]);
    } catch (err) {
      alert("Cleanup failed: " + (err instanceof Error ? err.message : String(err)));
    }
  }

  return (
    <div className={styles.agentList}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "12px",
          flexWrap: "wrap",
          gap: "8px",
        }}
      >
        <h4 style={{ margin: 0, color: "#344054" }}>Created Agents ({agents.length})</h4>
        <button
          type="button"
          className="btn-secondary"
          style={{
            fontSize: "0.76rem",
            padding: "4px 8px",
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            borderColor: "#d0d5dd",
          }}
          onClick={() => void handleCheckTestAgents()}
          disabled={isChecking || Boolean(isCleaningTestAgents)}
          title="Safely scan and clean up test agents created by automated test suites"
        >
          🧹 {isChecking ? "Scanning..." : "Clean Test Agents"}
        </button>
      </div>

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
            <div style={{ marginTop: "12px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
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
              <button
                className="btn-secondary"
                style={{ padding: "4px 10px", fontSize: "0.78rem" }}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedSettingAgentId(a.id);
                }}
              >
                ⚙️ Edit Settings
              </button>
              <button
                className="btn-secondary"
                style={{
                  padding: "4px 10px",
                  fontSize: "0.78rem",
                  color: "#b42318",
                  borderColor: "#fecdca",
                  backgroundColor: "#fef3f2",
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  setDeleteError(null);
                  setAgentToDelete(a);
                }}
              >
                🗑️ Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      {showCleanupModal && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(16, 24, 40, 0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: "16px",
          }}
        >
          <div
            style={{
              background: "#ffffff",
              borderRadius: "12px",
              padding: "24px",
              maxWidth: "480px",
              width: "100%",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)",
            }}
          >
            <h3 style={{ margin: "0 0 12px 0", fontSize: "1.1rem", color: "#101828" }}>
              {previewTestAgents.length === 0
                ? "No Test Agents Found"
                : `Clean Up ${previewTestAgents.length} Test Agent(s)`}
            </h3>
            {previewTestAgents.length === 0 ? (
              <p style={{ margin: "0 0 20px 0", fontSize: "0.88rem", color: "#475467", lineHeight: 1.5 }}>
                No agents with explicit test metadata (<code>is_test = true</code> or test project namespace) were found in the database. All your existing agents are safe production agents.
              </p>
            ) : (
              <>
                <p style={{ margin: "0 0 12px 0", fontSize: "0.88rem", color: "#475467", lineHeight: 1.5 }}>
                  The following agents were identified strictly by explicit test metadata. Production agents will <strong>never</strong> be deleted:
                </p>
                <div
                  style={{
                    maxHeight: "180px",
                    overflowY: "auto",
                    background: "#f9fafb",
                    borderRadius: "8px",
                    padding: "10px 14px",
                    marginBottom: "18px",
                    border: "1px solid #eaecf0",
                    fontSize: "0.82rem",
                  }}
                >
                  {previewTestAgents.map((t) => (
                    <div key={t.id} style={{ padding: "4px 0", borderBottom: "1px solid #f2f4f7" }}>
                      <strong>{t.name}</strong> <span style={{ color: "#667085" }}>({t.project_name || "test"})</span>
                    </div>
                  ))}
                </div>
              </>
            )}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setShowCleanupModal(false)}
                disabled={Boolean(isCleaningTestAgents)}
              >
                {previewTestAgents.length === 0 ? "Close" : "Cancel"}
              </button>
              {previewTestAgents.length > 0 && (
                <button
                  type="button"
                  style={{
                    background: "#d92d20",
                    color: "#fff",
                    border: "none",
                    borderRadius: "6px",
                    padding: "8px 14px",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                  onClick={() => void handleConfirmCleanup()}
                  disabled={Boolean(isCleaningTestAgents)}
                >
                  {isCleaningTestAgents ? "Deleting..." : "Delete Test Agents"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
