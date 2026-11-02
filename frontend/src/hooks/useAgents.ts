import { useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import {
  analyzeJD,
  cleanupTestAgentsApi,
  createAgentApi,
  deleteAgentApi,
  getAgents,
  getJson,
  getMarkdown,
  pollUntilDone,
  uploadJD,
} from "@/lib/api";
import type { CompanyDetails, CreatedAgent, ProcessingStatus } from "@/lib/api";
import { statusConfig } from "@/lib/ui";

type Tab = "workflow" | "chat" | "settings";
type ChatHistories = Record<string, Array<{ id: string; sender: "user" | "assistant"; text: string }>>;

interface UseAgentsOptions {
  agents: CreatedAgent[];
  setAgents: Dispatch<SetStateAction<CreatedAgent[]>>;
  companyDetails: CompanyDetails;
  jobTitle: string;
  jdId: string | null;
  jdText: string;
  markdown: string | null;
  jsonData: Record<string, unknown> | null;
  specVersion: number;
  agentNameInput: string;
  setAgentNameInput: Dispatch<SetStateAction<string>>;
  setCreatedAgentSuccess: Dispatch<SetStateAction<string | null>>;
  setActiveTab: Dispatch<SetStateAction<Tab>>;
  selectedAgentId: string;
  setSelectedAgentId: Dispatch<SetStateAction<string>>;
  setChatHistories: Dispatch<SetStateAction<ChatHistories>>;
  setMarkdown: Dispatch<SetStateAction<string | null>>;
  setJsonData: Dispatch<SetStateAction<Record<string, unknown> | null>>;
  setJdId: Dispatch<SetStateAction<string | null>>;
  setJdText: Dispatch<SetStateAction<string>>;
}

export function useAgents(options: UseAgentsOptions) {
  const {
    agents,
    setAgents,
    companyDetails,
    jobTitle,
    jdId,
    jdText,
    markdown,
    jsonData,
    specVersion,
    agentNameInput,
    setAgentNameInput,
    setCreatedAgentSuccess,
    setActiveTab,
    selectedAgentId,
    setSelectedAgentId,
    setChatHistories,
    setMarkdown,
    setJsonData,
    setJdId,
    setJdText,
  } = options;

  const [agentToDelete, setAgentToDelete] = useState<CreatedAgent | null>(null);
  const [isDeletingAgent, setIsDeletingAgent] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteSuccessMsg, setDeleteSuccessMsg] = useState<string | null>(null);
  const [selectedSettingAgentId, setSelectedSettingAgentId] = useState<string | null>(null);
  const [editCompany, setEditCompany] = useState<CompanyDetails>({
    companyName: "",
    department: "",
    projectName: "",
  });
  const [editTitle, setEditTitle] = useState("");
  const [editJdText, setEditJdText] = useState("");
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [regenStatus, setRegenStatus] = useState<string | null>(null);
  const [regenSuccessMsg, setRegenSuccessMsg] = useState<string | null>(null);
  const regenAbortRef = useRef<AbortController | null>(null);
  const createAgentInFlightRef = useRef(false);
  const [isCreatingAgent, setIsCreatingAgent] = useState(false);
  const [createAgentError, setCreateAgentError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    getAgents()
      .then((response) => {
        if (mounted && Array.isArray(response) && response.length > 0) {
          setAgents((previous) => {
            const existingIds = new Set(previous.map((agent) => agent.id));
            const newAgents = response.filter((agent) => !existingIds.has(agent.id));
            return [...previous, ...newAgents];
          });
        }
      })
      .catch((error) => {
        console.warn("Could not load agents from backend:", error);
      });
    return () => {
      mounted = false;
    };
  }, [setAgents]);

  useEffect(() => () => regenAbortRef.current?.abort(), []);

  useEffect(() => {
    if (selectedSettingAgentId) {
      const target = agents.find((agent) => agent.id === selectedSettingAgentId);
      if (target) {
        setEditCompany({ ...target.companyDetails });
        setEditTitle(target.title);
        setEditJdText(target.jdText);
      }
    } else if (agents.length > 0) {
      setSelectedSettingAgentId(agents[0].id);
    }
  }, [selectedSettingAgentId, agents]);

  async function handleCreateAgent() {
    if (createAgentInFlightRef.current) return;
    if (!jdId) {
      setCreateAgentError("Analyze a job description before launching an agent.");
      return;
    }
    if (!markdown?.trim()) {
      setCreateAgentError("The generated specification is not available yet.");
      return;
    }

    createAgentInFlightRef.current = true;
    setIsCreatingAgent(true);
    setCreateAgentError(null);
    const name = agentNameInput.trim() || `${jobTitle || "JD"} Agent`;
    const stamp = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const newAgent: CreatedAgent = {
      id: `agent-${Date.now()}`,
      agentName: name,
      title: jobTitle,
      companyDetails: { ...companyDetails },
      jdId,
      jdText,
      markdown,
      jsonData: jsonData || {},
      specificationVersion: specVersion,
      status: "ACTIVE",
      createdAt: stamp,
      updatedAt: stamp,
    };

    try {
      const persisted = await createAgentApi(newAgent);
      setAgents((previous) => [persisted, ...previous.filter((agent) => agent.id !== persisted.id)]);
      setSelectedAgentId(persisted.id);
      setCreatedAgentSuccess(`Agent "${persisted.agentName}" successfully created!`);
      setAgentNameInput("");
      setActiveTab("chat");
    } catch (error) {
      setCreateAgentError((error as Error).message || "Could not launch the agent. Please try again.");
    } finally {
      createAgentInFlightRef.current = false;
      setIsCreatingAgent(false);
    }
  }

  async function handleDeleteAgent(agentId: string, cancelActive = true) {
    setIsDeletingAgent(true);
    setDeleteError(null);
    try {
      await deleteAgentApi(agentId, cancelActive);

      setAgents((previous) => {
        const next = previous.filter((agent) => agent.id !== agentId);
        if (selectedSettingAgentId === agentId) {
          setSelectedSettingAgentId(next.length > 0 ? next[0].id : null);
        }
        if (selectedAgentId === agentId) {
          setSelectedAgentId(next.length > 0 ? next[0].id : "current");
        }
        return next;
      });
      setChatHistories((previous) => {
        const next = { ...previous };
        delete next[agentId];
        return next;
      });

      setDeleteSuccessMsg("Agent successfully deleted. Job Description and specifications were preserved.");
      setTimeout(() => setDeleteSuccessMsg(null), 6000);
      setAgentToDelete(null);
    } catch (error) {
      console.error("Failed to delete agent:", error);
      setDeleteError((error as Error).message || "Failed to delete agent. Please try again.");
    } finally {
      setIsDeletingAgent(false);
    }
  }

  async function handleRegenerateAgentContext() {
    if (!selectedSettingAgentId || isRegenerating) return;
    const target = agents.find((agent) => agent.id === selectedSettingAgentId);
    if (!target) return;
    if (!editJdText.trim()) {
      alert("JD Text cannot be empty.");
      return;
    }

    regenAbortRef.current?.abort();
    const controller = new AbortController();
    regenAbortRef.current = controller;
    setIsRegenerating(true);
    setRegenStatus("Uploading updated JD...");
    setRegenSuccessMsg(null);

    try {
      const { jd_id: regeneratedJdId } = await uploadJD(
        editCompany.projectName || target.companyDetails.projectName || "updated-project",
        { text: editJdText },
        editTitle.trim() || target.title
      );
      setRegenStatus("Analyzing updated context...");
      await analyzeJD(regeneratedJdId);

      const final = await pollUntilDone(regeneratedJdId, {
        signal: controller.signal,
        onStatus: (status: ProcessingStatus) =>
          setRegenStatus(`Status: ${statusConfig[status]?.label || status}`),
      });
      if (final.status === "FAILED") {
        alert(`Regeneration failed: ${final.error_message || "Unknown error"}`);
        return;
      }

      const [markdownResult, jsonResult] = await Promise.all([
        getMarkdown(regeneratedJdId),
        getJson(regeneratedJdId),
      ]);
      setAgents((previous) =>
        previous.map((agent) =>
          agent.id === selectedSettingAgentId
            ? {
                ...agent,
                title: editTitle.trim() || agent.title,
                companyDetails: { ...editCompany },
                jdId: regeneratedJdId,
                jdText: editJdText,
                markdown: markdownResult.markdown,
                jsonData: jsonResult.json,
                specificationVersion:
                  markdownResult.specification_version || agent.specificationVersion + 1,
                updatedAt: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
              }
            : agent
        )
      );

      if (target.jdId === jdId) {
        setMarkdown(markdownResult.markdown);
        setJsonData(jsonResult.json);
        setJdId(regeneratedJdId);
        setJdText(editJdText);
      }
      setRegenSuccessMsg(
        `Successfully regenerated context! Agent re-pointed to Specification v${markdownResult.specification_version}`
      );
    } catch (error) {
      if ((error as Error)?.name !== "AbortError") {
        alert(`Regeneration failed: ${(error as Error).message}`);
      }
    } finally {
      setIsRegenerating(false);
      setRegenStatus(null);
    }
  }

  const [isCleaningTestAgents, setIsCleaningTestAgents] = useState(false);

  async function handleCleanupTestAgents(dryRun: boolean = false) {
    setIsCleaningTestAgents(true);
    try {
      const result = await cleanupTestAgentsApi(dryRun);
      if (!dryRun && result.deleted_agent_ids && result.deleted_agent_ids.length > 0) {
        const deletedSet = new Set(result.deleted_agent_ids);
        setAgents((previous) => previous.filter((agent) => !deletedSet.has(agent.id)));
        setChatHistories((previous) => {
          const next = { ...previous };
          for (const id of result.deleted_agent_ids!) {
            delete next[id];
          }
          return next;
        });
        setDeleteSuccessMsg(`Safely cleaned up ${result.deleted_count ?? result.deleted_agent_ids.length} test agent(s).`);
        setTimeout(() => setDeleteSuccessMsg(null), 6000);
      }
      return result;
    } finally {
      setIsCleaningTestAgents(false);
    }
  }

  return {
    handleCleanupTestAgents,
    isCleaningTestAgents,
    agentToDelete,
    setAgentToDelete,
    isDeletingAgent,
    deleteError,
    setDeleteError,
    deleteSuccessMsg,
    selectedSettingAgentId,
    setSelectedSettingAgentId,
    editCompany,
    setEditCompany,
    editTitle,
    setEditTitle,
    editJdText,
    setEditJdText,
    isRegenerating,
    regenStatus,
    regenSuccessMsg,
    isCreatingAgent,
    createAgentError,
    handleCreateAgent,
    handleDeleteAgent,
    handleRegenerateAgentContext,
  };
}
