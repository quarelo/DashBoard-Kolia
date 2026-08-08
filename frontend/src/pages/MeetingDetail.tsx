import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ArrowLeft,
  Calendar,
  Clock,
  User,
  Building2,
  Tag,
  TrendingUp,
  TrendingDown,
  Minus,
  Star,
  AlertTriangle,
  Target,
  Package,
  Heart,
  Swords,
  MessageSquare,
  ChevronRight,
} from "lucide-react";
import {
  RadialBarChart,
  RadialBar,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { meetingsService } from "../services/meetingsService";
import { insightsService, translateType, translatePriority } from "../services/insightsService";
import type { Insight, InsightType, Sentiment } from "../types";
import { Badge } from "../components/ui/Badge";
import { ScoreBar } from "../components/ui/ScoreBar";
import { cn } from "../lib/utils";

/* ── Helpers ──────────────────────────────────────────────────── */
const sentimentConfig: Record<Sentiment, { label: string; icon: React.ReactNode; color: string; bg: string }> = {
  positive: {
    label: "Positivo",
    icon: <TrendingUp size={16} />,
    color: "text-emerald-600",
    bg: "bg-emerald-50 border-emerald-200",
  },
  neutral: {
    label: "Neutro",
    icon: <Minus size={16} />,
    color: "text-gray-500",
    bg: "bg-gray-100 border-gray-200",
  },
  negative: {
    label: "Negativo",
    icon: <TrendingDown size={16} />,
    color: "text-rose-600",
    bg: "bg-rose-50 border-rose-200",
  },
};

const typeIcons: Record<InsightType, React.ReactNode> = {
  churn_risk:           <AlertTriangle size={14} className="text-rose-500" />,
  upsell_opportunity:   <Target size={14} className="text-blue-500" />,
  product_feedback:     <Package size={14} className="text-violet-500" />,
  sentiment_alert:      <Heart size={14} className="text-pink-500" />,
  competitive_mention:  <Swords size={14} className="text-gray-500" />,
};

function NpsGauge({ nps }: { nps: number | null }) {
  if (nps === null) return <p className="text-gray-400 text-sm">NPS não disponível</p>;

  const color =
    nps >= 70 ? "#22c55e"
    : nps >= 50 ? "#3b82f6"
    : nps >= 30 ? "#f59e0b"
    : "#ef4444";

  const data = [{ value: nps, fill: color }];

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-28 h-28">
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart
            cx="50%"
            cy="50%"
            innerRadius="65%"
            outerRadius="100%"
            barSize={10}
            data={data}
            startAngle={90}
            endAngle={90 - (nps / 100) * 360}
          >
            <RadialBar dataKey="value" cornerRadius={5} background={{ fill: "#f3f4f6" }} />
            <Tooltip formatter={(v) => [`NPS: ${v}`, ""]} />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-black" style={{ color }}>{nps}</span>
          <span className="text-[10px] text-gray-400 font-medium">NPS</span>
        </div>
      </div>
      <p className="text-xs font-medium mt-1" style={{ color }}>
        {nps >= 70 ? "Promotor" : nps >= 50 ? "Neutro" : nps >= 30 ? "Atenção" : "Detrator"}
      </p>
    </div>
  );
}

function InsightRow({ insight, onClick }: { insight: Insight; onClick: () => void }) {
  return (
    <div
      onClick={onClick}
      className="flex items-start gap-3 p-4 rounded-xl border border-gray-200 hover:border-brand/30 hover:bg-brand/8/30 transition-all cursor-pointer group"
    >
      <div className="mt-0.5">{typeIcons[insight.type]}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          <Badge variant="type" type={insight.type}>{translateType(insight.type)}</Badge>
          <Badge variant="priority" priority={insight.priority}>{translatePriority(insight.priority)}</Badge>
        </div>
        <p className="text-sm text-gray-700 leading-relaxed line-clamp-2">{insight.summary}</p>
        <div className="mt-2 w-40">
          <ScoreBar score={insight.score} size="sm" />
        </div>
      </div>
      <ChevronRight size={15} className="text-gray-300 group-hover:text-brand transition-colors flex-shrink-0 mt-1" />
    </div>
  );
}

