import React from "react";
import type { SettingsPageProps } from "./SettingsPage";
import styles from "./AgentList.module.css";

type AgentListProps = Pick<SettingsPageProps, "agents" | "selectedSettingAgentId" | "setSelectedSettingAgentId" | "setSelectedAgentId" | "setActiveTab" | "setDeleteError" | "setAgentToDelete">;

export default function AgentList({
    agents,
    selectedSettingAgentId,
    setSelectedSettingAgentId,
    setSelectedAgentId,
    setActiveTab,
    setDeleteError,
    setAgentToDelete,
}: AgentListProps) {
  return (
    <div className={styles.agentList}>
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
                  </div>
  );
}
