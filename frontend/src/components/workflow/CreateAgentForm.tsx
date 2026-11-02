import type { WorkflowPageProps } from "./WorkflowPage";
import styles from "./CreateAgentForm.module.css";

type CreateAgentFormProps = Pick<
  WorkflowPageProps,
  | "isStep3Done"
  | "isStep4Done"
  | "createdAgentSuccess"
  | "agentNameInput"
  | "setAgentNameInput"
  | "isCreatingAgent"
  | "createAgentError"
  | "handleCreateAgent"
>;

export default function CreateAgentForm({
  isStep3Done,
  isStep4Done,
  createdAgentSuccess,
  agentNameInput,
  setAgentNameInput,
  isCreatingAgent,
  createAgentError,
  handleCreateAgent,
}: CreateAgentFormProps) {
  return (
    <>
      {isStep4Done ? (
        <div className={`${styles.createAgentForm} card`} style={{ borderColor: "#6366f1" }}>
          <h3 style={{ margin: "0 0 8px 0", fontSize: "1.1rem" }}>Step 5: Create JD Agent</h3>
          <p style={{ margin: "0 0 16px 0", fontSize: "0.88rem", color: "#667085" }}>
            Finalize your configuration to register this JD agent with the verified specification.
          </p>

          {createdAgentSuccess && <div className="alert-success">✓ {createdAgentSuccess}</div>}
          {createAgentError && <div className="alert-error">{createAgentError}</div>}

          <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
            <input
              type="text"
              className="input-text"
              style={{ flex: 1 }}
              placeholder="Agent Name (e.g. Senior Backend Screener)"
              value={agentNameInput}
              onChange={(e) => setAgentNameInput(e.target.value)}
            />
            <button className="btn-primary" onClick={handleCreateAgent} disabled={isCreatingAgent}>
              {isCreatingAgent ? "Launching..." : "✨ Launch the agent"}
            </button>
          </div>
        </div>
      ) : isStep3Done ? (
        <div className={`${styles.createAgentForm} card`} style={{ borderColor: "#e2e8f0", background: "#f8fafc", padding: "18px 20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{ fontSize: "1.1rem" }}>🔒</span>
            <div>
              <h4 style={{ margin: "0 0 2px 0", fontSize: "1rem", color: "#64748b" }}>
                Step 5: Create JD Agent (Gated)
              </h4>
              <p style={{ margin: 0, fontSize: "0.84rem", color: "#94a3b8" }}>
                Please resolve the ambiguity trade-offs in <strong>Step 4</strong> above to unlock JD Agent registration.
              </p>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
