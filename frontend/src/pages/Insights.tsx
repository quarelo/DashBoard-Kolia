import { useState, useMemo } from "react";
import {
  Search, X, AlertTriangle, Target, Package, TriangleAlert, HelpCircle,
  ChevronDown, Quote,
} from "lucide-react";
import { useAsync } from "../lib/useAsync";
import { dashboardService } from "../services/dashboardService";
import { PageError, PageLoader, EmptyState } from "../components/ui/PageState";
import { Badge } from "../components/ui/Badge";
import { ScoreBar } from "../components/ui/ScoreBar";
import { cn } from "../lib/utils";
import type { AnalysisDetail, DerivedInsight, InsightType, Priority } from "../types";

const priorityOrder: Record<Priority, number> = { critical: 0, high: 1, medium: 2, low: 3 };
const priorityLabels: Record<Priority, string> = { critical: "Crítico", high: "Alto", medium: "Médio", low: "Baixo" };
const typeLabels: Record<InsightType, string> = {
  churn_risk: "Risco de Churn",
  upsell_opportunity: "Oportunidade",
  product_feedback: "Feedback / Gap",
  sentiment_alert: "Alerta de Sentimento",
  competitive_mention: "Menção a Concorrente",
};
const typeIcons: Record<InsightType, React.ReactNode> = {
  churn_risk: <AlertTriangle size={14} className="text-rose-500" />,
  upsell_opportunity: <Target size={14} className="text-blue-500" />,
  product_feedback: <Package size={14} className="text-violet-500" />,
  sentiment_alert: <TriangleAlert size={14} className="text-amber-500" />,
  competitive_mention: <HelpCircle size={14} className="text-slate-500" />,
};

function scoreToPriority(score: number): Priority {
  if (score >= 67) return "critical";
  if (score >= 40) return "high";
  if (score >= 15) return "medium";
  return "low";
}

/** Deriva sinais individuais do resumo final de cada análise. */
function buildInsights(details: AnalysisDetail[]): DerivedInsight[] {
  const out: DerivedInsight[] = [];
  for (const d of details) {
    const fs = d.finalSummary;
    if (!fs) continue;
    const base = { analysisId: d.analysisId, meetingTitle: d.title, date: d.createdAt, relatedProducts: fs.produto };

    if (fs.risco_churn.score > 0) {
      out.push({
        ...base, id: `${d.analysisId}-churn`, type: "churn_risk",
        priority: scoreToPriority(fs.risco_churn.score), score: fs.risco_churn.score,
        category: "Risco de churn", summary: fs.risco_churn.justificativa || "Sinal de risco identificado.",
        evidence: fs.evidencias.find((e) => e.categoria === "churn")?.trecho ?? "",
      });
    }
    if (fs.score_oportunidade.score > 0) {
      out.push({
        ...base, id: `${d.analysisId}-opp`, type: "upsell_opportunity",
        priority: scoreToPriority(fs.score_oportunidade.score), score: fs.score_oportunidade.score,
        category: "Oportunidade comercial", summary: fs.score_oportunidade.justificativa || fs.oportunidade_comercial[0] || "Oportunidade identificada.",
        evidence: fs.evidencias.find((e) => e.categoria === "oportunidade")?.trecho ?? "",
      });
    }
    fs.oportunidade_comercial.forEach((text, i) => {
      if (fs.score_oportunidade.score > 0 && i === 0) return;
      out.push({
        ...base, id: `${d.analysisId}-oc-${i}`, type: "upsell_opportunity", priority: "medium",
        score: fs.score_oportunidade.score, category: "Oportunidade comercial", summary: text, evidence: "",
      });
    });
    fs.problemas_identificados.forEach((text, i) => out.push({
      ...base, id: `${d.analysisId}-prob-${i}`, type: "product_feedback", priority: "high",
      score: fs.risco_churn.score, category: "Problema identificado", summary: text, evidence: "",
    }));
    fs.gap_produto.forEach((text, i) => out.push({
      ...base, id: `${d.analysisId}-gap-${i}`, type: "product_feedback", priority: "medium",
      score: 0, category: "Gap de produto", summary: text, evidence: "",
    }));
    fs.feedback_produto.forEach((text, i) => out.push({
      ...base, id: `${d.analysisId}-fb-${i}`, type: "product_feedback", priority: "low",
      score: 0, category: "Feedback de produto", summary: text, evidence: "",
    }));
    if (d.sentiment === "negativo" || d.sentiment === "misto") {
      out.push({
        ...base, id: `${d.analysisId}-sent`, type: "sentiment_alert",
        priority: d.sentiment === "negativo" ? "high" : "medium", score: 0,
        category: "Alerta de sentimento", summary: fs.sentimento.justificativa || `Sentimento ${d.sentiment}.`,
        evidence: fs.evidencias.find((e) => e.categoria === "sentimento")?.trecho ?? "",
      });
    }
  }
  return out;
}

