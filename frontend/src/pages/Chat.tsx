import { useState, useRef, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { Send, Loader2, User, Plus, ChevronDown, CalendarDays, MessagesSquare } from "lucide-react";
import {
  chatService, fallbackMessages,
  type ChatOption, type ConversationSummary, type StoredMessage,
} from "../services/chatService";
import { ApiError } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import { PageError, PageLoader, EmptyState } from "../components/ui/PageState";
import type { ChatMessage } from "../types";
import { cn } from "../lib/utils";
import { KoliaLogo } from "../components/ui/KoliaLogo";

let msgSeq = 0;
const nextId = (prefix: string) => `${prefix}-${++msgSeq}`;

function renderMarkdown(raw: string): string {
  return raw
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/^[•-] (.+)$/gm, '<li class="ml-4 list-disc text-ink-secondary text-sm">$1</li>')
    .replace(/\n\n/g, '<div class="h-2"></div>')
    .replace(/\n/g, "<br/>");
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const time = new Date(msg.timestamp).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return (
    <div className={cn("flex gap-3 max-w-3xl group", isUser ? "ml-auto flex-row-reverse" : "")}>
      <div className={cn(
        "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center mt-0.5 ring-2",
        isUser ? "gradient-brand ring-brand/20" : "bg-[#111827] ring-white",
      )}>
        {isUser ? <User size={14} className="text-white" /> : <KoliaLogo variant="icon" height={16} />}
      </div>
      <div className={cn(
        "flex-1 rounded-2xl px-4 py-3 text-sm leading-relaxed",
        isUser ? "gradient-brand text-white rounded-tr-sm shadow-brand-sm" : "bg-white border border-surface-border text-ink rounded-tl-sm shadow-card",
      )}>
        {isUser ? (
          <p className="whitespace-pre-wrap">{msg.content}</p>
        ) : (
          <div className="[&_strong]:font-semibold [&_strong]:text-ink [&_li]:my-0.5" dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
        )}

        {!isUser && msg.citations && msg.citations.length > 0 && (
          <div className="mt-3 pt-3 border-t border-surface-border space-y-2">
            <p className="text-[10px] font-bold text-ink-muted uppercase tracking-widest">
              Trechos citados
            </p>
            {msg.citations.map((c) => (
              <blockquote key={c.chunk_id} className="border-l-[3px] border-brand/40 bg-brand/5 rounded-r-lg px-3 py-1.5">
                <p className="text-xs text-ink-secondary italic leading-relaxed">"{c.excerpt}"</p>
                <p className="text-[10px] text-ink-muted mt-1">
                  trecho #{c.chunk_index} · relevância {Math.round(c.similarity * 100)}%
                </p>
              </blockquote>
            ))}
          </div>
        )}

        <p className={cn("text-[10px] mt-2 opacity-60", isUser ? "text-white" : "text-ink-muted")}>{time}</p>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-3">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[#111827] ring-2 ring-white flex items-center justify-center">
        <KoliaLogo variant="icon" height={16} />
      </div>
      <div className="bg-white border border-surface-border rounded-2xl rounded-tl-sm shadow-card px-4 py-3 flex items-center gap-2.5">
        <Loader2 size={13} className="text-brand animate-spin" />
        <span className="text-sm text-ink-secondary">Consultando a transcrição...</span>
      </div>
    </div>
  );
}

