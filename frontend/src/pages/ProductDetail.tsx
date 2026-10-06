import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { ArrowLeft, Package, TriangleAlert, AlertTriangle, MessageSquare } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { KpiCard } from "../components/ui/KpiCard";
import { Card, CardContent, CardHeader, CardTitle, CardSubtitle } from "../components/ui/Card";
import { EmptyChart } from "../components/ui/EmptyChart";
import { LegendDot } from "../components/ui/LegendDot";
import { ProductMeetingGroup } from "../components/products/ProductMeetingGroup";
import { GapCoverageSection } from "../components/products/GapCoverageSection";
import { GapNatureSection } from "../components/products/GapNatureSection";
import { QualityProfileSection } from "../components/products/QualityProfileSection";
import { dashboardService, formatMonthLabel } from "../services/dashboardService";
import { useAsync } from "../lib/useAsync";
import { PageError, PageLoader } from "../components/ui/PageState";
import type { ProductHealthMonth, ProductPersonaCount } from "../types";

export function ProductDetail() {
  const { nome } = useParams<{ nome: string }>();
  const navigate = useNavigate();

  // Só os endpoints de leitura pura do produto — os três somam ~0,3s. As
  // menções totais vinham de `executive.topProdutos`, o que custava agregar
  // todas as análises por um número só, e falhava para produto fora do Top 10.
  const { data, loading, error, reload } = useAsync(async () => {
    if (!nome) throw new Error("Produto não informado.");
    const [insights, meetings, quality] = await Promise.all([
      dashboardService.productInsights(nome),
      dashboardService.productMeetings(nome),
      dashboardService.productQuality(nome),
    ]);
    return { insights, meetings, quality };
  }, [nome]);

  // A cobertura pelo catálogo fica **fora** do Promise.all de propósito: ela
  // passa pela IA e embedda cada gap, o que custa ~0,3s com o texto já em cache
  // e alguns segundos na primeira vez de cada produto. Junto com as outras, a
  // página inteira voltaria a esperar pelo pior caso; separada, o resto
  // aparece na hora e só este card espera.
  const catalogue = useAsync(async () => {
    if (!nome) throw new Error("Produto não informado.");
    return dashboardService.productGapCoverage(nome);
  }, [nome]);

  if (!nome) return <PageError message="Produto não informado." />;
  if (loading) return <PageLoader label="Carregando produto..." />;
  if (error || !data) return <PageError message={error ?? "Sem dados."} onRetry={reload} />;

  const { insights, meetings, quality } = data;
  // Somado a partir de `saude_mensal` por ser a mesma fonte dos gráficos
  // abaixo, então o KPI e a barra do mês nunca discordam.
  const totals = insights.saudeMensal.reduce(
    (acc, m) => ({
      reclamacoes: acc.reclamacoes + m.reclamacoes,
      gaps: acc.gaps + m.gaps,
      elogios: acc.elogios + m.elogios,
    }),
    { reclamacoes: 0, gaps: 0, elogios: 0 },
  );

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <Link
          to="/app/products"
          className="inline-flex items-center gap-1.5 text-xs text-ink-secondary hover:text-ink transition-colors mb-2"
        >
          <ArrowLeft size={13} /> Voltar para Produtos
        </Link>
        <h1 className="text-2xl font-extrabold text-ink">{nome}</h1>
        <p className="text-sm text-ink-secondary mt-0.5">
          {insights.reunioesDetalhadas} {insights.reunioesDetalhadas === 1 ? "reunião cita" : "reuniões citam"} este
          produto sozinho — a mesma regra do Gráfico de Produto
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Menções totais"
          value={insights.mencoesTotais}
          caption={
            insights.mencoesTotais > insights.reunioesDetalhadas
              ? `${insights.reunioesDetalhadas} citam só este produto`
              : undefined
          }
          icon={<Package size={16} />}
          accent="brand"
        />
        <KpiCard label="Reclamações" value={totals.reclamacoes} icon={<TriangleAlert size={16} />} accent="rose" />
        <KpiCard label="Gaps" value={totals.gaps} icon={<AlertTriangle size={16} />} accent="amber" />
        <KpiCard label="Elogios" value={totals.elogios} icon={<MessageSquare size={16} />} accent="emerald" />
      </div>

      <CatalogueCoverageCard state={catalogue} />

      {/* Sem `items-start`: os dois cards esticam para a altura da linha, que é
          a do mais alto. Qual dos dois é o mais alto varia — o de qualidade
          cresce quando aparece o aviso de amostra pequena, o de natureza cresce
          com o número de categorias (mediana 2, máximo 8 na carga) — então os
          dois precisam saber se distribuir, e não só um. */}
      <div className="grid lg:grid-cols-2 gap-4">
        <QualityProfileSection profile={quality} />
        <GapNatureSection items={insights.naturezaGaps} />
      </div>

      <HealthTrendSection items={insights.saudeMensal} />

      <PersonaSection items={insights.personas} />

      <Card>
        <CardHeader>
          <CardTitle>Reclamações, Gaps e Elogios</CardTitle>
          <CardSubtitle>Reuniões por trás de cada item, citando este produto sozinho</CardSubtitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <ProductMeetingGroup
            label="Reclamações" color="text-rose-600" dot="bg-rose-500"
            items={meetings.reclamacoes} onOpen={(id) => navigate(`/app/meetings/${id}`)}
            emptyLabel="Nenhuma reclamação registrada para este produto."
          />
          <ProductMeetingGroup
            label="Gaps" color="text-amber-600" dot="bg-amber-400"
            items={meetings.gaps} onOpen={(id) => navigate(`/app/meetings/${id}`)}
            emptyLabel="Nenhum gap registrado para este produto."
          />
          <ProductMeetingGroup
            label="Elogios" color="text-emerald-600" dot="bg-emerald-500"
            items={meetings.elogios} onOpen={(id) => navigate(`/app/meetings/${id}`)}
            emptyLabel="Nenhum elogio registrado para este produto."
          />
        </CardContent>
      </Card>
    </div>
  );
}