/* ── Main Component ───────────────────────────────────────────── */
export function MeetingDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const meeting = meetingsService.getById(id ?? "");

  if (!meeting) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-4">
        <p className="text-gray-400 text-lg">Reunião não encontrada.</p>
        <button onClick={() => navigate("/app/meetings")} className="text-brand text-sm hover:underline">
          Voltar para Reuniões
        </button>
      </div>
    );
  }

  const insights = meeting.insightIds
    .map((iid) => insightsService.getById(iid))
    .filter((i): i is Insight => Boolean(i));

  const sentiment = sentimentConfig[meeting.sentiment];
  const totvsPeople = meeting.participants.filter((p) => p.company === "TOTVS");
  const clientPeople = meeting.participants.filter((p) => p.company === "CLIENT");

  return (
    <div className="space-y-5 max-w-5xl">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <button
          onClick={() => navigate("/app/meetings")}
          className="flex items-center gap-1.5 hover:text-brand transition-colors"
        >
          <ArrowLeft size={15} />
          Reuniões
        </button>
        <span className="text-gray-300">/</span>
        <span className="text-gray-700 font-medium truncate">{meeting.title}</span>
      </div>

      {/* Page header */}
      <div className="bg-white border border-gray-200 rounded-2xl p-6">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-brand uppercase tracking-wider mb-1">
              {meeting.segment}
            </p>
            <h1 className="text-2xl font-bold text-gray-900 leading-tight mb-1">
              {meeting.title}
            </h1>
            <p className="text-sm text-gray-500">{meeting.client}</p>
          </div>
          <div className={cn("flex items-center gap-2 px-3 py-2 rounded-xl border text-sm font-semibold flex-shrink-0", sentiment.bg, sentiment.color)}>
            {sentiment.icon}
            {sentiment.label}
          </div>
        </div>

        {/* Meta grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t border-gray-100">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-brand/8 flex items-center justify-center flex-shrink-0">
              <Calendar size={14} className="text-brand" />
            </div>
            <div>
              <p className="text-xs text-gray-400">Data</p>
              <p className="text-sm font-semibold text-gray-800">
                {new Date(meeting.date).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" })}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-purple-50 flex items-center justify-center flex-shrink-0">
              <Clock size={14} className="text-purple-600" />
            </div>
            <div>
              <p className="text-xs text-gray-400">Duração</p>
              <p className="text-sm font-semibold text-gray-800">{meeting.duration} minutos</p>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-50 flex items-center justify-center flex-shrink-0">
              <User size={14} className="text-emerald-600" />
            </div>
            <div>
              <p className="text-xs text-gray-400">Responsável TOTVS</p>
              <p className="text-sm font-semibold text-gray-800">{meeting.totvsSalesperson}</p>
              <p className="text-xs text-gray-400">{meeting.totvsRole}</p>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-orange-50 flex items-center justify-center flex-shrink-0">
              <Building2 size={14} className="text-orange-600" />
            </div>
            <div>
              <p className="text-xs text-gray-400">Segmento</p>
              <p className="text-sm font-semibold text-gray-800">{meeting.segment}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Scores + NPS */}
      <div className="grid md:grid-cols-3 gap-4">
        {/* NPS Gauge */}
        <div className="bg-white border border-gray-200 rounded-2xl p-5 flex flex-col items-center justify-center gap-2">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">NPS do Cliente</p>
          <NpsGauge nps={meeting.nps} />
        </div>

        {/* Risk Score */}
        <div className="bg-white border border-gray-200 rounded-2xl p-5">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Score de Risco</p>
          <div className="flex items-end gap-3 mb-3">
            <span className="text-4xl font-black text-rose-500">{meeting.riskScore}</span>
            <span className="text-sm text-gray-400 mb-1">/100</span>
          </div>
          <ScoreBar score={meeting.riskScore} showLabel={false} />
          <p className="text-xs text-gray-400 mt-2">
            {meeting.riskScore >= 80 ? "Risco crítico — ação imediata necessária"
              : meeting.riskScore >= 60 ? "Risco alto — monitorar de perto"
              : meeting.riskScore >= 40 ? "Risco moderado"
              : "Risco baixo"}
          </p>
        </div>

        {/* Opportunity Score */}
        <div className="bg-white border border-gray-200 rounded-2xl p-5">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Score de Oportunidade</p>
          <div className="flex items-end gap-3 mb-3">
            <span className="text-4xl font-black text-blue-500">{meeting.opportunityScore}</span>
            <span className="text-sm text-gray-400 mb-1">/100</span>
          </div>
          <div className="bg-gray-100 rounded-full overflow-hidden h-2">
            <div
              className="h-full rounded-full bg-brand/80"
              style={{ width: `${meeting.opportunityScore}%` }}
            />
          </div>
          <p className="text-xs text-gray-400 mt-2">
            {meeting.opportunityScore >= 80 ? "Alta oportunidade — priorizar ação comercial"
              : meeting.opportunityScore >= 60 ? "Boa oportunidade — qualificar"
              : meeting.opportunityScore >= 40 ? "Oportunidade moderada"
              : "Potencial baixo no momento"}
          </p>
        </div>
      </div>

      {/* Transcript + Keywords */}
      <div className="grid md:grid-cols-3 gap-4">
        {/* Transcript snippet */}
        <div className="md:col-span-2 bg-white border border-gray-200 rounded-2xl p-5">
          <h3 className="text-sm font-bold text-gray-900 mb-3 flex items-center gap-2">
            <MessageSquare size={15} className="text-blue-500" />
            Trecho da Transcrição
          </h3>
          <blockquote className="border-l-4 border-brand/30 bg-brand/8 rounded-r-lg p-4">
            <p className="text-sm text-gray-700 italic leading-relaxed">
              "{meeting.transcriptSnippet}"
            </p>
          </blockquote>
        </div>

        {/* Keywords */}
        <div className="bg-white border border-gray-200 rounded-2xl p-5">
          <h3 className="text-sm font-bold text-gray-900 mb-3 flex items-center gap-2">
            <Tag size={15} className="text-violet-500" />
            Palavras-chave (TF-IDF)
          </h3>
          <div className="flex flex-wrap gap-2">
            {meeting.keywords.map((kw, i) => (
              <span
                key={kw}
                className="px-2.5 py-1 rounded-lg border text-xs font-medium"
                style={{
                  background: `rgba(59,130,246,${0.04 + (meeting.keywords.length - i) / meeting.keywords.length * 0.12})`,
                  borderColor: `rgba(59,130,246,${0.1 + (meeting.keywords.length - i) / meeting.keywords.length * 0.2})`,
                  color: "#1d4ed8",
                  fontSize: `${11 + (meeting.keywords.length - i) * 0.5}px`,
                }}
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Participants */}
      <div className="bg-white border border-gray-200 rounded-2xl p-5">
        <h3 className="text-sm font-bold text-gray-900 mb-4">Participantes</h3>
        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <p className="text-xs font-semibold text-brand uppercase tracking-wider mb-3">
              TOTVS ({totvsPeople.length})
            </p>
            <div className="space-y-2">
              {totvsPeople.map((p) => (
                <div key={p.name} className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-full gradient-brand flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                    {p.name[0]}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-800">{p.name}</p>
                    <p className="text-xs text-gray-400">{p.role}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
              {meeting.client} ({clientPeople.length})
            </p>
            <div className="space-y-2">
              {clientPeople.map((p) => (
                <div key={p.name} className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-gray-600 text-xs font-bold flex-shrink-0">
                    {p.name[0]}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-800">{p.name}</p>
                    <p className="text-xs text-gray-400">{p.role}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Tags */}
      {meeting.tags.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-400 font-medium">Tags:</span>
          {meeting.tags.map((tag) => (
            <span key={tag} className="px-2.5 py-1 bg-gray-100 text-gray-600 border border-gray-200 rounded-lg text-xs font-medium">
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Insights */}
      <div className="bg-white border border-gray-200 rounded-2xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-gray-900 flex items-center gap-2">
            <Star size={15} className="text-amber-400" />
            Insights Vinculados ({insights.length})
          </h3>
          <Link
            to="/app/insights"
            className="text-xs text-brand hover:text-brand font-medium flex items-center gap-1"
          >
            Ver todos os insights <ChevronRight size={12} />
          </Link>
        </div>

        {insights.length === 0 ? (
          <p className="text-sm text-gray-400 py-4 text-center">
            Nenhum insight vinculado a esta reunião.
          </p>
        ) : (
          <div className="space-y-3">
            {insights.map((insight) => (
              <InsightRow
                key={insight.id}
                insight={insight}
                onClick={() => navigate("/app/insights")}
              />
            ))}
          </div>
        )}
      </div>

      {/* Chat CTA */}
      <div className="bg-gradient-to-r from-brand to-brand-600 rounded-2xl p-5 flex items-center justify-between gap-4">
        <div>
          <p className="font-bold text-white mb-0.5">Analisar esta reunião com a IA</p>
          <p className="text-blue-100 text-sm">
            Faça perguntas específicas sobre {meeting.client} no Chat IA com contexto desta reunião.
          </p>
        </div>
        <Link
          to={`/app/chat?meetingId=${meeting.id}`}
          className="flex items-center gap-2 px-5 py-2.5 bg-white text-blue-700 font-semibold rounded-xl hover:bg-brand/8 transition-all text-sm flex-shrink-0 shadow-md"
        >
          <MessageSquare size={15} />
          Abrir Chat
        </Link>
      </div>
    </div>
  );
}
