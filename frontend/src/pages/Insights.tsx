import { useState, useMemo } from "react";
import {
  Search, Filter, ChevronDown, X, AlertTriangle, Target, Package,
  Heart, Swords, ExternalLink, Calendar, Building2, Tag,
  Lightbulb, Quote, ArrowUpDown,
} from "lucide-react";
import { Badge, priorityConfig } from "../components/ui/Badge";
import { ScoreBar } from "../components/ui/ScoreBar";
import { insightsService, translateType, translatePriority } from "../services/insightsService";
import type { Insight, InsightType, Priority } from "../types";
import { cn } from "../lib/utils";

const allInsights = insightsService.getAll();

const priorityOrder: Record<Priority, number> = { critical: 0, high: 1, medium: 2, low: 3 };

const typeIcons: Record<InsightType, React.ReactNode> = {
  churn_risk:          <AlertTriangle size={14} className="text-rose-500" />,
  upsell_opportunity:  <Target size={14} className="text-brand" />,
  product_feedback:    <Package size={14} className="text-violet-500" />,
  sentiment_alert:     <Heart size={14} className="text-pink-500" />,
  competitive_mention: <Swords size={14} className="text-slate-500" />,
};

/* ── Drawer ─────────────────────────────────────────────────── */
function InsightDrawer({ insight, onClose }: { insight: Insight; onClose: () => void }) {
  const cfg = priorityConfig[insight.priority];

  return (
    <>
      <div className="fixed inset-0 bg-black/25 backdrop-blur-[2px] z-40 animate-fade-in" onClick={onClose} />
      <div className="fixed right-0 top-0 bottom-0 w-full max-w-[520px] bg-white shadow-2xl z-50 flex flex-col animate-slide-right">

        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-surface-border">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap mb-2">
                {typeIcons[insight.type]}
                <Badge variant="type" type={insight.type}>{translateType(insight.type)}</Badge>
                <span className={cn(
                  "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-semibold border",
                  cfg.className
                )}>
                  <span className={cn("w-1.5 h-1.5 rounded-full", cfg.dot)} />
                  {translatePriority(insight.priority)}
                </span>
              </div>
              <h2 className="text-lg font-bold text-ink">{insight.client}</h2>
              <p className="text-sm text-ink-secondary flex items-center gap-2 mt-1">
                <Building2 size={12} />{insight.segment}
                <span className="text-surface-border">·</span>
                <Calendar size={12} />{new Date(insight.date).toLocaleDateString("pt-BR")}
              </p>
            </div>
            <button onClick={onClose} className="p-2 rounded-lg hover:bg-surface text-ink-muted hover:text-ink transition-colors flex-shrink-0">
              <X size={17} />
            </button>
          </div>
        </div>

        {/* Score bar */}
        <div className="px-6 py-3 bg-surface border-b border-surface-border">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-ink-secondary">Score de Risco / Oportunidade</span>
            <span className="text-xl font-black text-ink tabular-nums">{insight.score}<span className="text-xs text-ink-muted font-normal">/100</span></span>
          </div>
          <ScoreBar score={insight.score} showLabel={false} size="sm" />
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5 scrollbar-thin">
          {/* Summary */}
          <section>
            <h3 className="flex items-center gap-2 text-xs font-bold text-ink uppercase tracking-wider mb-2.5">
              <div className="w-5 h-5 rounded bg-brand/10 flex items-center justify-center">
                <Lightbulb size={11} className="text-brand" />
              </div>
              Resumo da Análise
            </h3>
            <p className="text-sm text-ink-secondary leading-relaxed">{insight.summary}</p>
          </section>

          {/* Evidence */}
          <section>
            <h3 className="flex items-center gap-2 text-xs font-bold text-ink uppercase tracking-wider mb-2.5">
              <div className="w-5 h-5 rounded bg-violet-100 flex items-center justify-center">
                <Quote size={11} className="text-violet-600" />
              </div>
              Evidência da Transcrição
            </h3>
            <blockquote className="border-l-[3px] border-brand bg-brand/5 rounded-r-xl p-4">
              <p className="text-sm text-ink italic leading-relaxed">{insight.transcriptEvidence}</p>
            </blockquote>
          </section>

          {/* Products */}
          <section>
            <h3 className="flex items-center gap-2 text-xs font-bold text-ink uppercase tracking-wider mb-2.5">
              <div className="w-5 h-5 rounded bg-emerald-100 flex items-center justify-center">
                <Tag size={11} className="text-emerald-600" />
              </div>
              Produtos Relacionados
            </h3>
            <div className="flex flex-wrap gap-2">
              {insight.relatedProducts.map((p) => (
                <span key={p} className="px-3 py-1.5 bg-surface border border-surface-border rounded-lg text-xs font-medium text-ink-secondary hover:border-brand/30 hover:bg-brand/5 transition-all cursor-default">
                  {p}
                </span>
              ))}
            </div>
          </section>

          {/* AI Recommendation */}
          <section>
            <h3 className="flex items-center gap-2 text-xs font-bold text-ink uppercase tracking-wider mb-2.5">
              <div className="w-5 h-5 rounded bg-amber-100 flex items-center justify-center">
                <Target size={11} className="text-amber-600" />
              </div>
              Recomendação da IA
            </h3>
            <div className="bg-gradient-to-br from-brand/5 to-brand/10 border border-brand/20 rounded-xl p-4">
              <p className="text-sm text-ink leading-relaxed">{insight.aiRecommendation}</p>
            </div>
          </section>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-surface-border flex gap-3">
          <button className="btn-primary flex-1 justify-center">
            <ExternalLink size={13} />
            Ver Reunião Completa
          </button>
          <button onClick={onClose} className="btn-ghost px-4 py-2">
            Fechar
          </button>
        </div>
      </div>
    </>
  );
}

