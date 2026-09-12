import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search, ChevronRight, ChevronDown, Filter, Layers, Users, Calendar, CheckCircle2, Loader2, Trash2,
} from "lucide-react";
import { useAsync } from "../lib/useAsync";
import { useAuth } from "../context/AuthContext";
import { DeleteMeetingDialog } from "../components/meetings/DeleteMeetingDialog";
import { dashboardService, sentimentLabels, sentimentTone, statusLabel } from "../services/dashboardService";
import { PageError, PageLoader, EmptyState } from "../components/ui/PageState";
import { ScoreBar } from "../components/ui/ScoreBar";
import type { AnalysisListItem, SentimentClass } from "../types";
import { cn } from "../lib/utils";

const sentimentOptions = [
  { value: "all", label: "Qualquer sentimento" },
  { value: "positivo", label: "Positivo" },
  { value: "neutro", label: "Neutro" },
  { value: "negativo", label: "Negativo" },
  { value: "misto", label: "Misto" },
];

function SentimentBadge({ sentiment }: { sentiment: SentimentClass }) {
  return (
    <span className={cn("inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border", sentimentTone[sentiment])}>
      {sentimentLabels[sentiment]}
    </span>
  );
}

function StatusChip({ status, isFinal }: { status: string; isFinal: boolean }) {
  const done = isFinal || status === "DONE";
  return (
    <span className={cn(
      "inline-flex items-center gap-1 text-xs font-medium",
      done ? "text-emerald-600" : "text-amber-600",
    )}>
      {done ? <CheckCircle2 size={12} /> : <Loader2 size={12} className="animate-spin" />}
      {statusLabel(status)}
    </span>
  );
}

