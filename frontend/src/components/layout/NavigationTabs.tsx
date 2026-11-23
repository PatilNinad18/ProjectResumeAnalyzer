import styles from "./NavigationTabs.module.css";

type Tab = "workflow" | "screening" | "chat" | "settings";
interface NavigationTabsProps { activeTab: Tab; onChange: (tab: Tab) => void; }

export default function NavigationTabs({ activeTab, onChange }: NavigationTabsProps) {
  return (
    <div className={`${styles.navigationTabs} sub-nav-wrap`}>
      <nav className="nav-tabs">
        <button className={`nav-btn ${activeTab === "workflow" ? "active" : ""}`} onClick={() => onChange("workflow")}><span>📋</span> Workflow</button>
        <button className={`nav-btn ${activeTab === "screening" ? "active" : ""}`} onClick={() => onChange("screening")}><span>🎯</span> Screening</button>
        <button className={`nav-btn ${activeTab === "chat" ? "active" : ""}`} onClick={() => onChange("chat")}><span>💬</span> Chat</button>
        <button className={`nav-btn ${activeTab === "settings" ? "active" : ""}`} onClick={() => onChange("settings")}><span>⚙️</span> Settings</button>
      </nav>
    </div>
  );
}