/* ── filters ────────────────────────────────────────────────── */
const typeOptions = [
  { value: "all", label: "Todos os tipos" },
  { value: "churn_risk",          label: "Risco de Churn" },
  { value: "upsell_opportunity",  label: "Oportunidade" },
  { value: "product_feedback",    label: "Feedback Produto" },
  { value: "sentiment_alert",     label: "Alerta Sentimento" },
  { value: "competitive_mention", label: "Menção Concorrente" },
];

const priorityOptions = [
  { value: "all",      label: "Todas as prioridades" },
  { value: "critical", label: "🔴 Crítico" },
  { value: "high",     label: "🟠 Alto" },
  { value: "medium",   label: "🟡 Médio" },
  { value: "low",      label: "🟢 Baixo" },
];

function Select({ value, onChange, options }: {
  value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="input-base appearance-none pr-8 cursor-pointer bg-white py-2"
      >
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-muted pointer-events-none" />
    </div>
  );
}

/* ── sort header cell ───────────────────────────────────────── */
function SortTh({ label, field, current, dir, onSort }: {
  label: string; field: string; current: string; dir: "asc" | "desc";
  onSort: (f: string) => void;
}) {
  const active = current === field;
  return (
    <th
      onClick={() => onSort(field)}
      className="text-left text-xs font-semibold text-ink-secondary uppercase tracking-wider px-5 py-3 cursor-pointer hover:text-ink select-none whitespace-nowrap"
    >
      <div className="flex items-center gap-1.5">
        {label}
        <ArrowUpDown size={11} className={cn("transition-colors", active ? "text-brand" : "text-ink-disabled")} />
      </div>
    </th>
  );
}

