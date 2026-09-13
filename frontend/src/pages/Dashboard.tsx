import { useState } from "react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Legend,
} from "recharts";
import {
  FileText, Clock, Package, AlertTriangle, TrendingUp, Filter, ChevronDown, X, Loader2,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { KpiCard } from "../components/ui/KpiCard";
import { Card, CardContent, CardHeader, CardTitle, CardSubtitle } from "../components/ui/Card";
import { ScoreBar } from "../components/ui/ScoreBar";
import {
  dashboardService, formatDuration, formatMonthLabel, themeLabel,
} from "../services/dashboardService";
import { useAsync } from "../lib/useAsync";
import { PageError, PageLoader } from "../components/ui/PageState";
import type {
  ExecutiveDashboard, MonthlyComparison, ProductBreakdown, ProductMeetingItem,
  RankedMeeting, SegmentRiskOpportunity, ThemeRanking, UfRisk,
} from "../types";

const RISK_COLOR = "#ef4444";
const OPPORTUNITY_COLOR = "#22c55e";
const NEUTRAL_COLOR = "#8b5cf6";

// Altura FIXA (não max-h) para as listas de ranking: cards lado a lado com
// contagens diferentes (2 UFs vs 6 segmentos, por exemplo) ficavam com
// alturas desiguais porque max-h só limita o crescimento, não garante um
// piso — uma lista curta simplesmente ficava mais baixa que a longa. Com
// altura fixa os dois cards do par sempre batem, e quem tem mais itens rola
// por dentro em vez de esticar o card.
const RANKING_LIST_HEIGHT = "h-[320px] overflow-y-auto pr-1";

export function Dashboard() {
  const { data, loading, error, reload } = useAsync(() => dashboardService.executive(), []);

  // Filtro só do Top 5 (risco/oportunidade): não mexe no resto da dashboard.
  // Vazio = sem filtro, usa o top5 que já veio no payload geral (sem chamada
  // extra); só busca de novo quando o gestor escolhe uma UF/segmento.
  const [top5Uf, setTop5Uf] = useState("");
  const [top5Segmento, setTop5Segmento] = useState("");
  const hasTop5Filter = Boolean(top5Uf || top5Segmento);
  const {
    data: filteredTop5, loading: top5Loading, error: top5Error, reload: reloadTop5,
  } = useAsync(
    () => hasTop5Filter
      ? dashboardService.executive({ uf: top5Uf || undefined, segmento: top5Segmento || undefined })
      : Promise.resolve(null),
    [top5Uf, top5Segmento],
  );

  // Produto selecionado no Gráfico de Produto (clique numa barra abre o
  // detalhe); null = modal fechado, sem chamada extra.
  const [selectedProduct, setSelectedProduct] = useState<string | null>(null);

  if (loading) return <PageLoader label="Carregando indicadores..." />;
  if (error || !data) return <PageError message={error ?? "Sem dados."} onRetry={reload} />;

  const top5Risco = hasTop5Filter && filteredTop5 ? filteredTop5.top5Risco : data.top5Risco;
  const top5Oportunidade = hasTop5Filter && filteredTop5 ? filteredTop5.top5Oportunidade : data.top5Oportunidade;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-extrabold text-ink">Dashboard Executiva</h1>
          <p className="text-sm text-ink-secondary mt-0.5">
            Visão gerencial das reuniões analisadas pela IA
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-ink-secondary">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          Dados do banco
        </div>
      </div>

      <KpiRow data={data} />
      <MonthlyComparisonSection items={data.comparativoMensal} />
      <ProductSection items={data.topProdutos} onSelectProduct={setSelectedProduct} />
      <ThemesSection items={data.temas} />

      <div className="grid lg:grid-cols-2 gap-4 items-start">
        <UfRiskSection items={data.topUfRisco} />
        <SegmentSection items={data.topSegmentos} />
      </div>

      <Top5FilterBar
        uf={top5Uf} segmento={top5Segmento}
        ufOptions={data.topUfRisco.map((u) => u.uf)}
        segmentoOptions={data.topSegmentos.map((s) => s.segmento)}
        onUfChange={setTop5Uf} onSegmentoChange={setTop5Segmento}
      />

      <div className="grid lg:grid-cols-2 gap-4 items-start">
        <RankedMeetingsSection
          title="Top 5 — Reuniões em Risco de Churn"
          subtitle="Maior score de risco primeiro"
          icon={<AlertTriangle size={15} className="text-rose-500" />}
          items={top5Risco}
          loading={hasTop5Filter && top5Loading}
          error={hasTop5Filter ? top5Error : null}
          onRetry={reloadTop5}
          colorMode="risk"
          emptyLabel={hasTop5Filter
            ? "Nenhuma reunião com risco de churn para esse filtro."
            : "Nenhuma reunião com risco de churn identificado no período."}
        />
        <RankedMeetingsSection
          title="Top 5 — Reuniões com Mais Oportunidade"
          subtitle="Maior score de oportunidade primeiro"
          icon={<TrendingUp size={15} className="text-emerald-500" />}
          items={top5Oportunidade}
          loading={hasTop5Filter && top5Loading}
          error={hasTop5Filter ? top5Error : null}
          onRetry={reloadTop5}
          colorMode="opportunity"
          emptyLabel={hasTop5Filter
            ? "Nenhuma oportunidade para esse filtro."
            : "Nenhuma oportunidade comercial identificada no período."}
        />
      </div>

      {selectedProduct && (
        <ProductMeetingsModal nome={selectedProduct} onClose={() => setSelectedProduct(null)} />
      )}
    </div>
  );
}