function InsightDrawer({ insight, onClose }: { insight: DerivedInsight; onClose: () => void }) {
  return (
    <>
      <div className="fixed inset-0 bg-black/25 backdrop-blur-[2px] z-40 animate-fade-in" onClick={onClose} />
      <div className="fixed right-0 top-0 bottom-0 w-full max-w-[520px] bg-white shadow-2xl z-50 flex flex-col animate-slide-right">
        <div className="px-6 pt-6 pb-4 border-b border-surface-border">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap mb-2">
                {typeIcons[insight.type]}
                <Badge variant="type" type={insight.type}>{typeLabels[insight.type]}</Badge>
                <Badge variant="priority" priority={insight.priority}>{priorityLabels[insight.priority]}</Badge>
              </div>
              <h2 className="text-lg font-bold text-ink">{insight.meetingTitle}</h2>
              <p className="text-sm text-ink-secondary mt-1">
                {insight.category} · {new Date(insight.date).toLocaleDateString("pt-BR")}
              </p>
            </div>
            <button onClick={onClose} className="p-2 rounded-lg hover:bg-surface text-ink-muted hover:text-ink transition-colors flex-shrink-0">
              <X size={17} />
            </button>
          </div>
        </div>

        {insight.score > 0 && (
          <div className="px-6 py-3 bg-surface border-b border-surface-border">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-ink-secondary">Score</span>
              <span className="text-xl font-black text-ink tabular-nums">{insight.score}<span className="text-xs text-ink-muted font-normal">/100</span></span>
            </div>
            <ScoreBar score={insight.score} showLabel={false} size="sm" colorMode={insight.type === "upsell_opportunity" ? "opportunity" : "risk"} />
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5 scrollbar-thin">
          <section>
            <h3 className="text-xs font-bold text-ink uppercase tracking-wider mb-2">Descrição</h3>
            <p className="text-sm text-ink-secondary leading-relaxed">{insight.summary}</p>
          </section>
          {insight.evidence && (
            <section>
              <h3 className="flex items-center gap-2 text-xs font-bold text-ink uppercase tracking-wider mb-2">
                <Quote size={11} className="text-violet-600" /> Evidência
              </h3>
              <blockquote className="border-l-[3px] border-brand bg-brand/5 rounded-r-xl p-4">
                <p className="text-sm text-ink italic leading-relaxed">"{insight.evidence}"</p>
              </blockquote>
            </section>
          )}
          {insight.relatedProducts.length > 0 && (
            <section>
              <h3 className="text-xs font-bold text-ink uppercase tracking-wider mb-2">Produtos relacionados</h3>
              <div className="flex flex-wrap gap-2">
                {insight.relatedProducts.map((p) => (
                  <span key={p} className="px-3 py-1.5 bg-surface border border-surface-border rounded-lg text-xs font-medium text-ink-secondary">{p}</span>
                ))}
              </div>
            </section>
          )}
        </div>

        <div className="px-6 py-4 border-t border-surface-border flex gap-3">
          <a href={`/app/meetings/${insight.analysisId}`} className="btn-primary flex-1 justify-center">Ver reunião completa</a>
          <button onClick={onClose} className="btn-ghost px-4 py-2">Fechar</button>
        </div>
      </div>
    </>
  );
}

const typeOptions = [
  { value: "all", label: "Todos os tipos" },
  { value: "churn_risk", label: "Risco de Churn" },
  { value: "upsell_opportunity", label: "Oportunidade" },
  { value: "product_feedback", label: "Feedback / Gap" },
  { value: "sentiment_alert", label: "Alerta de Sentimento" },
];

export function Insights() {
  const { data, loading, error, reload } = useAsync(async () => {
    const { items } = await dashboardService.list(0, 100);
    const details = await Promise.all(items.slice(0, 60).map((i) => dashboardService.detail(i.analysisId)));
    return buildInsights(details);
  }, []);

  const [selected, setSelected] = useState<DerivedInsight | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [priorityFilter, setPriorityFilter] = useState<Priority | "all">("all");

  const all = useMemo(() => data ?? [], [data]);

  const filtered = useMemo(() => {
    let rows = [...all];
    if (search) {
      const q = search.toLowerCase();
      rows = rows.filter((i) => i.summary.toLowerCase().includes(q) || i.meetingTitle.toLowerCase().includes(q));
    }
    if (typeFilter !== "all") rows = rows.filter((i) => i.type === typeFilter);
    if (priorityFilter !== "all") rows = rows.filter((i) => i.priority === priorityFilter);
    rows.sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority] || b.score - a.score);
    return rows;
  }, [all, search, typeFilter, priorityFilter]);

  if (loading) return <PageLoader label="Extraindo sinais das análises..." />;
  if (error) return <PageError message={error} onRetry={reload} />;

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="text-2xl font-extrabold text-ink">Insights</h1>
        <p className="text-sm text-ink-secondary mt-0.5">
          {filtered.length} de {all.length} sinais extraídos das transcrições
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {(["critical", "high", "medium", "low"] as Priority[]).map((p) => {
          const count = all.filter((i) => i.priority === p).length;
          return (
            <button
              key={p}
              onClick={() => setPriorityFilter(priorityFilter === p ? "all" : p)}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all",
                priorityFilter === p ? "bg-brand text-white border-brand" : "bg-white text-ink-secondary border-surface-border hover:border-brand/30",
              )}
            >
              {priorityLabels[p]}: {count}
            </button>
          );
        })}
        {priorityFilter !== "all" && (
          <button onClick={() => setPriorityFilter("all")} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs text-ink-muted hover:text-ink">
            <X size={11} /> Limpar
          </button>
        )}
      </div>

      <div className="card p-4 flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-48">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted pointer-events-none" />
          <input
            type="text"
            placeholder="Buscar sinal ou reunião..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input-base pl-9"
          />
        </div>
        <div className="relative">
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="input-base appearance-none pr-8 cursor-pointer bg-white py-2">
            {typeOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-muted pointer-events-none" />
        </div>
      </div>

      {all.length === 0 ? (
        <EmptyState title="Nenhum sinal extraído ainda" hint="Assim que houver análises com resumo final, os sinais aparecem aqui." />
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-surface border-b border-surface-border text-left text-xs font-semibold text-ink-secondary uppercase tracking-wider">
                  <th className="px-5 py-3">Reunião</th>
                  <th className="px-5 py-3">Tipo</th>
                  <th className="px-5 py-3">Sinal</th>
                  <th className="px-5 py-3">Score</th>
                  <th className="px-5 py-3">Prioridade</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {filtered.length === 0 ? (
                  <tr><td colSpan={5} className="text-center py-16 text-sm text-ink-muted">Nenhum sinal com os filtros selecionados.</td></tr>
                ) : filtered.map((insight) => (
                  <tr key={insight.id} onClick={() => setSelected(insight)} className="hover:bg-brand/[0.03] cursor-pointer transition-colors group">
                    <td className="px-5 py-3.5">
                      <p className="text-sm font-semibold text-ink group-hover:text-brand transition-colors truncate max-w-[180px]">{insight.meetingTitle}</p>
                      <p className="text-xs text-ink-muted">{new Date(insight.date).toLocaleDateString("pt-BR")}</p>
                    </td>
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">{typeIcons[insight.type]}<span className="text-sm text-ink-secondary whitespace-nowrap">{typeLabels[insight.type]}</span></div>
                    </td>
                    <td className="px-5 py-3.5"><p className="text-sm text-ink-secondary line-clamp-2 max-w-md">{insight.summary}</p></td>
                    <td className="px-5 py-3.5"><div className="w-24">{insight.score > 0 ? <ScoreBar score={insight.score} size="xs" colorMode={insight.type === "upsell_opportunity" ? "opportunity" : "risk"} /> : <span className="text-xs text-ink-muted">—</span>}</div></td>
                    <td className="px-5 py-3.5"><Badge variant="priority" priority={insight.priority}>{priorityLabels[insight.priority]}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {selected && <InsightDrawer insight={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