function AnalysisSelector({ options, value, onChange, disabled }: {
  options: ChatOption[]; value: string | null; onChange: (id: string) => void; disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const current = options.find((o) => o.analysisId === value);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        className="flex items-center gap-2 px-3.5 py-2 bg-white border border-surface-border rounded-xl text-sm font-medium text-ink hover:border-brand/40 transition-all max-w-md disabled:opacity-60"
      >
        <CalendarDays size={13} className="text-brand flex-shrink-0" />
        <span className="truncate">{current?.title ?? "Selecione uma reunião"}</span>
        <ChevronDown size={13} className={cn("text-ink-muted flex-shrink-0 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute top-full left-0 mt-2 w-[420px] max-w-[80vw] bg-white border border-surface-border rounded-xl shadow-card-lg z-20 max-h-72 overflow-y-auto scrollbar-thin">
            {options.map((o) => (
              <button
                key={o.analysisId}
                onClick={() => { onChange(o.analysisId); setOpen(false); }}
                className={cn("w-full flex items-center gap-2.5 px-4 py-2.5 text-sm hover:bg-brand/5 transition-colors text-left", o.analysisId === value && "bg-brand/5")}
              >
                <CalendarDays size={13} className="text-brand flex-shrink-0" />
                <span className="text-ink-secondary truncate flex-1">{o.title}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

// As conversas desta reunião, como a barra lateral do claude.ai: a atual em
// destaque, as anteriores guardadas à parte e reabríveis.
function ConversationList({ conversations, activeId, disabled, onSelect }: {
  conversations: ConversationSummary[];
  activeId: string | null;
  disabled: boolean;
  onSelect: (conversation: ConversationSummary) => void;
}) {
  return (
    <aside className="card flex flex-col md:w-64 flex-shrink-0 max-h-44 md:max-h-none overflow-hidden">
      <p className="px-4 pt-3 pb-2 text-[10px] font-bold text-ink-muted uppercase tracking-widest flex items-center gap-1.5">
        <MessagesSquare size={12} /> Conversas desta reunião
      </p>
      <div className="flex-1 overflow-y-auto scrollbar-thin px-2 pb-2 space-y-1">
        {activeId === null && (
          <div className="rounded-lg px-3 py-2 bg-brand/10 text-brand">
            <span className="block text-sm font-medium truncate">Nova conversa</span>
            <span className="block text-[10px] opacity-70 mt-0.5">ainda sem perguntas</span>
          </div>
        )}
        {conversations.length === 0 && activeId !== null && (
          <p className="text-xs text-ink-muted px-3 py-2">Nenhuma conversa guardada.</p>
        )}
        {conversations.map((c) => (
          <button
            key={c.id}
            onClick={() => onSelect(c)}
            disabled={disabled}
            className={cn(
              "w-full text-left rounded-lg px-3 py-2 transition-colors disabled:opacity-60",
              c.id === activeId ? "bg-brand/10 text-brand" : "text-ink-secondary hover:bg-surface",
            )}
          >
            <span className="block text-sm font-medium truncate">{c.title}</span>
            <span className="block text-[10px] text-ink-muted mt-0.5">{formatWhen(c.updated_at)}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}

function greeting(title: string): ChatMessage {
  return {
    id: "init",
    role: "assistant",
    content: `Contexto: **${title}**.\n\nPergunte sobre riscos, oportunidades, produtos, próximas ações ou o que ficou em aberto nesta reunião.`,
    timestamp: new Date().toISOString(),
  };
}

function toMessages(title: string, stored: StoredMessage[]): ChatMessage[] {
  return [
    greeting(title),
    ...stored.map((m) => ({
      id: nextId(m.role === "user" ? "u" : "a"),
      role: m.role,
      content: m.content,
      timestamp: m.created_at,
      grounded: m.grounded ?? undefined,
    })),
  ];
}

export function Chat() {
  const [searchParams] = useSearchParams();
  const { data: options, loading, error, reload } = useAsync(() => chatService.listAnalyses(), []);

  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  // null = conversa nova, que só passa a existir no servidor na primeira pergunta.
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  // Trocar de reunião ou de conversa invalida as respostas que ainda estão a caminho.
  const viewRef = useRef(0);

  const titleOf = (id: string) => options?.find((o) => o.analysisId === id)?.title ?? "";

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  async function openAnalysis(id: string, title: string) {
    const view = ++viewRef.current;
    setAnalysisId(id);
    setConversationId(null);
    setConversations([]);
    setMessages([greeting(title)]);
    setInput("");
    try {
      const list = await chatService.conversations(id);
      if (view !== viewRef.current) return;
      setConversations(list);
      // Reabre a mais recente: quem volta à reunião continua de onde parou.
      if (list.length > 0) await openConversation(id, title, list[0].id, view);
    } catch {
      // Lista indisponível não pode impedir uma pergunta nova.
    }
  }

  async function openConversation(id: string, title: string, target: string, view = ++viewRef.current) {
    setConversationId(target);
    setMessages([greeting(title)]);
    try {
      const stored = await chatService.conversation(id, target);
      if (view !== viewRef.current) return;
      setMessages(toMessages(title, stored));
    } catch {
      // Conversa antiga indisponível: a tela fica pronta para continuar mesmo assim.
    }
  }

  async function refreshConversations(id: string, view: number) {
    try {
      const list = await chatService.conversations(id);
      if (view === viewRef.current) setConversations(list);
    } catch {
      // A lista volta na próxima troca de conversa.
    }
  }

  // Começa outra conversa na mesma reunião; as anteriores continuam na lista.
  function startNewConversation() {
    if (!analysisId) return;
    ++viewRef.current;
    setConversationId(null);
    setMessages([greeting(titleOf(analysisId))]);
    setInput("");
  }

  function switchAnalysis(id: string) {
    const opt = options?.find((o) => o.analysisId === id);
    if (opt) void openAnalysis(id, opt.title);
  }

  // Escolha inicial: ?analysisId= ou a primeira da lista.
  useEffect(() => {
    if (!options || options.length === 0 || analysisId) return;
    const requested = searchParams.get("analysisId");
    const pick = options.find((o) => o.analysisId === requested) ?? options[0];
    // Mesma exceção de antes: a primeira reunião só é conhecida depois que a lista chega.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void openAnalysis(pick.analysisId, pick.title);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options, analysisId, searchParams]);

  async function send(content: string) {
    const text = content.trim();
    if (!text || busy || !analysisId) return;
    const view = viewRef.current;
    const currentAnalysis = analysisId;
    const userMsg: ChatMessage = { id: nextId("u"), role: "user", content: text, timestamp: new Date().toISOString() };
    const history = messages.filter((m) => m.id !== "init").map((m) => ({ role: m.role, content: m.content }));
    setMessages((p) => [...p, userMsg]);
    setInput("");
    setBusy(true);
    try {
      const res = await chatService.ask(currentAnalysis, text, history, conversationId);
      if (view !== viewRef.current) return;
      const note = res.fallback_reason && res.answer
        ? `\n\n_${fallbackMessages[res.fallback_reason] ?? ""}_`
        : "";
      setMessages((p) => [...p, {
        id: nextId("a"), role: "assistant",
        content: (res.answer || fallbackMessages[res.fallback_reason ?? ""] || "Sem resposta.") + note,
        timestamp: new Date().toISOString(),
        citations: res.citations,
        grounded: res.grounded,
      }]);
      if (res.conversation_id) {
        setConversationId(res.conversation_id);
        void refreshConversations(currentAnalysis, view);
      }
    } catch (err) {
      if (view !== viewRef.current) return;
      const message = err instanceof ApiError
        ? (err.status === 409
            ? "A indexação desta reunião ainda não terminou. Tente novamente em instantes."
            : err.message)
        : "Não consegui falar com a IA agora. Tente novamente em instantes.";
      setMessages((p) => [...p, {
        id: nextId("a"), role: "assistant", content: message, timestamp: new Date().toISOString(),
      }]);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <PageLoader label="Carregando reuniões..." />;
  if (error) return <PageError message={error} onRetry={reload} />;
  if (!options || options.length === 0) {
    return <EmptyState title="Nenhuma reunião pronta para conversa" hint="O chat fica disponível quando uma análise conclui a indexação (RAG)." />;
  }

  const suggested = chatService.suggestedQuestions();
  const showSuggestions = messages.length <= 1 && !busy;

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem-3rem)] max-h-[820px] animate-fade-in">
      <div className="flex items-start justify-between mb-3 gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-extrabold text-ink">Chat IA</h1>
          <p className="text-sm text-ink-secondary mt-0.5">Converse com base em uma transcrição analisada</p>
        </div>
        <button
          onClick={startNewConversation}
          disabled={busy || conversationId === null}
          className="btn-ghost gap-1.5 py-2 text-xs disabled:opacity-50"
        >
          <Plus size={12} /> Nova conversa
        </button>
      </div>

      <div className="card px-4 py-3 mb-3 flex flex-wrap items-center gap-3">
        <span className="text-xs font-semibold text-ink-secondary flex-shrink-0">Reunião:</span>
        <AnalysisSelector options={options} value={analysisId} onChange={switchAnalysis} disabled={busy} />
      </div>

      <div className="flex-1 min-h-0 flex flex-col md:flex-row gap-3">
        <ConversationList
          conversations={conversations}
          activeId={conversationId}
          disabled={busy}
          onSelect={(c) => analysisId && void openConversation(analysisId, titleOf(analysisId), c.id)}
        />

        <div className="flex-1 min-h-0 flex flex-col card overflow-hidden">
          <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4 scrollbar-thin bg-[#FAFAFA]">
            {messages.map((msg) => <MessageBubble key={msg.id} msg={msg} />)}
            {busy && <TypingIndicator />}
            <div ref={bottomRef} />
          </div>

          {showSuggestions && (
            <div className="px-5 py-3 border-t border-surface-border bg-white">
              <p className="text-[10px] font-bold text-ink-muted uppercase tracking-widest mb-2">Sugestões</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {suggested.map((q) => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    className="text-left text-xs font-medium text-ink-secondary bg-surface hover:bg-brand/8 hover:text-brand border border-surface-border hover:border-brand/30 rounded-xl px-3.5 py-2.5 transition-all leading-snug"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="px-4 py-4 border-t border-surface-border bg-white">
            <p className="text-[10px] text-ink-muted text-left mb-2">
              O ChatBot pode cometer erros. Por isso, lembre-se de conferir informações relevantes.
            </p>
            <div className="flex gap-3 items-end">
              <div className="flex-1 bg-surface border border-surface-border rounded-2xl focus-within:border-brand/50 focus-within:ring-2 focus-within:ring-brand/20 transition-all">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
                  placeholder="Pergunte sobre esta reunião..."
                  rows={1}
                  disabled={busy}
                  className="w-full px-4 py-3 text-sm text-ink bg-transparent resize-none focus:outline-none placeholder-ink-muted scrollbar-thin"
                  style={{ minHeight: 44, maxHeight: 140 }}
                />
              </div>
              <button
                onClick={() => send(input)}
                disabled={!input.trim() || busy}
                className={cn(
                  "flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-all",
                  input.trim() && !busy ? "gradient-brand text-white shadow-brand" : "bg-surface text-ink-disabled cursor-not-allowed",
                )}
              >
                <Send size={15} />
              </button>
            </div>
            <p className="text-[10px] text-ink-muted mt-2 text-center">Enter envia · Shift+Enter nova linha</p>
          </div>
        </div>
      </div>
    </div>
  );
}
