import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  Calendar,
  Clock,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Minus,
  User,
  Tag,
  Filter,
  ChevronDown,
  Building2,
} from "lucide-react";
import { meetingsService } from "../services/meetingsService";
import { insightsService } from "../services/insightsService";
import type { Meeting, Sentiment } from "../types";
import { cn } from "../lib/utils";
import { ScoreBar } from "../components/ui/ScoreBar";
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const _unused = insightsService;

const allMeetings = meetingsService.getAll();

const sentimentConfig: Record<Sentiment, { label: string; icon: React.ReactNode; badge: string }> = {
  positive: {
    label: "Positivo",
    icon: <TrendingUp size={13} className="text-emerald-500" />,
    badge: "bg-emerald-50 text-emerald-700 border-emerald-200",
  },
  neutral: {
    label: "Neutro",
    icon: <Minus size={13} className="text-gray-400" />,
    badge: "bg-gray-100 text-gray-600 border-gray-200",
  },
  negative: {
    label: "Negativo",
    icon: <TrendingDown size={13} className="text-rose-500" />,
    badge: "bg-rose-50 text-rose-700 border-rose-200",
  },
};

const segments = ["Todos os segmentos", ...Array.from(new Set(allMeetings.map((m) => m.segment))).sort()];
const sentimentOptions = [
  { value: "all", label: "Qualquer sentimento" },
  { value: "positive", label: "Positivo" },
  { value: "neutral", label: "Neutro" },
  { value: "negative", label: "Negativo" },
];

function SentimentBadge({ sentiment }: { sentiment: Sentiment }) {
  const cfg = sentimentConfig[sentiment];
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border", cfg.badge)}>
      {cfg.icon}
      {cfg.label}
    </span>
  );
}

function NpsBadge({ nps }: { nps: number | null }) {
  if (nps === null) return <span className="text-xs text-gray-400">—</span>;
  const color =
    nps >= 70 ? "text-emerald-600 bg-emerald-50 border-emerald-200"
    : nps >= 50 ? "text-brand bg-brand/8 border-brand/30"
    : nps >= 30 ? "text-amber-600 bg-amber-50 border-amber-200"
    : "text-rose-600 bg-rose-50 border-rose-200";
  return (
    <span className={cn("inline-block px-2 py-0.5 rounded text-xs font-bold border", color)}>
      {nps}
    </span>
  );
}

