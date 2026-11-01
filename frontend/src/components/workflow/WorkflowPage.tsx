import React from "react";
import ReactMarkdown from "react-markdown";
import type { ClarificationsResponse, ProcessingStatus, CompanyDetails, CreatedAgent, ChatTurn, ContextComparisonResponse, RequirementDiffItem, AmbiguityItem, JDContextType, BatchTask } from "@/lib/api";
import { statusConfig, formatElapsed } from "@/lib/ui";
import styles from "./WorkflowPage.module.css";
import WorkflowStepper from "./WorkflowStepper";
import CompanyDetailsForm from "./CompanyDetailsForm";
import JDInputSection from "./JDInputSection";
import SpecificationViewer from "./SpecificationViewer";
import ClarificationPanel from "./ClarificationPanel";
import CreateAgentForm from "./CreateAgentForm";
import type { useJDBatch } from "@/hooks/useJDBatch";

export interface WorkflowPageProps {
  batchState: ReturnType<typeof useJDBatch>;
  handleLaunchBatchAgent: (agentName: string, task: BatchTask, markdown: string) => Promise<void>;
  isStep1Done: boolean;
  isStep2Done: boolean;
  currentStep: number;
  isStep3Done: boolean;
  isStep4Done: boolean;
  isStep5Done: boolean;
  handleSaveCompanyDetails: (e: React.FormEvent) => void;
  companyDetails: CompanyDetails;
  setCompanyDetails: React.Dispatch<React.SetStateAction<CompanyDetails>>;
  status: ProcessingStatus | null;
  agents: CreatedAgent[];
  handleResetForNewJD: () => void;
  jobTitle: string;
  setJobTitle: React.Dispatch<React.SetStateAction<string>>;
  handleFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  jdText: string;
  setJdText: React.Dispatch<React.SetStateAction<string>>;
  setSelectedFile: React.Dispatch<React.SetStateAction<File | null>>;
  selectedFile: File | null;
  analysisProgress: { percent: number; stageLabel: string; };
  nowTs: number;
  analysisStartedAt: number | null;
  handleCancelAnalysis: () => Promise<void>;
  analysisSuccessMsg: string | null;
  setAnalysisSuccessMsg: React.Dispatch<React.SetStateAction<string | null>>;
  error: string | null;
  handleAnalyseJD: () => Promise<void>;
  setError: React.Dispatch<React.SetStateAction<string | null>>;
  markdown: string | null;
  step4Ref: React.MutableRefObject<HTMLDivElement | null>;
  specVersion: number;
  contextTab: "markdown" | "json" | "compare";
  setContextTab: React.Dispatch<React.SetStateAction<"markdown" | "json" | "compare">>;
  isEnrichedView: boolean;
  fetchComparison: (base?: JDContextType, target?: JDContextType, targetJdId?: string) => Promise<void>;
  comparisonBaseContext: JDContextType;
  comparisonTargetContext: JDContextType;
  isDiffActive: boolean;
  setShowDiffHighlights: React.Dispatch<React.SetStateAction<boolean>>;
  showDiffHighlights: boolean;
  diffChangedCount: number;
  handleToggleEnrichment: (enable: boolean) => Promise<void>;
  downloadFile: (filename: string, content: string, mime: string) => void;
  jsonData: Record<string, unknown> | null;
  setComparisonBaseContext: React.Dispatch<React.SetStateAction<JDContextType>>;
  setComparisonTargetContext: React.Dispatch<React.SetStateAction<JDContextType>>;
  comparisonData: ContextComparisonResponse | null;
  isLoadingComparison: boolean;
  comparisonFilter: "all" | "added" | "modified" | "removed" | "unchanged";
  setComparisonFilter: React.Dispatch<React.SetStateAction<"all" | "added" | "modified" | "removed" | "unchanged">>;
  comparisonViewMode: "unified" | "side_by_side";
  setComparisonViewMode: React.Dispatch<React.SetStateAction<"unified" | "side_by_side">>;
  setMarkdownDiff: React.Dispatch<React.SetStateAction<{ text: string; changed: boolean; }[] | null>>;
  markdownDiff: { text: string; changed: boolean; }[] | null;
  clarificationsData: ClarificationsResponse | null;
  allClarificationItems: { key: string; topic: string; questionText: string; rationale?: string; category?: string; priority?: string; structuredOptions: Array<{ label: string; description: string; }>; isResolved: boolean; currentValue: string; }[];
  setClarificationViewMode: React.Dispatch<React.SetStateAction<"all" | "wizard">>;
  clarificationViewMode: "all" | "wizard";
  isResolvingClarifications: boolean;
  resolveProgress: { percent: number; stageLabel: string; };
  handleCancelResolve: () => Promise<void>;
  resolveSuccessMsg: string | null;
  setResolveSuccessMsg: React.Dispatch<React.SetStateAction<string | null>>;
  resolveError: string | null;
  handleResolveClarifications: () => Promise<void>;
  setResolveError: React.Dispatch<React.SetStateAction<string | null>>;
  activeClarificationIndex: number;
  setActiveClarificationIndex: React.Dispatch<React.SetStateAction<number>>;
  setClarificationAnswers: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  createdAgentSuccess: string | null;
  agentNameInput: string;
  setAgentNameInput: React.Dispatch<React.SetStateAction<string>>;
  isCreatingAgent: boolean;
  createAgentError: string | null;
  handleCreateAgent: () => Promise<void>;
}

export default function WorkflowPage({
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
}: WorkflowPageProps) {
  const sharedProps = {
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
  return (
    <div className={styles.workflowPage}>
              {/* Stepper Progress Indicator */}
              <WorkflowStepper {...sharedProps} />

              {/* Step 1: Company Details */}
              <CompanyDetailsForm {...sharedProps} />

              {/* Step 2 & 3: Enter / Upload JD & Analyse */}
              <JDInputSection {...sharedProps} batchState={batchState} />

              {/* Step 4: View / Download JD Context */}
              <SpecificationViewer {...sharedProps} />

                            {/* Ambiguities & Clarifications Requiring TA Input */}
              <ClarificationPanel {...sharedProps} />
{/* Step 5: Create Agent */}
              <CreateAgentForm {...sharedProps} />
            </div>
  );
}