/* ── Saúde mês a mês ───────────────────────────────────────────────────── */

function HealthTrendSection({ items }: { items: ProductHealthMonth[] }) {
  const chartData = items.map((m) => ({ ...m, label: formatMonthLabel(m.mes) }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Saúde do Produto Mês a Mês</CardTitle>
        <CardSubtitle>Reclamações, gaps e elogios ao longo do tempo</CardSubtitle>
      </CardHeader>
      <CardContent>
        {chartData.length === 0 ? (
          <EmptyChart label="Sem histórico mensal suficiente para este produto." />
        ) : (
          <>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={chartData} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#9CA3AF" }} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#9CA3AF" }} axisLine={false} tickLine={false} />
                <Tooltip />
                <Bar dataKey="reclamacoes" name="Reclamações" stackId="saude" fill="#f43f5e" />
                <Bar dataKey="gaps" name="Gaps" stackId="saude" fill="#fbbf24" />
                <Bar dataKey="elogios" name="Elogios" stackId="saude" fill="#22c55e" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="flex items-center gap-4 pt-2 text-xs text-ink-secondary">
              <LegendDot color="bg-rose-500" label="Reclamações" />
              <LegendDot color="bg-amber-400" label="Gaps" />
              <LegendDot color="bg-emerald-500" label="Elogios" />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/* ── Gap × catálogo (carrega sozinho: passa pela IA) ─────────────────── */

/** Casca de carregamento/erro do único card da página que depende da IA. Erro
 * aqui não derruba a página: o resto dos dados é leitura pura do banco e já
 * está na tela, então o card mostra o próprio erro com retry. */
function CatalogueCoverageCard({ state }: {
  state: ReturnType<typeof useAsync<Awaited<ReturnType<typeof dashboardService.productGapCoverage>>>>;
}) {
  if (state.loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Gaps com Produto no Catálogo</CardTitle>
          <CardSubtitle>Casando cada gap com os produtos TOTVS...</CardSubtitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2 animate-pulse">
            <div className="h-3 rounded-full bg-surface" />
            <div className="h-12 rounded-lg bg-surface" />
            <div className="h-12 rounded-lg bg-surface" />
          </div>
        </CardContent>
      </Card>
    );
  }
  if (state.error || !state.data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Gaps com Produto no Catálogo</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-ink-secondary">
            {state.error ?? "Não foi possível casar os gaps com o catálogo."}{" "}
            <button onClick={state.reload} className="text-brand font-semibold hover:underline">
              Tentar novamente
            </button>
          </p>
        </CardContent>
      </Card>
    );
  }
  return <GapCoverageSection coverage={state.data} />;
}

/* ── Personas ─────────────────────────────────────────────────────────── */

function PersonaSection({ items }: { items: ProductPersonaCount[] }) {
  const maxCount = Math.max(1, ...items.map((p) => p.ocorrencias));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Personas Envolvidas</CardTitle>
        <CardSubtitle>Quem, profissionalmente, fala deste produto nas reuniões</CardSubtitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <EmptyChart label="Sem persona identificada nas reuniões deste produto." />
        ) : (
          <div className="space-y-2.5 max-h-[280px] overflow-y-auto pr-1">
            {items.map((item) => (
              <div key={item.nome} className="flex items-center gap-3">
                <span className="text-xs font-semibold text-ink w-32 flex-shrink-0 truncate" title={item.nome}>
                  {item.nome}
                </span>
                <div className="flex-1 h-3 rounded-full bg-surface overflow-hidden">
                  <div
                    className="h-full rounded-full bg-violet-500"
                    style={{ width: `${(item.ocorrencias / maxCount) * 100}%` }}
                  />
                </div>
                <span className="text-xs font-bold text-ink tabular-nums w-6 text-right flex-shrink-0">
                  {item.ocorrencias}
                </span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
