import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area, Legend, RadarChart, PolarGrid,
  PolarAngleAxis, Radar,
} from "recharts";
import { FileText, AlertTriangle, TrendingUp, Star, Clock, ArrowRight } from "lucide-react";
import { KpiCard } from "../components/ui/KpiCard";
import { Card, CardContent, CardHeader, CardTitle, CardSubtitle } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { PriorityDot } from "../components/ui/Badge";
import { insightsService, translateType } from "../services/insightsService";
import { meetingsService } from "../services/meetingsService";
import { useNavigate } from "react-router-dom";
import type { Insight } from "../types";

/* ── chart data ─────────────────────────────────────────────── */
const riskData         = insightsService.getRiskDistribution();
const opportunitiesData = insightsService.getOpportunitiesByCategory();
const sentimentData    = meetingsService.getSentimentTimeline();
const productData      = meetingsService.getProductMentions();
const recentInsights   = insightsService.getAll().slice(0, 5);
const recentMeetings   = meetingsService.getRecentMeetings(5);

const BRAND   = "#E76B38";
const BRAND20 = "#E76B3833";

/* ── custom tooltip ────────────────────────────────────────── */
function ChartTooltip({ active, payload, label }: {
  active?: boolean; label?: string;
  payload?: { value: number; name: string; color: string }[];
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-surface-border rounded-lg shadow-card-md px-3 py-2.5 text-xs">
      {label && <p className="font-semibold text-ink mb-1">{label}</p>}
      {payload.map((e, i) => (
        <p key={i} className="text-ink-secondary">
          <span className="font-medium" style={{ color: e.color }}>{e.name}: </span>
          <span className="font-bold text-ink">{e.value}</span>
        </p>
      ))}
    </div>
  );
}

function SentimentDot({ sentiment }: { sentiment: Insight["priority"] | string }) {
  const map: Record<string, string> = {
    positive: "bg-emerald-500",
    neutral:  "bg-slate-300",
    negative: "bg-rose-500",
  };
  return <span className={`inline-block w-2 h-2 rounded-full flex-shrink-0 ${map[sentiment] ?? "bg-slate-300"}`} />;
}

