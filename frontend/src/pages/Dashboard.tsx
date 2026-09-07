import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from "recharts";
import { FileText, AlertTriangle, TrendingUp, Activity, ArrowRight, Package } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { KpiCard } from "../components/ui/KpiCard";
import { Card, CardContent, CardHeader, CardTitle, CardSubtitle } from "../components/ui/Card";
import { dashboardService, sentimentLabels } from "../services/dashboardService";
import { useAsync } from "../lib/useAsync";
import { PageError, PageLoader } from "../components/ui/PageState";
import type { AnalysisListItem, SentimentClass } from "../types";

const BRAND = "#E76B38";

const SENTIMENT_COLOR: Record<string, string> = {
  positivo: "#22c55e",
  neutro: "#9CA3AF",
  negativo: "#ef4444",
  misto: "#f59e0b",
  "não identificado": "#D1D5DB",
};

const RISK_BUCKET = [
  { key: "alto", label: "Alto", fill: "#ef4444" },
  { key: "medio", label: "Médio", fill: "#f59e0b" },
  { key: "baixo", label: "Baixo / sem sinal", fill: "#22c55e" },
] as const;

function SentimentDot({ sentiment }: { sentiment: SentimentClass }) {
  return (
    <span
      className="inline-block w-2 h-2 rounded-full flex-shrink-0"
      style={{ background: SENTIMENT_COLOR[sentiment] ?? "#D1D5DB" }}
    />
  );
}

export function Dashboard() {
  const navigate = useNavigate();
  const { data, loading, error, reload } = useAsync(() => dashboardService.overview(), []);

  if (loading) return <PageLoader label="Carregando análises..." />;
  if (error || !data) return <PageError message={error ?? "Sem dados."} onRetry={reload} />;

  const riskData = RISK_BUCKET
    .map((b) => ({ name: b.label, value: data.riskBuckets[b.key], fill: b.fill }))
    .filter((d) => d.value > 0);

  const sentimentData = Object.entries(data.sentiment)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => ({ name: sentimentLabels[k as SentimentClass] ?? k, value: v, fill: SENTIMENT_COLOR[k] ?? "#D1D5DB" }));

  const productData = data.topProducts.slice(0, 6).map((p) => ({
    product: p.name.length > 22 ? p.name.slice(0, 21) + "…" : p.name,
    mentions: p.count,
  }));

  const opportunities = data.recent.filter((r) => r.opportunityScore > 0).length;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-ink">Dashboard Executivo</h1>
          <p className="text-sm text-ink-secondary mt-0.5">
            Transcrições analisadas pela IA · {data.total} {data.total === 1 ? "reunião" : "reuniões"}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-ink-secondary">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          Dados do banco
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Reuniões Analisadas" value={data.analyzed} icon={<FileText size={16} />} accent="brand" />
        <KpiCard label="Reuniões em Risco Alto" value={data.highRiskCount} icon={<AlertTriangle size={16} />} accent="rose" />
        <KpiCard label="Com Oportunidade" value={opportunities} icon={<TrendingUp size={16} />} accent="emerald" />
        <KpiCard label="Risco Médio" value={data.avgRisk} icon={<Activity size={16} />} accent="violet" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Distribuição de Risco de Churn</CardTitle>
            <CardSubtitle>Por faixa de score</CardSubtitle>
          </CardHeader>
          <CardContent>
            {riskData.length === 0 ? (
              <EmptyChart />
            ) : (
              <div className="flex items-center gap-3">
                <ResponsiveContainer width="55%" height={170}>
                  <PieChart>
                    <Pie data={riskData} innerRadius={44} outerRadius={72} paddingAngle={3} dataKey="value">
                      {riskData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                    </Pie>
                    <Tooltip formatter={(v) => [`${v} reuniões`, ""]} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-2.5 flex-1">
                  {riskData.map((item) => (
                    <div key={item.name} className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: item.fill }} />
                      <span className="text-xs text-ink-secondary flex-1">{item.name}</span>
                      <span className="text-xs font-bold text-ink tabular-nums">{item.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Sentimento das Reuniões</CardTitle>
            <CardSubtitle>Classificação da IA</CardSubtitle>
          </CardHeader>
          <CardContent>
            {sentimentData.length === 0 ? (
              <EmptyChart />
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={sentimentData} margin={{ top: 0, right: 0, left: -18, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#9CA3AF" }} axisLine={false} tickLine={false} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#9CA3AF" }} axisLine={false} tickLine={false} />
                  <Tooltip formatter={(v) => [`${v} reuniões`, ""]} />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {sentimentData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="flex items-center gap-2">
            <Package size={15} className="text-brand" />
            <div>
              <CardTitle>Produtos Mais Citados</CardTitle>
              <CardSubtitle>Contagem de reuniões que mencionam</CardSubtitle>
            </div>
          </CardHeader>
          <CardContent>
            {productData.length === 0 ? (
              <EmptyChart />
            ) : (
              <ResponsiveContainer width="100%" height={Math.max(160, productData.length * 34)}>
                <BarChart data={productData} layout="vertical" margin={{ top: 0, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" horizontal={false} />
                  <XAxis type="number" allowDecimals={false} tick={{ fontSize: 10, fill: "#9CA3AF" }} axisLine={false} tickLine={false} />
                  <YAxis type="category" dataKey="product" width={140} tick={{ fontSize: 10, fill: "#6B7280" }} axisLine={false} tickLine={false} />
                  <Tooltip formatter={(v) => [`${v} reuniões`, ""]} />
                  <Bar dataKey="mentions" fill={BRAND} radius={[0, 4, 4, 0]} barSize={16} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex items-center justify-between">
            <div>
              <CardTitle>Reuniões Recentes</CardTitle>
              <CardSubtitle>Últimas transcrições processadas</CardSubtitle>
            </div>
            <button onClick={() => navigate("/app/meetings")}
              className="flex items-center gap-1 text-xs text-brand hover:text-brand-600 font-semibold transition-colors">
              Ver todas <ArrowRight size={12} />
            </button>
          </CardHeader>
          <CardContent className="pt-0 space-y-1">
            {data.recent.length === 0 ? (
              <p className="text-sm text-ink-muted py-6 text-center">Nenhuma análise ainda.</p>
            ) : data.recent.map((m: AnalysisListItem) => (
              <div
                key={m.analysisId}
                onClick={() => navigate(`/app/meetings/${m.analysisId}`)}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-surface cursor-pointer transition-colors group"
              >
                <SentimentDot sentiment={m.sentiment} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-ink group-hover:text-brand truncate transition-colors">
                    {m.title}
                  </p>
                  <p className="text-xs text-ink-secondary truncate">
                    {m.products.slice(0, 2).join(" · ") || `${m.totalChunks} trechos analisados`}
                  </p>
                </div>
                <div className="flex items-center gap-3 text-xs flex-shrink-0">
                  <span className="text-rose-500 font-semibold tabular-nums" title="Risco de churn">R {m.riskScore}</span>
                  <span className="text-blue-500 font-semibold tabular-nums" title="Oportunidade">O {m.opportunityScore}</span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function EmptyChart() {
  return (
    <div className="h-[170px] flex items-center justify-center text-xs text-ink-muted">
      Sem dados suficientes para este gráfico.
    </div>
  );
}
