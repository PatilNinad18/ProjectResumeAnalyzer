"use client";

import { useState } from "react";
import AppHeader from "@/components/layout/AppHeader";
import NavigationTabs from "@/components/layout/NavigationTabs";
import WorkflowPage from "@/components/workflow/WorkflowPage";
import ChatPage from "@/components/chat/ChatPage";
import SettingsPage from "@/components/settings/SettingsPage";
import AgentDeleteDialog from "@/components/settings/AgentDeleteDialog";
import { useChat } from "@/hooks/useChat";
import { useJDWorkflow } from "@/hooks/useJDWorkflow";
import { useJDBatch } from "@/hooks/useJDBatch";
import { useAgents } from "@/hooks/useAgents";
import { createAgentApi, getJson } from "@/lib/api";
import type { CompanyDetails, CreatedAgent, BatchTask } from "@/lib/api";

export default function Home() {
  // Navigation
  const [activeTab, setActiveTab] = useState<"workflow" | "chat" | "settings">("workflow");

  const [agents, setAgents] = useState<CreatedAgent[]>([]);
  const [agentNameInput, setAgentNameInput] = useState("");
  const [createdAgentSuccess, setCreatedAgentSuccess] = useState<string | null>(null);
  const jdWorkflow = useJDWorkflow({
    agents,
    setCreatedAgentSuccess,
    setAgentNameInput,
  });
  const batchState = useJDBatch(jdWorkflow.companyDetails.projectName.trim() || "default-project");
  const {
    companyDetails, setCompanyDetails, isCompanySaved, jobTitle, setJobTitle,
    jdText, setJdText, jdId, setJdId, status, error, setError, markdown,
    setMarkdown, jsonData, setJsonData, specVersion, contextTab, setContextTab, isEnrichedView,
    analysisProgress, analysisSuccessMsg, setAnalysisSuccessMsg, resolveProgress,
    resolveError, setResolveError, comparisonData, isLoadingComparison,
    comparisonBaseContext, setComparisonBaseContext, comparisonTargetContext,
    setComparisonTargetContext, comparisonFilter, setComparisonFilter,
    comparisonViewMode, setComparisonViewMode, clarificationsData, clarificationAnswers,
    activeClarificationIndex, clarificationViewMode, isResolvingClarifications,
    resolveSuccessMsg, setResolveSuccessMsg,
    markdownDiff, setMarkdownDiff, showDiffHighlights, setShowDiffHighlights, diffChangedCount,
    step4Ref, selectedFile, setSelectedFile,
    analysisStartedAt, nowTs, allClarificationItems, isStep1Done, isStep2Done,
    isStep3Done, isStep4Done, isStep5Done, isDiffActive, currentStep,
    handleSaveCompanyDetails, fetchComparison, handleCancelAnalysis,
    handleCancelResolve, handleResetForNewJD, handleEnrichJD,
    handleToggleEnrichment, handleResolveClarifications, handleAnalyseJD,
    handleFileUpload, downloadFile,
    setClarificationViewMode, setActiveClarificationIndex, setClarificationAnswers,
  } = jdWorkflow;

  const {
    selectedAgentId,
    setSelectedAgentId,
    chatHistories,
    setChatHistories,
    chatInput,
    setChatInput,
    isChatLoading,
    currentChatMessages,
    activeAgentForChat,
    handleSendChatMessage,
    handleClearChatHistory,
  } = useChat({ agents, jdId, markdown, jdText });

  const agentManagement = useAgents({
    agents, setAgents, companyDetails, jobTitle, jdId, jdText, markdown, jsonData, specVersion,
    agentNameInput, setAgentNameInput, setCreatedAgentSuccess, setActiveTab,
    selectedAgentId, setSelectedAgentId, setChatHistories,
    setMarkdown, setJsonData, setJdId, setJdText,
  });
  const {
    agentToDelete, setAgentToDelete, isDeletingAgent, deleteError, setDeleteError,
    deleteSuccessMsg, selectedSettingAgentId, setSelectedSettingAgentId, editCompany,
    setEditCompany, editTitle, setEditTitle, editJdText, setEditJdText, isRegenerating,
    regenStatus, regenSuccessMsg, isCreatingAgent, createAgentError, handleCreateAgent, handleDeleteAgent,
    handleRegenerateAgentContext,
  } = agentManagement;

  async function handleLaunchBatchAgent(agentName: string, task: BatchTask, agentMarkdown: string) {
    const trimmedName = agentName.trim();
    if (!trimmedName) throw new Error("Enter an agent name before launching.");
    if (task.status !== "COMPLETED" || !agentMarkdown.trim()) {
      throw new Error("This job description must finish processing before its agent can be launched.");
    }

    const jsonResponse = await getJson(task.jd_id);
    const created = await createAgentApi({
      agentName: trimmedName,
      title: task.title,
      companyDetails: { ...companyDetails },
      jdId: task.jd_id,
      markdown: agentMarkdown,
      jsonData: jsonResponse.json,
      specificationVersion: jsonResponse.specification_version,
      status: "ACTIVE",
    });
    setAgents((previous) => [created, ...previous.filter((agent) => agent.id !== created.id)]);
    setSelectedAgentId(created.id);
    setActiveTab("chat");
  }

  const hasReadyContext = isStep3Done || Boolean(activeAgentForChat);

  const workflowPageProps = {
    batchState,
    handleLaunchBatchAgent,
    isStep1Done,
    isStep2Done,
    currentStep,
    isStep3Done,
    isStep4Done,
    isStep5Done,
    handleSaveCompanyDetails,
    companyDetails,
    setCompanyDetails,
    status,
    agents,
    handleResetForNewJD,
    jobTitle,
    setJobTitle,
    handleFileUpload,
    jdText,
    setJdText,
    setSelectedFile,
    selectedFile,
    analysisProgress,
    nowTs,
    analysisStartedAt,
    handleCancelAnalysis,
    analysisSuccessMsg,
    setAnalysisSuccessMsg,
    error,
    handleAnalyseJD,
    setError,
    markdown,
    step4Ref,
    specVersion,
    contextTab,
    setContextTab,
    isEnrichedView,
    fetchComparison,
    comparisonBaseContext,
    comparisonTargetContext,
    isDiffActive,
    setShowDiffHighlights,
    showDiffHighlights,
    diffChangedCount,
    handleToggleEnrichment,
    downloadFile,
    jsonData,
    setComparisonBaseContext,
    setComparisonTargetContext,
    comparisonData,
    isLoadingComparison,
    comparisonFilter,
    setComparisonFilter,
    comparisonViewMode,
    setComparisonViewMode,
    setMarkdownDiff,
    markdownDiff,
    clarificationsData,
    allClarificationItems,
    setClarificationViewMode,
    clarificationViewMode,
    isResolvingClarifications,
    resolveProgress,
    handleCancelResolve,
    resolveSuccessMsg,
    setResolveSuccessMsg,
    resolveError,
    handleResolveClarifications,
    setResolveError,
    activeClarificationIndex,
    setActiveClarificationIndex,
    setClarificationAnswers,
    createdAgentSuccess,
    agentNameInput,
    setAgentNameInput,
    isCreatingAgent,
    createAgentError,
    handleCreateAgent,
  };

  const chatPageProps = {
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
  };

  const settingsPageProps = {
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
  };

  const deleteDialogProps = {
    agentToDelete,
    isDeletingAgent,
    setAgentToDelete,
    jdId,
    deleteError,
    handleDeleteAgent,
  };

  return (
    <>

      <div className="app-container">
        {/* Top Navbar — avatar, Ask Anything pill, AI mark + title, evaluation context button */}
        <AppHeader onNavigate={() => setActiveTab("workflow")} />

        <NavigationTabs activeTab={activeTab} onChange={setActiveTab} />

        <main className="main-content">
          {/* ========================================================================= */}
          {/* TAB 1: LINEAR JD WORKFLOW (Company -> Upload -> Analyse -> View -> Agent)  */}
          {/* ========================================================================= */}
          {activeTab === "workflow" && <WorkflowPage {...workflowPageProps} />}

          {/* ========================================================================= */}
          {/* TAB 2: DEDICATED JD CHAT PAGE — styled as the "Ask Anything about JD" panel */}
          {/* ========================================================================= */}
          {activeTab === "chat" && <ChatPage {...chatPageProps} />}

          {/* ========================================================================= */}
          {/* TAB 3: AGENT SETTINGS & CONTEXT REGENERATION                              */}
          {/* ========================================================================= */}
          {activeTab === "settings" && <SettingsPage {...settingsPageProps} />}
          {/* Delete Confirmation Modal */}
          <AgentDeleteDialog {...deleteDialogProps} />
        </main>
      </div>
    </>
  );
}