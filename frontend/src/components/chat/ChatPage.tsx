import React from "react";
import ReactMarkdown from "react-markdown";
import { API_BASE, TERMINAL_STATUSES } from "@/lib/api";
import type { CompanyDetails, CreatedAgent } from "@/lib/api";
import styles from "./ChatPage.module.css";

interface ChatPageProps {
  activeAgentForChat: CreatedAgent | undefined;
  companyDetails: CompanyDetails;
  selectedAgentId: string;
  setSelectedAgentId: React.Dispatch<React.SetStateAction<string>>;
  markdown: string | null;
  agents: CreatedAgent[];
  handleClearChatHistory: () => void;
  setActiveTab: React.Dispatch<React.SetStateAction<"workflow" | "chat" | "settings">>;
  hasReadyContext: boolean;
  currentChatMessages: { id: string; sender: "user" | "assistant"; text: string; }[];
  isChatLoading: boolean;
  handleSendChatMessage: (textToSend?: string) => Promise<void>;
  chatInput: string;
  setChatInput: React.Dispatch<React.SetStateAction<string>>;
}

export default function ChatPage({
    activeAgentForChat,
    companyDetails,
    selectedAgentId,
    setSelectedAgentId,
    markdown,
    agents,
    handleClearChatHistory,
    setActiveTab,
    hasReadyContext,
    currentChatMessages,
    isChatLoading,
    handleSendChatMessage,
    chatInput,
    setChatInput,
}: ChatPageProps) {
  return (
    <div className={`${styles.chatPage} chat-container`}>
              {/* Dark Chat Header */}
              <div className="chat-topbar">
                <div style={{ display: "flex", alignItems: "center", gap: "12px", minWidth: 0 }}>
                  <span style={{ fontSize: "1.3rem" }}>✨</span>
                  <div style={{ minWidth: 0 }}>
                    <h4 style={{ margin: 0, fontSize: "1rem", color: "#fff", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {activeAgentForChat ? activeAgentForChat.agentName : "Ask Anything about JD"}
                    </h4>
                    <span style={{ fontSize: "0.76rem", color: "rgba(255,255,255,0.6)" }}>
                      {activeAgentForChat
                        ? `${activeAgentForChat.companyDetails.companyName} • Spec v${activeAgentForChat.specificationVersion}`
                        : "Scans converted .md context to answer questions"}
                    </span>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <select
                    className="select select-on-dark"
                    style={{ width: "auto", minWidth: "180px" }}
                    value={selectedAgentId}
                    onChange={(e) => setSelectedAgentId(e.target.value)}
                  >
                    {markdown && <option value="current">Current Active JD Context</option>}
                    {agents.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.agentName} ({a.companyDetails.companyName})
                      </option>
                    ))}
                    {!markdown && agents.length === 0 && <option value="none">No Agent Created Yet</option>}
                  </select>
                  <button className="btn-ghost-dark" onClick={handleClearChatHistory}>
                    Clear History
                  </button>
                  <button className="chat-close-btn" onClick={() => setActiveTab("workflow")} title="Close">
                    ✕
                  </button>
                </div>
              </div>

              {/* Context Status */}
              <div className="context-status-row">
                <span>Context Status:</span>
                {hasReadyContext ? (
                  <span className="context-status-badge ready">✓ Markdown Ready</span>
                ) : (
                  <span className="context-status-badge pending">○ Pending Analysis</span>
                )}
              </div>

              {/* Message Thread */}
              <div className="chat-messages">
                {currentChatMessages.map((msg) => (
                  <div key={msg.id} className={`message-bubble ${msg.sender === "user" ? "message-user" : "message-assistant"}`}>
                    <ReactMarkdown>{msg.text}</ReactMarkdown>
                  </div>
                ))}
                {isChatLoading && (
                  <div className="message-bubble message-assistant" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span className="spinner"></span> Generating response...
                  </div>
                )}
              </div>

              {/* Suggested Questions */}
              <div className="prompt-chips">
                <button className="chip" onClick={() => handleSendChatMessage("What technical skills and tools are required?")}>
                  Technical Skills
                </button>
                <button className="chip" onClick={() => handleSendChatMessage("What is the required experience level?")}>
                  Experience Level
                </button>
                <button className="chip" onClick={() => handleSendChatMessage("What is the remote work policy for this role?")}>
                  Remote Policy
                </button>
                <button className="chip" onClick={() => handleSendChatMessage("What responsibilities are outlined?")}>
                  Responsibilities
                </button>
              </div>

              {/* Input Bar */}
              <div className="chat-input-bar">
                <input
                  type="text"
                  className="input-text"
                  style={{ flex: 1 }}
                  placeholder="Ask anything about the JD..."
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSendChatMessage()}
                />
                <button className="btn-primary" onClick={() => handleSendChatMessage()} disabled={isChatLoading || !chatInput.trim()}>
                  Send
                </button>
              </div>
            </div>
  );
}