function MeetingCard({ meeting }: { meeting: Meeting }) {
  const navigate = useNavigate();
  const insightCount = meeting.insightIds.length;
  const insights = meeting.insightIds.map((id) => insightsService.getById(id)).filter(Boolean);
  const maxRisk = Math.max(...insights.map((i) => i?.score ?? 0), 0);

  return (
    <div
      onClick={() => navigate(`/app/meetings/${meeting.id}`)}
      className="bg-white border border-gray-200 rounded-xl p-5 hover:shadow-md hover:border-brand/30 transition-all duration-200 cursor-pointer group"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-gray-400 mb-0.5">{meeting.segment}</p>
          <h3 className="font-bold text-gray-900 text-sm leading-snug group-hover:text-brand transition-colors truncate">
            {meeting.title}
          </h3>
        </div>
        <SentimentBadge sentiment={meeting.sentiment} />
      </div>

      {/* Meta */}
      <div className="flex flex-wrap gap-3 text-xs text-gray-500 mb-4">
        <span className="flex items-center gap-1.5">
          <Building2 size={12} className="text-gray-400" />
          {meeting.client}
        </span>
        <span className="flex items-center gap-1.5">
          <Calendar size={12} className="text-gray-400" />
          {new Date(meeting.date).toLocaleDateString("pt-BR")}
        </span>
        <span className="flex items-center gap-1.5">
          <Clock size={12} className="text-gray-400" />
          {meeting.duration} min
        </span>
        <span className="flex items-center gap-1.5">
          <User size={12} className="text-gray-400" />
          {meeting.totvsSalesperson}
        </span>
      </div>

      {/* Transcript snippet */}
      <p className="text-xs text-gray-500 leading-relaxed mb-4 line-clamp-2">
        {meeting.transcriptSnippet}
      </p>

      {/* Scores */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-gray-500">Risco</span>
            <span className="text-xs font-bold text-gray-700">{meeting.riskScore}</span>
          </div>
          <ScoreBar score={meeting.riskScore} showLabel={false} size="sm" />
        </div>
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-gray-500">Oportunidade</span>
            <span className="text-xs font-bold text-gray-700">{meeting.opportunityScore}</span>
          </div>
          <div className="bg-gray-100 rounded-full overflow-hidden h-1.5">
            <div
              className="h-full rounded-full bg-brand/80"
              style={{ width: `${meeting.opportunityScore}%` }}
            />
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">NPS:</span>
          <NpsBadge nps={meeting.nps} />
          {insightCount > 0 && (
            <span className="ml-1 px-2 py-0.5 bg-brand/8 text-brand border border-brand/30 text-xs rounded font-medium">
              {insightCount} insight{insightCount > 1 ? "s" : ""}
            </span>
          )}
        </div>
        <ChevronRight size={15} className="text-gray-300 group-hover:text-brand transition-colors" />
      </div>

      {/* Keywords */}
      {meeting.keywords.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-gray-100">
          {meeting.keywords.slice(0, 4).map((kw) => (
            <span key={kw} className="flex items-center gap-1 px-2 py-0.5 bg-gray-50 text-gray-500 border border-gray-200 rounded text-xs">
              <Tag size={9} />
              {kw}
            </span>
          ))}
          {meeting.keywords.length > 4 && (
            <span className="px-2 py-0.5 text-gray-400 text-xs">+{meeting.keywords.length - 4}</span>
          )}
        </div>
      )}
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
  const [search, setSearch] = useState("");
  const [segmentFilter, setSegmentFilter] = useState("Todos os segmentos");
  const [sentimentFilter, setSentimentFilter] = useState("all");
  const [sortField, setSortField] = useState<"date" | "riskScore" | "opportunityScore" | "nps">("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const stats = meetingsService.getStats();

  const filtered = useMemo(() => {
    let data = [...allMeetings];

    if (search) {
      const q = search.toLowerCase();
      data = data.filter(
        (m) =>
          m.client.toLowerCase().includes(q) ||
          m.title.toLowerCase().includes(q) ||
          m.totvsSalesperson.toLowerCase().includes(q) ||
          m.keywords.some((k) => k.toLowerCase().includes(q))
      );
    }

    if (segmentFilter !== "Todos os segmentos") {
      data = data.filter((m) => m.segment === segmentFilter);
    }

    if (sentimentFilter !== "all") {
      data = data.filter((m) => m.sentiment === sentimentFilter);
    }

    data.sort((a, b) => {
      let cmp = 0;
      if (sortField === "date") cmp = a.date.localeCompare(b.date);
      else if (sortField === "riskScore") cmp = a.riskScore - b.riskScore;
      else if (sortField === "opportunityScore") cmp = a.opportunityScore - b.opportunityScore;
      else if (sortField === "nps") cmp = (a.nps ?? -1) - (b.nps ?? -1);
      return sortDir === "asc" ? cmp : -cmp;
    });

    return data;
  }, [search, segmentFilter, sentimentFilter, sortField, sortDir]);

  function toggleSort(field: typeof sortField) {
    if (sortField === field) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortField(field); setSortDir("desc"); }
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Reuniões</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {filtered.length} de {allMeetings.length} reuniões · transcrições analisadas pela IA
        </p>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Total de Reuniões"     value={stats.total}       sub="transcrições processadas"  color="text-brand" />
        <StatCard label="Sentimento Positivo"   value={`${stats.positive}/${stats.total}`} sub="reuniões favoráveis" color="text-emerald-600" />
        <StatCard label="Sentimento Negativo"   value={`${stats.negative}/${stats.total}`} sub="exigem atenção"      color="text-rose-600" />
        <StatCard label="NPS Médio"             value={stats.avgNps}      sub="média dos clientes"        color="text-violet-600" />
      </div>

      {/* Filters */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 flex flex-wrap gap-3 items-center">
        {/* Search */}
        <div className="relative flex-1 min-w-52">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Buscar cliente, responsável, palavra-chave..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-brand/30 transition-all"
          />
        </div>

        {/* Segment */}
        <div className="relative">
          <Filter size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
          <select
            value={segmentFilter}
            onChange={(e) => setSegmentFilter(e.target.value)}
            className="appearance-none pl-9 pr-8 py-2 text-sm bg-white border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-brand/30 cursor-pointer"
          >
            {segments.map((s) => <option key={s}>{s}</option>)}
          </select>
          <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
        </div>

        {/* Sentiment */}
        <div className="relative">
          <select
            value={sentimentFilter}
            onChange={(e) => setSentimentFilter(e.target.value)}
            className="appearance-none pl-3 pr-8 py-2 text-sm bg-white border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-brand/30 cursor-pointer"
          >
            {sentimentOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
        </div>

        {/* Sort */}
        <div className="flex items-center gap-1.5 ml-auto flex-wrap">
          <span className="text-xs text-gray-400">Ordenar por:</span>
          {(["date", "riskScore", "opportunityScore", "nps"] as const).map((f) => {
            const labels: Record<typeof f, string> = {
              date: "Data",
              riskScore: "Risco",
              opportunityScore: "Oportunidade",
              nps: "NPS",
            };
            return (
              <button
                key={f}
                onClick={() => toggleSort(f)}
                className={cn(
                  "px-2.5 py-1 rounded-md text-xs font-medium border transition-all",
                  sortField === f
                    ? "gradient-brand text-white border-brand/30"
                    : "bg-white text-gray-600 border-gray-200 hover:border-brand/30"
                )}
              >
                {labels[f]}
                {sortField === f && (sortDir === "desc" ? " ↓" : " ↑")}
              </button>
            );
          })}
        </div>
      </div>

      {/* Grid */}
      {filtered.length === 0 ? (
        <div className="text-center py-16 text-sm text-gray-400 bg-white rounded-xl border border-gray-200">
          Nenhuma reunião encontrada com os filtros selecionados.
        </div>
      ) : (
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((meeting) => (
            <MeetingCard key={meeting.id} meeting={meeting} />
          ))}
        </div>
      )}
    </div>
  );
}