function MeetingCard({ item, onDelete }: { item: AnalysisListItem; onDelete?: () => void }) {
  const navigate = useNavigate();
  return (
    <div
      onClick={() => navigate(`/app/meetings/${item.analysisId}`)}
      className="bg-white border border-gray-200 rounded-xl p-5 hover:shadow-md hover:border-brand/30 transition-all duration-200 cursor-pointer group"
    >
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex-1 min-w-0">
          <h3 className="font-bold text-gray-900 text-sm leading-snug group-hover:text-brand transition-colors line-clamp-2">
            {item.title}
          </h3>
        </div>
        <SentimentBadge sentiment={item.sentiment} />
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-gray-500 mb-4">
        <span className="flex items-center gap-1.5">
          <Layers size={12} className="text-gray-400" />
          {item.totalChunks} trechos
        </span>
        <span className="flex items-center gap-1.5">
          <Calendar size={12} className="text-gray-400" />
          {new Date(item.createdAt).toLocaleDateString("pt-BR")}
        </span>
        <StatusChip status={item.status} isFinal={item.summaryIsFinal} />
      </div>

      {item.products.length > 0 && (
        <p className="text-xs text-gray-500 leading-relaxed mb-4 line-clamp-2">
          <span className="font-medium text-gray-600">Produtos: </span>
          {item.products.join(" · ")}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-gray-500">Risco de churn</span>
            <span className="text-xs font-bold text-gray-700">{item.riskScore}</span>
          </div>
          <ScoreBar score={item.riskScore} showLabel={false} size="sm" colorMode="risk" />
        </div>
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-gray-500">Oportunidade</span>
            <span className="text-xs font-bold text-gray-700">{item.opportunityScore}</span>
          </div>
          <ScoreBar score={item.opportunityScore} showLabel={false} size="sm" colorMode="opportunity" />
        </div>
      </div>

      <div className="flex items-center justify-between">
        {item.personas.length > 0 ? (
          <span className="flex items-center gap-1.5 text-xs text-gray-500">
            <Users size={12} className="text-gray-400" />
            {item.personas.slice(0, 3).join(", ")}
          </span>
        ) : <span />}
        <div className="flex items-center gap-1">
          {onDelete && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              title="Excluir reunião"
              aria-label="Excluir reunião"
              className="p-1.5 rounded-md text-gray-300 hover:text-rose-600 hover:bg-rose-50 transition-colors"
            >
              <Trash2 size={14} />
            </button>
          )}
          <ChevronRight size={15} className="text-gray-300 group-hover:text-brand transition-colors" />
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, color }: { label: string; value: string | number; sub: string; color: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl px-5 py-4 flex flex-col gap-0.5">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={cn("text-2xl font-black", color)}>{value}</p>
      <p className="text-xs text-gray-400">{sub}</p>
    </div>
  );
}

export function Meetings() {
  const { data, loading, error, reload } = useAsync(() => dashboardService.list(0, 200), []);
  const [search, setSearch] = useState("");
  const [sentimentFilter, setSentimentFilter] = useState("all");
  const [sortField, setSortField] = useState<"date" | "riskScore" | "opportunityScore">("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const { user } = useAuth();
  const [deleting, setDeleting] = useState<AnalysisListItem | null>(null);
  // Tira da tela na hora, sem recarregar a lista inteira depois de cada exclusão.
  const [removedIds, setRemovedIds] = useState<Set<string>>(() => new Set());

  const items = useMemo(
    () => (data?.items ?? []).filter((m) => !removedIds.has(m.analysisId)),
    [data, removedIds],
  );

  const filtered = useMemo(() => {
    let rows = [...items];
    if (search) {
      const q = search.toLowerCase();
      rows = rows.filter(
        (m) =>
          m.title.toLowerCase().includes(q) ||
          m.products.some((p) => p.toLowerCase().includes(q)) ||
          m.personas.some((p) => p.toLowerCase().includes(q)),
      );
    }
    if (sentimentFilter !== "all") rows = rows.filter((m) => m.sentiment === sentimentFilter);
    rows.sort((a, b) => {
      const cmp =
        sortField === "date" ? a.createdAt.localeCompare(b.createdAt)
        : sortField === "riskScore" ? a.riskScore - b.riskScore
        : a.opportunityScore - b.opportunityScore;
      return sortDir === "asc" ? cmp : -cmp;
    });
    return rows;
  }, [items, search, sentimentFilter, sortField, sortDir]);

  function toggleSort(field: typeof sortField) {
    if (sortField === field) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortField(field); setSortDir("desc"); }
  }

  if (loading) return <PageLoader label="Carregando reuniões..." />;
  if (error || !data) return <PageError message={error ?? "Sem dados."} onRetry={reload} />;

  const analyzed = items.filter((m) => m.summaryIsFinal || m.status === "DONE").length;
  const highRisk = items.filter((m) => m.riskScore >= 67).length;
  const avgRisk = items.length ? Math.round(items.reduce((s, m) => s + m.riskScore, 0) / items.length) : 0;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Reuniões</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {filtered.length} de {items.length} · transcrições analisadas pela IA
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Total de Reuniões" value={items.length} sub="transcrições processadas" color="text-brand" />
        <StatCard label="Análises Concluídas" value={`${analyzed}/${items.length}`} sub="resumo final pronto" color="text-emerald-600" />
        <StatCard label="Risco Alto" value={highRisk} sub="score ≥ 67" color="text-rose-600" />
        <StatCard label="Risco Médio" value={avgRisk} sub="média dos scores" color="text-violet-600" />
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-4 flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-52">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Buscar título, produto, persona..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand/20 focus:border-brand/30 transition-all"
          />
        </div>

        <div className="relative">
          <Filter size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <select
            value={sentimentFilter}
            onChange={(e) => setSentimentFilter(e.target.value)}
            className="appearance-none pl-9 pr-8 py-2 text-sm bg-white border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand/20 focus:border-brand/30 cursor-pointer"
          >
            {sentimentOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
        </div>

        <div className="flex items-center gap-1.5 ml-auto flex-wrap">
          <span className="text-xs text-gray-400">Ordenar por:</span>
          {(["date", "riskScore", "opportunityScore"] as const).map((f) => {
            const labels: Record<typeof f, string> = { date: "Data", riskScore: "Risco", opportunityScore: "Oportunidade" };
            return (
              <button
                key={f}
                onClick={() => toggleSort(f)}
                className={cn(
                  "px-2.5 py-1 rounded-md text-xs font-medium border transition-all",
                  sortField === f
                    ? "gradient-brand text-white border-brand/30"
                    : "bg-white text-gray-600 border-gray-200 hover:border-brand/30",
                )}
              >
                {labels[f]}{sortField === f && (sortDir === "desc" ? " ↓" : " ↑")}
              </button>
            );
          })}
        </div>
      </div>

      {items.length === 0 ? (
        <EmptyState
          title="Nenhuma reunião analisada ainda"
          hint="Importe transcrições e rode a análise para vê-las aqui."
        />
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-sm text-gray-400 bg-white rounded-xl border border-gray-200">
          Nenhuma reunião encontrada com os filtros selecionados.
        </div>
      ) : (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((item) => (
            <MeetingCard
              key={item.analysisId}
              item={item}
              // Análise sem importação: só o diretor comercial exclui; o backend confere o resto.
              onDelete={user?.role === "SALES_DIRECTOR" || item.meetingId !== null ? () => setDeleting(item) : undefined}
            />
          ))}
        </div>
      )}

      {deleting && (
        <DeleteMeetingDialog
          analysisId={deleting.analysisId}
          title={deleting.title}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            setRemovedIds((ids) => new Set(ids).add(deleting.analysisId));
            setDeleting(null);
          }}
        />
      )}
    </div>
  );
}
