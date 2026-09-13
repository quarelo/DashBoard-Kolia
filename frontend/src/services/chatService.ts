import { apiRequest } from "../lib/api";
import { dashboardService } from "./dashboardService";
import type { ChatCitation } from "../types";

export interface ChatOption {
  analysisId: string;
  title: string;
}

export interface ChatAnswer {
  answer: string;
  citations: ChatCitation[];
  grounded: boolean;
  fallback_reason:
    | "insufficient_evidence"
    | "model_unavailable"
    | "unsupported_answer"
    | "unsafe_request"
    | null;
  // A conversa em que o turno ficou guardado; null se a gravação falhou.
  conversation_id: string | null;
}

type HistoryTurn = { role: "user" | "assistant"; content: string };

export interface StoredMessage {
  role: "user" | "assistant";
  content: string;
  grounded: boolean | null;
  fallback_reason: string | null;
  created_at: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export const fallbackMessages: Record<string, string> = {
  insufficient_evidence:
    "Não encontrei trechos suficientes nesta reunião para responder com segurança.",
  model_unavailable: "O modelo de IA está indisponível no momento. Tente novamente em instantes.",
  unsupported_answer: "Não consegui sustentar uma resposta com base na transcrição.",
  unsafe_request: "Não posso responder a esse pedido.",
};

export const chatService = {
  async listAnalyses(): Promise<ChatOption[]> {
    // O chat RAG exige a análise em DONE (embeddings prontos) — ver contrato da IA.
    const { items } = await dashboardService.list(0, 200);
    return items
      .filter((item) => item.status === "DONE")
      .map((item) => ({ analysisId: item.analysisId, title: item.title }));
  },

  // Uma reunião pode ter várias conversas, guardadas no servidor.
  async conversations(analysisId: string): Promise<ConversationSummary[]> {
    const { conversations } = await apiRequest<{ conversations: ConversationSummary[] }>(
      `/api/dashboard/meetings/${analysisId}/chat/conversations`,
    );
    return conversations;
  },

  async conversation(analysisId: string, conversationId: string): Promise<StoredMessage[]> {
    const { messages } = await apiRequest<{ messages: StoredMessage[] }>(
      `/api/dashboard/meetings/${analysisId}/chat/conversations/${conversationId}`,
    );
    return messages;
  },

  // Sem conversationId, a pergunta começa uma conversa nova; a resposta traz o id dela.
  async ask(
    analysisId: string,
    question: string,
    history: HistoryTurn[],
    conversationId: string | null,
  ): Promise<ChatAnswer> {
    // A IA só aceita histórico alternado começando em "user" e terminando em
    // "assistant"; mandamos os últimos pares completos.
    const trimmed = history.slice(-6);
    const start = trimmed.findIndex((turn) => turn.role === "user");
    const clean = start === -1 ? [] : trimmed.slice(start);
    while (clean.length && clean[clean.length - 1].role !== "assistant") clean.pop();

    return apiRequest<ChatAnswer>(`/api/dashboard/meetings/${analysisId}/chat`, {
      method: "POST",
      body: {
        question,
        history: clean,
        ...(conversationId ? { conversation_id: conversationId } : {}),
      },
    });
  },

  suggestedQuestions(): string[] {
    return [
      "Faça um resumo executivo desta reunião.",
      "Quais produtos e módulos foram discutidos?",
      "Há algum sinal de risco de perder o cliente?",
      "Quais são as próximas ações combinadas?",
      "O que ficou em aberto ao final da conversa?",
    ];
  },
};
