import { useState, useRef, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { Send, Loader2, User, RotateCcw, ChevronDown, CalendarDays } from "lucide-react";
import { chatService, fallbackMessages, type ChatOption } from "../services/chatService";
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

function AnalysisSelector({ options, value, onChange }: {
  options: ChatOption[]; value: string | null; onChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const current = options.find((o) => o.analysisId === value);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 px-3.5 py-2 bg-white border border-surface-border rounded-xl text-sm font-medium text-ink hover:border-brand/40 transition-all max-w-md"
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

function greeting(title: string): ChatMessage {
  return {
    id: "init",
    role: "assistant",
    content: `Contexto: **${title}**.\n\nPergunte sobre riscos, oportunidades, produtos, próximas ações ou o que ficou em aberto nesta reunião.`,
    timestamp: new Date().toISOString(),
  };
}

export function Chat() {
  const [searchParams] = useSearchParams();
  const { data: options, loading, error, reload } = useAsync(() => chatService.listAnalyses(), []);

  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Escolha inicial: ?analysisId= ou a primeira da lista.
  useEffect(() => {
    if (!options || options.length === 0 || analysisId) return;
    const requested = searchParams.get("analysisId");
    const pick = options.find((o) => o.analysisId === requested) ?? options[0];
    /* eslint-disable react-hooks/set-state-in-effect */
    setAnalysisId(pick.analysisId);
    setMessages([greeting(pick.title)]);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [options, analysisId, searchParams]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  function switchAnalysis(id: string) {
    const opt = options?.find((o) => o.analysisId === id);
    setAnalysisId(id);
    setMessages(opt ? [greeting(opt.title)] : []);
    setInput("");
  }

  async function send(content: string) {
    const text = content.trim();
    if (!text || busy || !analysisId) return;
    const userMsg: ChatMessage = { id: nextId("u"), role: "user", content: text, timestamp: new Date().toISOString() };
    const history = messages.filter((m) => m.id !== "init").map((m) => ({ role: m.role, content: m.content }));
    setMessages((p) => [...p, userMsg]);
    setInput("");
    setBusy(true);
    try {
      const res = await chatService.ask(analysisId, text, history);
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
    } catch (err) {
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
          onClick={() => analysisId && switchAnalysis(analysisId)}
          className="btn-ghost gap-1.5 py-2 text-xs"
        >
          <RotateCcw size={12} /> Nova conversa
        </button>
      </div>

      <div className="card px-4 py-3 mb-3 flex flex-wrap items-center gap-3">
        <span className="text-xs font-semibold text-ink-secondary flex-shrink-0">Reunião:</span>
        <AnalysisSelector options={options} value={analysisId} onChange={switchAnalysis} />
      </div>

      <div className="flex-1 flex flex-col card overflow-hidden">
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
  );
}
