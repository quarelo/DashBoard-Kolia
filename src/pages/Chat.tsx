import { useState, useRef, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { Send, Loader2, User, RotateCcw, ChevronDown, CalendarDays, Lightbulb, X } from "lucide-react";
import { chatService } from "../services/chatService";
import type { ChatMessage, ChatContext } from "../types";
import { cn } from "../lib/utils";
import { KoliaLogo } from "../components/ui/KoliaLogo";

/* ── markdown renderer ──────────────────────────────────────── */
function renderMarkdown(raw: string): string {
  return raw
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/^> (.+)$/gm, '<blockquote class="border-l-[3px] border-brand/40 bg-brand/5 pl-3 py-1.5 rounded-r-lg italic text-ink-secondary text-sm my-2">$1</blockquote>')
    .replace(/^## (.+)$/gm, '<p class="font-bold text-ink mt-3 mb-1">$1</p>')
    .replace(/^(\d+)\. (.+)$/gm, '<li class="ml-4 list-decimal text-ink-secondary text-sm">$2</li>')
    .replace(/^[•\-] (.+)$/gm, '<li class="ml-4 list-disc text-ink-secondary text-sm">$1</li>')
    .replace(/\n\n/g, '<div class="h-2"></div>')
    .replace(/\n/g, "<br/>");
}

/* ── Message bubble ─────────────────────────────────────────── */
function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const time = new Date(msg.timestamp).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

  return (
    <div className={cn("flex gap-3 max-w-3xl group", isUser ? "ml-auto flex-row-reverse" : "")}>
      {/* Avatar */}
      <div className={cn(
        "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center mt-0.5 ring-2",
        isUser
          ? "gradient-brand ring-brand/20"
          : "bg-[#111827] ring-white"
      )}>
        {isUser
          ? <User size={14} className="text-white" />
          : <KoliaLogo variant="icon" height={16} />
        }
      </div>

      {/* Bubble */}
      <div className={cn(
        "flex-1 rounded-2xl px-4 py-3 text-sm leading-relaxed",
        isUser
          ? "gradient-brand text-white rounded-tr-sm shadow-brand-sm"
          : "bg-white border border-surface-border text-ink rounded-tl-sm shadow-card"
      )}>
        {isUser ? (
          <p className="whitespace-pre-wrap">{msg.content}</p>
        ) : (
          <div
            className="[&_strong]:font-semibold [&_strong]:text-ink [&_li]:my-0.5 [&_blockquote]:my-2"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
          />
        )}
        <p className={cn("text-[10px] mt-2 opacity-60", isUser ? "text-white" : "text-ink-muted")}>
          {time}
        </p>
      </div>
    </div>
  );
}

/* ── Typing indicator ───────────────────────────────────────── */
function TypingIndicator() {
  return (
    <div className="flex gap-3">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[#111827] ring-2 ring-white flex items-center justify-center">
        <KoliaLogo variant="icon" height={16} />
      </div>
      <div className="bg-white border border-surface-border rounded-2xl rounded-tl-sm shadow-card px-4 py-3 flex items-center gap-2.5">
        <Loader2 size={13} className="text-brand animate-spin" />
        <span className="text-sm text-ink-secondary">Analisando dados...</span>
        <span className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-1 h-1 rounded-full bg-brand/40"
              style={{ animation: `pulse 1.4s ease-in-out ${i * 0.2}s infinite` }}
            />
          ))}
        </span>
      </div>
    </div>
  );
}

/* ── Context banner ─────────────────────────────────────────── */
function ContextBanner({ context }: { context: ChatContext }) {
  if (context.type === "none") return null;

  const isMeeting = context.type === "meeting";
  return (
    <div className={cn(
      "flex items-center gap-2.5 px-4 py-2.5 rounded-xl border text-xs font-semibold",
      isMeeting
        ? "bg-brand/8 border-brand/25 text-brand"
        : "bg-amber-50 border-amber-200 text-amber-700"
    )}>
      {isMeeting ? <CalendarDays size={13} /> : <Lightbulb size={13} />}
      <span>
        {isMeeting
          ? "Você está conversando com base nesta reunião:"
          : "Você está conversando com base neste insight:"}
        {" "}
        <span className="font-bold">{context.label.replace(/^(📅|💡) /, "")}</span>
      </span>
    </div>
  );
}