/* ── main page ──────────────────────────────────────────────── */
export function Insights() {
  const [selected, setSelected] = useState<Insight | null>(null);
  const [search,        setSearch]        = useState("");
  const [typeFilter,    setTypeFilter]    = useState("all");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [sortField,     setSortField]     = useState<"score" | "date" | "priority">("priority");
  const [sortDir,       setSortDir]       = useState<"asc" | "desc">("asc");

  const filtered = useMemo(() => {
    let data = [...allInsights];

    if (search) {
      const q = search.toLowerCase();
      data = data.filter((i) =>
        i.client.toLowerCase().includes(q) ||
        i.summary.toLowerCase().includes(q) ||
        i.segment.toLowerCase().includes(q)
      );
    }
    if (typeFilter !== "all") data = data.filter((i) => i.type === typeFilter);
    if (priorityFilter !== "all") data = data.filter((i) => i.priority === priorityFilter);

    data.sort((a, b) => {
      let cmp = 0;
      if (sortField === "score") cmp = a.score - b.score;
      else if (sortField === "date") cmp = a.date.localeCompare(b.date);
      else cmp = priorityOrder[a.priority] - priorityOrder[b.priority];
      return sortDir === "asc" ? cmp : -cmp;
    });

    return data;
  }, [search, typeFilter, priorityFilter, sortField, sortDir]);

  function toggleSort(field: "score" | "date" | "priority") {
    if (sortField === field) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortField(field); setSortDir("asc"); }
  }

  /* priority badge inline */
  function PriorityBadge({ priority }: { priority: Priority }) {
    const cfg = priorityConfig[priority];
    return (
      <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-semibold border", cfg.className)}>
        <span className={cn("w-1.5 h-1.5 rounded-full", cfg.dot)} />
        {translatePriority(priority)}
      </span>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-ink">Insights</h1>
          <p className="text-sm text-ink-secondary mt-0.5">
            {filtered.length} de {allInsights.length} insights · análise de transcrições por IA
          </p>
        </div>
      </div>

      {/* Summary pills */}
      <div className="flex flex-wrap gap-2">
        {(["critical","high","medium","low"] as Priority[]).map((p) => {
          const count = allInsights.filter((i) => i.priority === p).length;
          const cfg = priorityConfig[p];
          return (
            <button
              key={p}
              onClick={() => setPriorityFilter(priorityFilter === p ? "all" : p)}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all",
                priorityFilter === p
                  ? cn(cfg.className, "ring-2 ring-offset-1 ring-current/30")
                  : "bg-white text-ink-secondary border-surface-border hover:border-brand/30"
              )}
            >
              <span className={cn("w-2 h-2 rounded-full", cfg.dot)} />
              {cfg.label}: {count}
            </button>
          );
        })}
        {priorityFilter !== "all" && (
          <button onClick={() => setPriorityFilter("all")} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs text-ink-muted hover:text-ink transition-colors">
            <X size={11} />Limpar filtro
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="card p-4 flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-48">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted pointer-events-none" />
          <input
            type="text"
            placeholder="Buscar cliente, insight, segmento..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input-base pl-9"
          />
          {search && (
            <button onClick={() => setSearch("")} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink transition-colors">
              <X size={13} />
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Filter size={13} className="text-ink-muted" />
          <Select value={typeFilter}     onChange={setTypeFilter}     options={typeOptions} />
          <Select value={priorityFilter} onChange={setPriorityFilter} options={priorityOptions} />
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-surface border-b border-surface-border">
                <th className="text-left text-xs font-semibold text-ink-secondary uppercase tracking-wider px-5 py-3 w-5">
                  <span className="sr-only">Prioridade</span>
                </th>
                <th className="text-left text-xs font-semibold text-ink-secondary uppercase tracking-wider px-5 py-3">
                  Cliente
                </th>
                <th className="text-left text-xs font-semibold text-ink-secondary uppercase tracking-wider px-5 py-3">
                  Tipo de Insight
                </th>
                <SortTh label="Score"      field="score"    current={sortField} dir={sortDir} onSort={(f) => toggleSort(f as "score" | "date" | "priority")} />
                <SortTh label="Prioridade" field="priority" current={sortField} dir={sortDir} onSort={(f) => toggleSort(f as "score" | "date" | "priority")} />
                <SortTh label="Data"       field="date"     current={sortField} dir={sortDir} onSort={(f) => toggleSort(f as "score" | "date" | "priority")} />
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-16 text-sm text-ink-muted">
                    Nenhum insight encontrado com os filtros selecionados.
                  </td>
                </tr>
              ) : filtered.map((insight) => (
                <tr
                  key={insight.id}
                  onClick={() => setSelected(insight)}
                  className="hover:bg-brand/[0.03] cursor-pointer transition-colors group"
                >
                  {/* Priority dot */}
                  <td className="px-4 py-3.5">
                    <span className={cn("w-2 h-2 rounded-full inline-block", priorityConfig[insight.priority].dot)} />
                  </td>
                  {/* Client */}
                  <td className="px-5 py-3.5">
                    <p className="text-sm font-semibold text-ink group-hover:text-brand transition-colors">{insight.client}</p>
                    <p className="text-xs text-ink-muted">{insight.segment}</p>
                  </td>
                  {/* Type */}
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-2">
                      {typeIcons[insight.type]}
                      <span className="text-sm text-ink-secondary">{translateType(insight.type)}</span>
                    </div>
                  </td>
                  {/* Score */}
                  <td className="px-5 py-3.5">
                    <div className="w-28">
                      <ScoreBar score={insight.score} size="xs" />
                    </div>
                  </td>
                  {/* Priority */}
                  <td className="px-5 py-3.5">
                    <PriorityBadge priority={insight.priority} />
                  </td>
                  {/* Date */}
                  <td className="px-5 py-3.5 text-sm text-ink-secondary whitespace-nowrap">
                    {new Date(insight.date).toLocaleDateString("pt-BR")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {selected && <InsightDrawer insight={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
