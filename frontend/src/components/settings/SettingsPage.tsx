import React from "react";
import type { CompanyDetails, CreatedAgent } from "@/lib/api";
import styles from "./SettingsPage.module.css";
import AgentList from "./AgentList";
import AgentEditor from "./AgentEditor";

export interface SettingsPageProps {
  deleteSuccessMsg: string | null;
  agents: CreatedAgent[];
  setActiveTab: React.Dispatch<React.SetStateAction<"workflow" | "chat" | "settings">>;
  selectedSettingAgentId: string | null;
  setSelectedSettingAgentId: React.Dispatch<React.SetStateAction<string | null>>;
  setSelectedAgentId: React.Dispatch<React.SetStateAction<string>>;
  setDeleteError: React.Dispatch<React.SetStateAction<string | null>>;
  setAgentToDelete: React.Dispatch<React.SetStateAction<CreatedAgent | null>>;
  regenSuccessMsg: string | null;
  regenStatus: string | null;
  editTitle: string;
  setEditTitle: React.Dispatch<React.SetStateAction<string>>;
  editCompany: CompanyDetails;
  setEditCompany: React.Dispatch<React.SetStateAction<CompanyDetails>>;
  editJdText: string;
  setEditJdText: React.Dispatch<React.SetStateAction<string>>;
  handleRegenerateAgentContext: () => Promise<void>;
  isRegenerating: boolean;
}

export default function SettingsPage({
    deleteSuccessMsg,
    agents,
    setActiveTab,
    selectedSettingAgentId,
    setSelectedSettingAgentId,
    setSelectedAgentId,
    setDeleteError,
    setAgentToDelete,
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
}: SettingsPageProps) {
  const agentListProps = {
    agents,
    selectedSettingAgentId,
    setSelectedSettingAgentId,
    setSelectedAgentId,
    setActiveTab,
    setDeleteError,
    setAgentToDelete,
  };
  const agentEditorProps = {
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
  };
  return (
    <div className={styles.settingsPage}>
              <h2 style={{ marginTop: 0, marginBottom: "20px" }}>Agent Management & Context Regeneration</h2>

              {deleteSuccessMsg && (
                <div className="alert-success" style={{ marginBottom: "20px" }}>
                  ✓ {deleteSuccessMsg}
                </div>
              )}

              {agents.length === 0 ? (
                <div className="card" style={{ textAlign: "center", padding: "40px" }}>
                  <p style={{ color: "#667085", fontSize: "1rem", margin: "0 0 16px 0" }}>
                    No agents created yet. Complete the <strong>Linear Setup Workflow</strong> to create your first JD agent.
                  </p>
                  <button className="btn-primary" onClick={() => setActiveTab("workflow")}>
                    Go to Workflow Setup →
                  </button>
                </div>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: "24px" }}>
                  {/* Left Column: Created Agents List */}
                  <AgentList {...agentListProps} />

                  {/* Right Column: Settings & Context Regeneration Form */}
                  {selectedSettingAgentId && <AgentEditor {...agentEditorProps} />}
                </div>
              )}
            </div>
  );
}