/* ── page ───────────────────────────────────────────────────── */
export function Dashboard() {
  const navigate = useNavigate();

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-ink">Dashboard Executivo</h1>
          <p className="text-sm text-ink-secondary mt-0.5">
            Visão geral · Atualizado em {new Date().toLocaleDateString("pt-BR", { day:"2-digit", month:"long", year:"numeric" })}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-ink-secondary">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          Dados ao vivo
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Reuniões Analisadas" value="500"  change={12}  changeLabel="vs. mês anterior" icon={<FileText size={16}/>}    accent="brand" />
        <KpiCard label="Clientes em Risco"   value="3"    change={-8}  changeLabel="vs. mês anterior" icon={<AlertTriangle size={16}/>} accent="rose" />
        <KpiCard label="Oportunidades"        value="47"   change={23}  changeLabel="vs. mês anterior" icon={<TrendingUp size={16}/>}   accent="emerald" />
        <KpiCard label="NPS Médio"            value="72"   change={4}   changeLabel="vs. mês anterior" icon={<Star size={16}/>}         accent="violet" />
      </div>

      {/* Charts row 1 */}
      <div className="grid lg:grid-cols-3 gap-4">
        {/* Pie — Distribuição de Riscos */}
        <Card>
          <CardHeader>
            <CardTitle>Distribuição de Riscos</CardTitle>
            <CardSubtitle>Por nível de prioridade</CardSubtitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <ResponsiveContainer width="55%" height={160}>
                <PieChart>
                  <Pie data={riskData} innerRadius={44} outerRadius={72} paddingAngle={3} dataKey="value">
                    {riskData.map((e, i) => <Cell key={i} fill={e.fill} />)}
                  </Pie>
                  <Tooltip formatter={(v) => [`${v} insights`, ""]} />
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
          </CardContent>
        </Card>

        {/* Bar — Oportunidades por categoria */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Oportunidades por Categoria</CardTitle>
            <CardSubtitle>Volume e score médio</CardSubtitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={opportunitiesData} margin={{ top:0, right:0, left:-18, bottom:0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" vertical={false} />
                <XAxis dataKey="category" tick={{ fontSize:10, fill:"#9CA3AF" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize:10, fill:"#9CA3AF" }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="count" name="Qtd."       fill={BRAND}   radius={[4,4,0,0]} />
                <Bar dataKey="value" name="Score médio" fill={BRAND20} radius={[4,4,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Charts row 2 */}
      <div className="grid lg:grid-cols-3 gap-4">
        {/* Area — Sentimento */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Evolução do Sentimento</CardTitle>
            <CardSubtitle>Distribuição mensal · Jan–Jun 2026</CardSubtitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={190}>
              <AreaChart data={sentimentData} margin={{ top:0, right:0, left:-18, bottom:0 }}>
                <defs>
                  {[
                    { id:"pos", color:"#22c55e" },
                    { id:"neu", color:"#9CA3AF" },
                    { id:"neg", color:"#ef4444" },
                  ].map(({ id, color }) => (
                    <linearGradient key={id} id={id} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={color} stopOpacity={0.25} />
                      <stop offset="95%" stopColor={color} stopOpacity={0} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize:11, fill:"#9CA3AF" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize:11, fill:"#9CA3AF" }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontSize:11 }} formatter={(v) => v === "positive" ? "Positivo" : v === "neutral" ? "Neutro" : "Negativo"} />
                <Area type="monotone" dataKey="positive" stroke="#22c55e" fill="url(#pos)" strokeWidth={2} />
                <Area type="monotone" dataKey="neutral"  stroke="#9CA3AF" fill="url(#neu)" strokeWidth={2} />
                <Area type="monotone" dataKey="negative" stroke="#ef4444" fill="url(#neg)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Radar — Produtos */}
        <Card>
          <CardHeader>
            <CardTitle>Produtos Mencionados</CardTitle>
            <CardSubtitle>Positivo vs. Negativo</CardSubtitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={190}>
              <RadarChart data={productData.slice(0, 5)}>
                <PolarGrid stroke="#F3F4F6" />
                <PolarAngleAxis dataKey="product" tick={{ fontSize:9, fill:"#9CA3AF" }} />
                <Radar name="Positivo" dataKey="positive" stroke={BRAND}   fill={BRAND}   fillOpacity={0.2} />
                <Radar name="Negativo" dataKey="negative" stroke="#ef4444" fill="#ef4444" fillOpacity={0.15} />
                <Legend wrapperStyle={{ fontSize:11 }} />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Bottom tables */}
      <div className="grid lg:grid-cols-2 gap-4">
        {/* Recent insights */}
        <Card>
          <CardHeader className="flex items-center justify-between">
            <div>
              <CardTitle>Insights Recentes</CardTitle>
              <CardSubtitle>Últimas análises geradas</CardSubtitle>
            </div>
            <button onClick={() => navigate("/app/insights")}
              className="flex items-center gap-1 text-xs text-brand hover:text-brand-600 font-semibold transition-colors">
              Ver todos <ArrowRight size={12} />
            </button>
          </CardHeader>
          <CardContent className="pt-0 space-y-1">
            {recentInsights.map((insight) => (
              <div
                key={insight.id}
                onClick={() => navigate("/app/insights")}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-surface cursor-pointer transition-colors group"
              >
                <PriorityDot priority={insight.priority} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-ink group-hover:text-brand truncate transition-colors">
                    {insight.client}
                  </p>
                  <p className="text-xs text-ink-secondary truncate">{insight.summary.slice(0, 52)}…</p>
                </div>
                <Badge variant="type" type={insight.type}>
                  {translateType(insight.type).split(" ")[0]}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Recent meetings */}
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
            {recentMeetings.map((m) => (
              <div
                key={m.id}
                onClick={() => navigate(`/app/meetings/${m.id}`)}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-surface cursor-pointer transition-colors group"
              >
                <SentimentDot sentiment={m.sentiment} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-ink group-hover:text-brand truncate transition-colors">
                    {m.client}
                  </p>
                  <p className="text-xs text-ink-secondary truncate">{m.title}</p>
                </div>
                <div className="flex items-center gap-1 text-xs text-ink-muted flex-shrink-0">
                  <Clock size={11} />
                  {m.duration}min
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
