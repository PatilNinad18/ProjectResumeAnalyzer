import styles from "./AppHeader.module.css";

interface AppHeaderProps { onNavigate: () => void; }

export default function AppHeader({ onNavigate }: AppHeaderProps) {
  return (
    <header className={`${styles.appHeader} topbar`}>
      <div className="topbar-left"><span className="user-avatar">N</span></div>
      <div className="topbar-center"><span className="ai-icon-box">AI</span><div className="brand-text"><span className="brand-title">JD Understanding Agent</span><span className="brand-subtitle">Intelligent job description analysis</span></div></div>
      <div className="topbar-right"><button className="context-btn" onClick={onNavigate}>AI Evaluation Context</button></div>
    </header>
  );
}