/* ── Context selector ───────────────────────────────────────── */
function ContextSelector({ context, onChange }: {
  context: ChatContext; onChange: (ctx: ChatContext) => void;
}) {
  const [open, setOpen] = useState(false);
  const opts = chatService.getContextOptions();
  const noCtx: ChatContext = { type: "none", id: null, label: "Contexto geral" };

  function pick(ctx: ChatContext) { onChange(ctx); setOpen(false); }

  const icon = context.type === "meeting" ? <CalendarDays size={13} className="text-brand" />
             : context.type === "insight"  ? <Lightbulb size={13} className="text-amber-500" />
             : <span className="w-3 h-3 rounded-full gradient-brand inline-block" />;

  const label = context.type === "none"
    ? "Contexto geral (todas as reuniões)"
    : context.label.replace(/^(📅|💡) /, "");

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 px-3.5 py-2 bg-white border border-surface-border rounded-xl text-sm font-medium text-ink hover:border-brand/40 hover:bg-brand/5 transition-all max-w-xs"
      >
        {icon}
        <span className="truncate max-w-[220px]">{label}</span>
        {context.type !== "none" && (
          <button
            onClick={(e) => { e.stopPropagation(); onChange(noCtx); }}
            className="text-ink-muted hover:text-ink ml-1 flex-shrink-0"
          >
            <X size={11} />
          </button>
        )}
        <ChevronDown size={13} className={cn("text-ink-muted flex-shrink-0 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute top-full left-0 mt-2 w-[440px] bg-white border border-surface-border rounded-xl shadow-card-lg z-20 max-h-72 overflow-y-auto scrollbar-thin animate-fade-in">
            {/* Global */}
            <button
              onClick={() => pick(noCtx)}
              className={cn("w-full flex items-center gap-2.5 px-4 py-3 text-sm hover:bg-surface transition-colors border-b border-surface-border", context.type === "none" && "bg-brand/5")}
            >
              <span className="w-3 h-3 rounded-full gradient-brand inline-block flex-shrink-0" />
              <span className="text-ink font-medium flex-1 text-left">Contexto geral (todas as reuniões)</span>
              {context.type === "none" && <span className="text-xs text-brand font-semibold">Ativo</span>}
            </button>

            {/* Meetings group */}
            <div className="px-4 pt-3 pb-1.5">
              <p className="text-[10px] font-bold text-ink-muted uppercase tracking-widest">Reuniões</p>
            </div>
            {opts.meetings.map((o) => (
              <button key={o.id} onClick={() => pick({ type: o.type, id: o.id, label: o.label })}
                className={cn("w-full flex items-center gap-2.5 px-4 py-2.5 text-sm hover:bg-brand/5 transition-colors text-left", context.id === o.id && "bg-brand/5")}>
                <CalendarDays size={13} className="text-brand flex-shrink-0" />
                <span className="text-ink-secondary truncate flex-1">{o.label.replace("📅 ", "")}</span>
                {context.id === o.id && <span className="text-xs text-brand font-bold flex-shrink-0">Ativo</span>}
              </button>
            ))}

            {/* Insights group */}
            <div className="px-4 pt-3 pb-1.5 border-t border-surface-border mt-1">
              <p className="text-[10px] font-bold text-ink-muted uppercase tracking-widest">Insights</p>
            </div>
            {opts.insights.map((o) => (
              <button key={o.id} onClick={() => pick({ type: o.type, id: o.id, label: o.label })}
                className={cn("w-full flex items-center gap-2.5 px-4 py-2.5 text-sm hover:bg-amber-50 transition-colors text-left", context.id === o.id && "bg-amber-50")}>
                <Lightbulb size={13} className="text-amber-500 flex-shrink-0" />
                <span className="text-ink-secondary truncate flex-1">{o.label.replace("💡 ", "")}</span>
                {context.id === o.id && <span className="text-xs text-amber-600 font-bold flex-shrink-0">Ativo</span>}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/* ── main page ──────────────────────────────────────────────── */
export function Chat() {
  const [searchParams] = useSearchParams();

  const initContext = useCallback((): ChatContext => {
    const meetingId = searchParams.get("meetingId");
    if (meetingId) {
      const found = chatService.getContextOptions().meetings.find((m) => m.id === meetingId);
      if (found) return { type: "meeting", id: found.id, label: found.label };
    }
    return { type: "none", id: null, label: "Contexto geral" };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [context,  setContext]  = useState<ChatContext>(initContext);
  const [messages, setMessages] = useState<ChatMessage[]>(() => chatService.getInitialMessages(initContext()));
  const [input,    setInput]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const bottomRef   = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function handleContextChange(ctx: ChatContext) {
    setContext(ctx);
    setMessages(chatService.getInitialMessages(ctx));
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  async function sendMessage(content: string) {
    if (!content.trim() || loading) return;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: content.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages((p) => [...p, userMsg]);
    setInput("");
    setLoading(true);
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    const reply = await chatService.sendMessage(content, context);
    setMessages((p) => [...p, reply]);
    setLoading(false);
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(input); }
  }

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
  }

  const suggested = chatService.getSuggestedQuestions(context);
  const showSuggestions = messages.length <= 1 && !loading;

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem-3rem)] max-h-[820px] animate-fade-in">
      {/* Page header */}
      <div className="flex items-start justify-between mb-3 gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-extrabold text-ink">Chat IA</h1>
          <p className="text-sm text-ink-secondary mt-0.5">Converse com a IA sobre reuniões e insights</p>
        </div>
        <button
          onClick={() => handleContextChange({ type: "none", id: null, label: "Contexto geral" })}
          className="btn-ghost gap-1.5 py-2 text-xs"
        >
          <RotateCcw size={12} />
          Nova conversa
        </button>
      </div>

      {/* Context toolbar */}
      <div className="card px-4 py-3 mb-3 flex flex-wrap items-center gap-3">
        <span className="text-xs font-semibold text-ink-secondary flex-shrink-0">
          Analisar com base em:
        </span>
        <ContextSelector context={context} onChange={handleContextChange} />
        <ContextBanner context={context} />
      </div>

      {/* Chat window */}
      <div className="flex-1 flex flex-col card overflow-hidden">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4 scrollbar-thin bg-[#FAFAFA]">
          {messages.map((msg) => <MessageBubble key={msg.id} msg={msg} />)}
          {loading && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>

        {/* Suggested questions */}
        {showSuggestions && (
          <div className="px-5 py-3 border-t border-surface-border bg-white">
            <p className="text-[10px] font-bold text-ink-muted uppercase tracking-widest mb-2">
              Sugestões
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {suggested.map((q) => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  className="text-left text-xs font-medium text-ink-secondary bg-surface hover:bg-brand/8 hover:text-brand border border-surface-border hover:border-brand/30 rounded-xl px-3.5 py-2.5 transition-all leading-snug"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Input */}
        <div className="px-4 py-4 border-t border-surface-border bg-white">
          <div className="flex gap-3 items-end">
            <div className="flex-1 bg-surface border border-surface-border rounded-2xl focus-within:border-brand/50 focus-within:ring-2 focus-within:ring-brand/20 transition-all">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={handleInput}
                onKeyDown={handleKey}
                placeholder={
                  context.type === "meeting" ? "Pergunte sobre esta reunião..."
                  : context.type === "insight" ? "Pergunte sobre este insight..."
                  : "Pergunte sobre seus clientes, reuniões ou insights..."
                }
                rows={1}
                disabled={loading}
                className="w-full px-4 py-3 text-sm text-ink bg-transparent resize-none focus:outline-none placeholder-ink-muted scrollbar-thin"
                style={{ minHeight: 44, maxHeight: 140 }}
              />
            </div>
            <button
              onClick={() => sendMessage(input)}
              disabled={!input.trim() || loading}
              className={cn(
                "flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-all",
                input.trim() && !loading
                  ? "gradient-brand text-white shadow-brand hover:shadow-brand"
                  : "bg-surface text-ink-disabled cursor-not-allowed"
              )}
            >
              <Send size={15} />
            </button>
          </div>
          <p className="text-[10px] text-ink-muted mt-2 text-center">
            Enter para enviar · Shift+Enter para nova linha
          </p>
        </div>
      </div>
    </div>
  );
}
