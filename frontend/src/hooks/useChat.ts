import { useEffect, useState } from "react";
import { askJDChatbot } from "@/lib/api";
import type { ChatTurn, CreatedAgent } from "@/lib/api";

interface UseChatOptions {
  agents: CreatedAgent[];
  jdId: string | null;
  markdown: string | null;
  jdText: string;
}

interface ChatMessage {
  id: string;
  sender: "user" | "assistant";
  text: string;
}

const welcomeMessage: ChatMessage = {
  id: "welcome",
  sender: "assistant",
  text: "Hello! I am your JD AI Assistant. I answer questions about this job description: requirements, technical skills, experience, work policy, and responsibilities. Ask me anything!",
};

export function useChat({ agents, jdId, markdown, jdText }: UseChatOptions) {
  const [selectedAgentId, setSelectedAgentId] = useState("current");
  const [chatHistories, setChatHistories] = useState<Record<string, ChatMessage[]>>({});
  const [chatInput, setChatInput] = useState("");
  const [isChatLoading, setIsChatLoading] = useState(false);

  const currentChatMessages = chatHistories[selectedAgentId] || [welcomeMessage];
  const activeAgentForChat = agents.find((agent) => agent.id === selectedAgentId);

  useEffect(() => {
    if (selectedAgentId === "current" && !markdown && agents.length > 0) {
      setSelectedAgentId(agents[0].id);
    }
  }, [selectedAgentId, markdown, agents]);

  async function handleSendChatMessage(textToSend?: string) {
    const question = (textToSend ?? chatInput).trim();
    if (!question || isChatLoading) return;

    const targetKey = selectedAgentId;
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      sender: "user",
      text: question,
    };
    const history: ChatTurn[] = (chatHistories[targetKey] || [])
      .filter((message) => message.id !== "welcome" && !message.text.startsWith("⚠️"))
      .slice(-6)
      .map((message) => ({ role: message.sender, content: message.text.slice(0, 1000) }));

    setChatHistories((previous) => ({
      ...previous,
      [targetKey]: [...(previous[targetKey] || [welcomeMessage]), userMessage],
    }));

    if (!textToSend) setChatInput("");
    setIsChatLoading(true);

    const pushAssistant = (text: string) =>
      setChatHistories((previous) => ({
        ...previous,
        [targetKey]: [
          ...(previous[targetKey] || []),
          { id: (Date.now() + 1).toString(), sender: "assistant", text },
        ],
      }));

    try {
      let targetJdId: string | null = null;
      let contextToUse: string | null = null;

      if (targetKey !== "current") {
        const agent = agents.find((item) => item.id === targetKey);
        if (agent) {
          targetJdId = agent.jdId;
          contextToUse = agent.markdown;
        }
      } else {
        targetJdId = jdId;
        contextToUse = markdown || (jdText.trim() ? `# Job Description\n\n${jdText}` : null);
      }

      if (!targetJdId && !contextToUse) {
        pushAssistant("⚠️ **No JD context yet.** Analyse a job description (or create an agent) first, then ask me about it.");
        return;
      }

      const { answer } = await askJDChatbot(targetJdId, question, contextToUse, history);
      pushAssistant(answer);
    } catch (error) {
      pushAssistant(`⚠️ **Error:** ${(error as Error).message}`);
    } finally {
      setIsChatLoading(false);
    }
  }

  function handleClearChatHistory() {
    setChatHistories((previous) => ({
      ...previous,
      [selectedAgentId]: [],
    }));
  }

  return {
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
  };
}