/* ── 1. KPIs ───────────────────────────────────────────────────────────── */

function KpiRow({ data }: { data: ExecutiveDashboard }) {
  const { kpis } = data;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <KpiCard
        label="Reuniões no período"
        value={kpis.totalReunioes}
        icon={<FileText size={16} />}
        accent="brand"
      />
      <KpiCard
        label="Duração média"
        value={kpis.duracaoMediaMinutos != null ? formatDuration(kpis.duracaoMediaMinutos) : "—"}
        icon={<Clock size={16} />}
        accent="violet"
      />
      <KpiCard
        label="Produto mais citado"
        value={kpis.produtoMaisCitado ?? "—"}
        caption={
          kpis.produtoMaisCitado && kpis.mencoesProdutoMaisCitado != null
            ? `${kpis.mencoesProdutoMaisCitado} menç${kpis.mencoesProdutoMaisCitado === 1 ? "ão" : "ões"}`
            : undefined
        }
        icon={<Package size={16} />}
        accent="blue"
      />
    </div>
  );
}

/* ── 2. Comparativo mensal ─────────────────────────────────────────────── */

function MonthlyComparisonSection({ items }: { items: MonthlyComparison[] }) {
  const chartData = items.map((m) => ({ ...m, label: formatMonthLabel(m.mes) }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Comparativo Mensal</CardTitle>
        <CardSubtitle>Reuniões, risco médio e oportunidade média ao longo do tempo</CardSubtitle>
      </CardHeader>
      <CardContent>
        {chartData.length === 0 ? (
          <EmptyChart label="Sem histórico mensal suficiente para este gráfico." />
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#9CA3AF" }} axisLine={false} tickLine={false} />
              <YAxis yAxisId="reunioes" allowDecimals={false} tick={{ fontSize: 10, fill: "#9CA3AF" }} axisLine={false} tickLine={false} />
              <YAxis yAxisId="score" orientation="right" domain={[0, 100]} tick={{ fontSize: 10, fill: "#9CA3AF" }} axisLine={false} tickLine={false} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar yAxisId="reunioes" dataKey="reunioes" name="Reuniões" fill={NEUTRAL_COLOR} radius={[4, 4, 0, 0]} barSize={28} fillOpacity={0.25} />
              <Line yAxisId="score" type="monotone" dataKey="riscoMedio" name="Risco médio" stroke={RISK_COLOR} strokeWidth={2} dot={{ r: 3 }} />
              <Line yAxisId="score" type="monotone" dataKey="oportunidadeMedia" name="Oportunidade média" stroke={OPPORTUNITY_COLOR} strokeWidth={2} dot={{ r: 3 }} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}

/* ── 3. Gráfico de produto ─────────────────────────────────────────────── */
const PRODUCT_LIST_HEIGHT = "max-h-[288px] overflow-y-auto pr-1";

function ProductSection({ items, onSelectProduct }: {
  items: ProductBreakdown[];
  onSelectProduct: (nome: string) => void;
}) {
  const hasBreakdown = items.some((p) => p.reclamacoes != null || p.gaps != null || p.elogios != null);
  const maxMentions = Math.max(1, ...items.map((p) => p.mencoes));

  return (
    <Card>
      <CardHeader>
        <CardTitle>O Gráfico de Produto</CardTitle>
        <CardSubtitle>Reclamações, gaps e elogios por produto citado nas reuniões — clique numa barra para ver as reuniões</CardSubtitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.length === 0 ? (
          <EmptyChart label="Nenhum produto citado no período." />
        ) : (
          <>
            <div className={`space-y-3 ${PRODUCT_LIST_HEIGHT}`}>
              {items.map((product) => (
                <ProductBar key={product.nome} product={product} maxMentions={maxMentions} onSelect={onSelectProduct} />
              ))}
            </div>
            {hasBreakdown && (
              <div className="flex items-center gap-4 pt-2 text-xs text-ink-secondary">
                <LegendDot color="bg-rose-500" label="Reclamações" />
                <LegendDot color="bg-amber-400" label="Gaps" />
                <LegendDot color="bg-emerald-500" label="Elogios" />
                <LegendDot color="bg-gray-300" label="Sem detalhamento" />
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ProductBar({ product, maxMentions, onSelect }: {
  product: ProductBreakdown;
  maxMentions: number;
  onSelect: (nome: string) => void;
}) {
  const { nome, mencoes, reclamacoes, gaps, elogios } = product;
  const hasDetail = reclamacoes != null || gaps != null || elogios != null;
  const total = (reclamacoes ?? 0) + (gaps ?? 0) + (elogios ?? 0);
  // Largura da barra escala pelas menções, para comparar volume entre produtos.
  const widthPct = Math.max(6, (mencoes / maxMentions) * 100);

  return (
    <div
      onClick={hasDetail && total > 0 ? () => onSelect(nome) : undefined}
      className={hasDetail && total > 0 ? "cursor-pointer group" : undefined}
      title={hasDetail && total > 0 ? `Ver reuniões de ${nome}` : undefined}
    >
      <div className="flex items-center justify-between text-xs mb-1">
        <span className="font-semibold text-ink truncate pr-2 group-hover:underline" title={nome}>{nome}</span>
        <span className="text-ink-muted flex-shrink-0 tabular-nums">{mencoes} menç{mencoes === 1 ? "ão" : "ões"}</span>
      </div>
      <div className="h-3.5 rounded-full bg-surface overflow-hidden flex" style={{ width: `${widthPct}%` }}>
        {hasDetail && total > 0 ? (
          <>
            {(reclamacoes ?? 0) > 0 && (
              <div
                className="h-full bg-rose-500 flex items-center justify-center text-white text-[9px] font-bold leading-none overflow-visible"
                style={{ width: `${((reclamacoes ?? 0) / total) * 100}%` }}
                title={`${reclamacoes} reclamações`}
              >
                {reclamacoes}
              </div>
            )}
            {(gaps ?? 0) > 0 && (
              <div
                className="h-full bg-amber-400 flex items-center justify-center text-white text-[9px] font-bold leading-none overflow-visible"
                style={{ width: `${((gaps ?? 0) / total) * 100}%` }}
                title={`${gaps} gaps`}
              >
                {gaps}
              </div>
            )}
            {(elogios ?? 0) > 0 && (
              <div
                className="h-full bg-emerald-500 flex items-center justify-center text-white text-[9px] font-bold leading-none overflow-visible"
                style={{ width: `${((elogios ?? 0) / total) * 100}%` }}
                title={`${elogios} elogios`}
              >
                {elogios}
              </div>
            )}
          </>
        ) : (
          <div className="h-full bg-gray-300 w-full" title="Sem detalhamento por reclamação/gap/elogio para este produto" />
        )}
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`w-2 h-2 rounded-full ${color}`} />
      {label}
    </span>
  );
}

/** Reuniões por trás dos números de um produto, agrupadas por reclamação/gap/
 * elogio — aberto ao clicar numa barra do Gráfico de Produto. */
function ProductMeetingsModal({ nome, onClose }: { nome: string; onClose: () => void }) {
  const { data, loading, error } = useAsync(() => dashboardService.productMeetings(nome), [nome]);
  const navigate = useNavigate();

  return (
    <>
      <div className="fixed inset-0 bg-black/25 backdrop-blur-[2px] z-40 animate-fade-in" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="product-meetings-title"
          className="pointer-events-auto w-full max-w-2xl max-h-[85vh] flex flex-col bg-white border border-gray-200 rounded-2xl shadow-2xl"
        >
          <div className="flex items-start justify-between gap-3 p-5 border-b border-surface-border flex-shrink-0">
            <div className="min-w-0">
              <h2 id="product-meetings-title" className="text-base font-bold text-ink truncate">{nome}</h2>
              <p className="text-xs text-ink-secondary mt-0.5">
                Reuniões que sustentam as reclamações, gaps e elogios deste produto
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-ink-muted hover:text-ink hover:bg-surface transition-colors flex-shrink-0"
            >
              <X size={16} />
            </button>
          </div>

          <div className="overflow-y-auto p-5 space-y-5">
            {loading ? (
              <div className="h-32 flex items-center justify-center gap-2 text-xs text-ink-muted">
                <Loader2 size={14} className="animate-spin" /> Carregando reuniões...
              </div>
            ) : error || !data ? (
              <p className="text-xs text-ink-secondary py-6 text-center">{error ?? "Não foi possível carregar as reuniões."}</p>
            ) : (
              <>
                <ProductMeetingGroup
                  label="Reclamações" color="text-rose-600" dot="bg-rose-500"
                  items={data.reclamacoes} onOpen={(id) => navigate(`/app/meetings/${id}`)}
                  emptyLabel="Nenhuma reclamação registrada para este produto."
                />
                <ProductMeetingGroup
                  label="Gaps" color="text-amber-600" dot="bg-amber-400"
                  items={data.gaps} onOpen={(id) => navigate(`/app/meetings/${id}`)}
                  emptyLabel="Nenhum gap registrado para este produto."
                />
                <ProductMeetingGroup
                  label="Elogios" color="text-emerald-600" dot="bg-emerald-500"
                  items={data.elogios} onOpen={(id) => navigate(`/app/meetings/${id}`)}
                  emptyLabel="Nenhum elogio registrado para este produto."
                />
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

function ProductMeetingGroup({ label, color, dot, items, onOpen, emptyLabel }: {
  label: string;
  color: string;
  dot: string;
  items: ProductMeetingItem[];
  onOpen: (analysisId: string) => void;
  emptyLabel: string;
}) {
  return (
    <div>
      <h3 className={`text-xs font-bold uppercase tracking-wide flex items-center gap-1.5 mb-2 ${color}`}>
        <span className={`w-2 h-2 rounded-full ${dot}`} />
        {label} ({items.length})
      </h3>
      {items.length === 0 ? (
        <p className="text-xs text-ink-muted">{emptyLabel}</p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div
              key={item.analysisId}
              onClick={() => onOpen(item.analysisId)}
              className="px-3 py-2 rounded-lg border border-surface-border hover:bg-surface cursor-pointer transition-colors"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-ink truncate">
                  Reunião {item.externalMeetingId}
                  {(item.uf || item.segmento) && (
                    <span className="text-ink-secondary font-normal">
                      {" "}({[item.uf, item.segmento].filter(Boolean).join(" · ")})
                    </span>
                  )}
                </p>
              </div>
              <ul className="mt-1 space-y-0.5">
                {item.itens.map((texto, i) => (
                  <li key={i} className="text-xs text-ink-secondary line-clamp-2">• {texto}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── 4. Temas e objeções ───────────────────────────────────────────────── */

// Recharts alinha o rótulo do eixo Y à direita por padrão (encostado nas
// barras) — como o texto é curto ("Gap", "Ação"), sobra um vão em branco à
// esquerda, antes do texto começar. Este tick customizado alinha o texto à
// esquerda, a poucos pixels da borda do card (x absoluto, não relativo ao `x`
// do tick — o `x` do tick é a posição da própria linha do eixo, rente às
// barras, e subtrair a largura do eixo dali jogava o texto para fora do SVG,
// que corta tudo que sai do viewport: cortava a primeira letra).
const THEME_AXIS_WIDTH = 150;

// O Recharts passa `y` como string | number: tipado só como number, o build quebrava.
function ThemeAxisTick({ y, payload }: { y?: string | number; payload?: { value?: string | number } }) {
  return (
    <text x={4} y={y} dy={4} textAnchor="start" fontSize={11} fill="#6B7280">
      {payload?.value}
    </text>
  );
}

function ThemesSection({ items }: { items: ThemeRanking[] }) {
  const chartData = items.map((t) => ({ ...t, label: themeLabel(t.tema) }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Temas e Objeções Detectados pela IA</CardTitle>
        <CardSubtitle>Categorias de evidência mais frequentes nas transcrições</CardSubtitle>
      </CardHeader>
      <CardContent>
        {chartData.length === 0 ? (
          <EmptyChart label="Sem evidências categorizadas suficientes." />
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(160, chartData.length * 32)}>
            <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 24, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" horizontal={false} />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 10, fill: "#9CA3AF" }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="label" width={THEME_AXIS_WIDTH} tick={ThemeAxisTick} axisLine={false} tickLine={false} />
              <Tooltip formatter={(v) => [`${v} ocorrências`, ""]} />
              <Bar dataKey="ocorrencias" fill={NEUTRAL_COLOR} radius={[0, 4, 4, 0]} barSize={16} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}

/* ── 5. Risco de churn por UF ──────────────────────────────────────────── */

function UfRiskSection({ items }: { items: UfRisk[] }) {
  const leader = items[0];
  const insight = leader && leader.riscoMedio > 0
    ? `${leader.uf} concentra o maior risco médio (${leader.riscoMedio}) entre ${leader.reunioes} ${leader.reunioes === 1 ? "reunião monitorada" : "reuniões monitoradas"}.`
    : null;
  const maxRisco = Math.max(1, ...items.map((u) => u.riscoMedio));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Risco de Churn por UF</CardTitle>
        <CardSubtitle>Estados ordenados pelo maior risco médio</CardSubtitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <EmptyChart label="Sem reuniões com UF identificada no período." />
        ) : (
          <div className={`flex flex-col justify-between gap-2.5 ${RANKING_LIST_HEIGHT}`}>
            {items.map((item) => (
              <div key={item.uf} className="flex items-center gap-3 flex-shrink-0">
                <span className="text-xs font-bold text-ink w-8 flex-shrink-0">{item.uf}</span>
                <div className="flex-1 h-3 rounded-full bg-surface overflow-hidden">
                  <div
                    className="h-full rounded-full bg-rose-500"
                    style={{ width: `${(item.riscoMedio / maxRisco) * 100}%` }}
                  />
                </div>
                <span className="text-xs font-bold text-ink tabular-nums w-9 text-right">{item.riscoMedio}</span>
                <span className="text-xs text-ink-muted tabular-nums w-16 text-right flex-shrink-0">
                  {item.reunioes} {item.reunioes === 1 ? "reunião" : "reuniões"}
                </span>
              </div>
            ))}
          </div>
        )}
        {insight && <p className="text-xs text-ink-secondary pt-2 mt-2 border-t border-surface-border">{insight}</p>}
      </CardContent>
    </Card>
  );
}

/* ── 6. Risco x oportunidade por segmento ──────────────────────────────── */

function SegmentSection({ items }: { items: SegmentRiskOpportunity[] }) {
  // Borboleta: risco e oportunidade divergem de uma coluna central de rótulos,
  // na mesma escala dos dois lados — assim o comprimento das barras é
  // comparável tanto entre segmentos quanto entre risco e oportunidade.
  const maxScore = Math.max(1, ...items.flatMap((s) => [s.riscoMedio, s.oportunidadeMedia]));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Risco x Oportunidade por Segmento</CardTitle>
        <CardSubtitle>Score médio de risco (esquerda) e de oportunidade (direita) por segmento</CardSubtitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <EmptyChart label="Sem reuniões com segmento identificado no período." />
        ) : (
          <>
            <div
              className={`grid items-center gap-y-3 gap-x-2 ${RANKING_LIST_HEIGHT}`}
              style={{ gridTemplateColumns: "1fr auto 1fr" }}
            >
              {items.map((item) => (
                <FragmentRow key={item.segmento} item={item} maxScore={maxScore} />
              ))}
            </div>
            <div className="flex items-center gap-4 pt-2 mt-1 text-xs text-ink-secondary">
              <LegendDot color="bg-rose-500" label="Risco médio" />
              <LegendDot color="bg-emerald-500" label="Oportunidade média" />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function FragmentRow({ item, maxScore }: { item: SegmentRiskOpportunity; maxScore: number }) {
  return (
    <>
      <div className="flex items-center justify-end gap-1.5">
        <span className="text-[10px] font-bold text-rose-600 tabular-nums flex-shrink-0">{item.riscoMedio}</span>
        <div className="h-4 flex justify-end" style={{ width: `${(item.riscoMedio / maxScore) * 100}%`, minWidth: item.riscoMedio > 0 ? 4 : 0 }}>
          <div className="h-full w-full rounded-l-md bg-rose-500" title={`Risco médio: ${item.riscoMedio}`} />
        </div>
      </div>

      <div className="flex flex-col items-center text-center px-1 min-w-[84px] max-w-[130px]">
        <span className="text-xs font-semibold text-ink truncate w-full" title={item.segmento}>{item.segmento}</span>
        <span className="text-[10px] text-ink-muted tabular-nums">
          {item.reunioes} {item.reunioes === 1 ? "reunião" : "reuniões"}
        </span>
      </div>

      <div className="flex items-center gap-1.5">
        <div className="h-4" style={{ width: `${(item.oportunidadeMedia / maxScore) * 100}%`, minWidth: item.oportunidadeMedia > 0 ? 4 : 0 }}>
          <div className="h-full w-full rounded-r-md bg-emerald-500" title={`Oportunidade média: ${item.oportunidadeMedia}`} />
        </div>
        <span className="text-[10px] font-bold text-emerald-600 tabular-nums flex-shrink-0">{item.oportunidadeMedia}</span>
      </div>
    </>
  );
}

/* ── Filtro do Top 5 (UF + segmento) ──────────────────────────────────── */

function Top5FilterBar({
  uf, segmento, ufOptions, segmentoOptions, onUfChange, onSegmentoChange,
}: {
  uf: string;
  segmento: string;
  ufOptions: string[];
  segmentoOptions: string[];
  onUfChange: (value: string) => void;
  onSegmentoChange: (value: string) => void;
}) {
  if (ufOptions.length === 0 && segmentoOptions.length === 0) return null;
  const hasFilter = Boolean(uf || segmento);
  return (
    <div className="flex flex-wrap items-center gap-2.5 -mb-1">
      <span className="text-xs font-semibold text-ink-secondary flex items-center gap-1.5 flex-shrink-0">
        <Filter size={13} /> Filtrar Top 5 por:
      </span>
      {ufOptions.length > 0 && (
        <FilterSelect label="Todas as UFs" value={uf} onChange={onUfChange} options={ufOptions} />
      )}
      {segmentoOptions.length > 0 && (
        <FilterSelect label="Todos os segmentos" value={segmento} onChange={onSegmentoChange} options={segmentoOptions} />
      )}
      {hasFilter && (
        <button
          onClick={() => { onUfChange(""); onSegmentoChange(""); }}
          className="flex items-center gap-1 text-xs text-ink-muted hover:text-ink transition-colors flex-shrink-0"
        >
          <X size={12} /> Limpar
        </button>
      )}
    </div>
  );
}

function FilterSelect({ label, value, onChange, options }: {
  label: string; value: string; onChange: (value: string) => void; options: string[];
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="appearance-none pl-3 pr-7 py-1.5 text-xs bg-white border border-surface-border rounded-lg focus:outline-none focus:ring-2 focus:ring-brand/20 focus:border-brand/30 cursor-pointer text-ink"
      >
        <option value="">{label}</option>
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
      <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-muted pointer-events-none" />
    </div>
  );
}

/* ── 7 & 8. Top 5 reuniões ─────────────────────────────────────────────── */

function RankedMeetingsSection({
  title, subtitle, icon, items, colorMode, emptyLabel, loading, error, onRetry,
}: {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  items: RankedMeeting[];
  colorMode: "risk" | "opportunity";
  emptyLabel: string;
  /** Carregando o Top 5 filtrado por UF/segmento (chamada extra, só quando há filtro). */
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}) {
  const navigate = useNavigate();
  return (
    <Card>
      <CardHeader className="flex items-center gap-2">
        {icon}
        <div>
          <CardTitle>{title}</CardTitle>
          <CardSubtitle>{subtitle}</CardSubtitle>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className={`flex items-center justify-center text-xs text-ink-muted ${RANKING_LIST_HEIGHT}`}>Aplicando filtro...</div>
        ) : error ? (
          <div className={`flex flex-col items-center justify-center gap-2 text-center ${RANKING_LIST_HEIGHT}`}>
            <p className="text-xs text-ink-secondary">{error}</p>
            {onRetry && <button onClick={onRetry} className="text-brand text-xs font-semibold hover:underline">Tentar novamente</button>}
          </div>
        ) : items.length === 0 ? (
          <p className={`text-sm text-ink-muted text-center flex items-center justify-center ${RANKING_LIST_HEIGHT}`}>{emptyLabel}</p>
        ) : <div className={`space-y-1 ${RANKING_LIST_HEIGHT}`}>{items.map((item) => (
          <div
            key={item.analysisId}
            onClick={() => navigate(`/app/meetings/${item.analysisId}`)}
            className="px-3 py-2.5 rounded-lg hover:bg-surface cursor-pointer transition-colors"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-ink truncate">
                Reunião {item.externalMeetingId}
                {(item.uf || item.segmento) && (
                  <span className="text-ink-secondary font-normal">
                    {" "}({[item.uf, item.segmento].filter(Boolean).join(" · ")})
                  </span>
                )}
              </p>
              <span className="text-sm font-extrabold text-ink tabular-nums flex-shrink-0">{item.score}</span>
            </div>
            <ScoreBar score={item.score} showLabel={false} size="xs" colorMode={colorMode} />
            {item.motivo && (
              <p className="text-xs text-ink-secondary mt-1 line-clamp-2">
                <span className="font-semibold">Motivo:</span> {item.motivo}
              </p>
            )}
          </div>
        ))}</div>}
      </CardContent>
    </Card>
  );
}

/* ── shared ────────────────────────────────────────────────────────────── */

function EmptyChart({ label }: { label: string }) {
  return (
    <div className="h-[120px] flex items-center justify-center text-xs text-ink-muted text-center px-4">
      {label}
    </div>
  );
}
