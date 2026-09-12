import { apiRequest } from "../lib/api";
import type {
  AnalysisDetail,
  AnalysisListItem,
  DashboardOverview,
  ExecutiveDashboard,
  FinalSummary,
  Priority,
  SentimentClass,
} from "../types";

/* ── shapes cruas do backend ─────────────────────────────────────────── */
interface RawListItem {
  analysis_id: string;
  external_meeting_id: string;
  title: string;
  status: string;
  summary_stage: string;
  summary_is_final: boolean;
  total_chunks: number;
  created_at: string;
  updated_at: string;
  risk_score: number;
  risk_reason: string;
  opportunity_score: number;
  opportunity_reason: string;
  sentiment: SentimentClass;
  sentiment_reason: string;
  products: string[];
  personas: string[];
  meeting: { id: string; external_id: string; metadata: Record<string, string> } | null;
}

interface RawDetail extends RawListItem {
  final_summary: FinalSummary | Record<string, never> | null;
  error_message: string | null;
  total_tokens: number;
  transcription: string | null;
  summary_ready: boolean;
  rag_ready: boolean;
}

interface RawExecutiveDashboard {
  kpis: {
    total_reunioes: number;
    duracao_media_minutos: number | null;
    produto_mais_citado: string | null;
    mencoes_produto_mais_citado: number | null;
  };
  comparativo_mensal: { mes: string; reunioes: number; risco_medio: number; oportunidade_media: number }[];
  top_produtos: { nome: string; mencoes: number; reclamacoes?: number; gaps?: number; elogios?: number }[];
  temas: { tema: string; ocorrencias: number }[];
  top_uf_risco: { uf: string; risco_medio: number; reunioes: number }[];
  top_segmentos: { segmento: string; reunioes: number; risco_medio: number; oportunidade_media: number }[];
  top5_risco: RawRankedMeeting[];
  top5_oportunidade: RawRankedMeeting[];
}

interface RawRankedMeeting {
  analysis_id: string;
  external_meeting_id: string;
  titulo: string;
  uf: string | null;
  segmento: string | null;
  score: number;
  motivo: string;
}

interface RawOverview {
  total: number;
  analyzed: number;
  processing: number;
  failed: number;
  avg_risk: number;
  avg_opportunity: number;
  high_risk_count: number;
  sentiment: Record<string, number>;
  risk_buckets: { baixo: number; medio: number; alto: number };
  top_products: { name: string; count: number }[];
  recent: RawListItem[];
}

/* ── adapters ────────────────────────────────────────────────────────── */
function toListItem(raw: RawListItem): AnalysisListItem {
  return {
    analysisId: raw.analysis_id,
    externalMeetingId: raw.external_meeting_id,
    meetingId: raw.meeting?.id ?? null,
    title: raw.title,
    status: raw.status,
    summaryStage: raw.summary_stage,
    summaryIsFinal: raw.summary_is_final,
    totalChunks: raw.total_chunks,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    riskScore: raw.risk_score ?? 0,
    riskReason: raw.risk_reason ?? "",
    opportunityScore: raw.opportunity_score ?? 0,
    opportunityReason: raw.opportunity_reason ?? "",
    sentiment: raw.sentiment ?? "não identificado",
    sentimentReason: raw.sentiment_reason ?? "",
    products: raw.products ?? [],
    personas: raw.personas ?? [],
    metadata: raw.meeting?.metadata ?? {},
  };
}

function toDetail(raw: RawDetail): AnalysisDetail {
  const fs = raw.final_summary && Object.keys(raw.final_summary).length
    ? (raw.final_summary as FinalSummary)
    : null;
  return {
    ...toListItem(raw),
    finalSummary: fs,
    transcription: raw.transcription,
    totalTokens: raw.total_tokens ?? 0,
    errorMessage: raw.error_message,
    summaryReady: raw.summary_ready ?? raw.summary_is_final,
    ragReady: raw.rag_ready ?? false,
  };
}

function toRankedMeeting(raw: RawRankedMeeting) {
  return {
    analysisId: raw.analysis_id,
    externalMeetingId: raw.external_meeting_id,
    titulo: raw.titulo,
    uf: raw.uf,
    segmento: raw.segmento,
    score: raw.score,
    motivo: raw.motivo,
  };
}

/* ── API ─────────────────────────────────────────────────────────────── */
export const dashboardService = {
  async executive(filters?: { uf?: string; segmento?: string }): Promise<ExecutiveDashboard> {
    const params = new URLSearchParams();
    if (filters?.uf) params.set("uf", filters.uf);
    if (filters?.segmento) params.set("segmento", filters.segmento);
    const query = params.toString();
    const raw = await apiRequest<RawExecutiveDashboard>(`/api/dashboard/executive${query ? `?${query}` : ""}`);
    return {
      kpis: {
        totalReunioes: raw.kpis.total_reunioes,
        duracaoMediaMinutos: raw.kpis.duracao_media_minutos,
        produtoMaisCitado: raw.kpis.produto_mais_citado,
        mencoesProdutoMaisCitado: raw.kpis.mencoes_produto_mais_citado,
      },
      comparativoMensal: (raw.comparativo_mensal ?? []).map((m) => ({
        mes: m.mes, reunioes: m.reunioes, riscoMedio: m.risco_medio, oportunidadeMedia: m.oportunidade_media,
      })),
      topProdutos: (raw.top_produtos ?? []).map((p) => ({
        nome: p.nome, mencoes: p.mencoes, reclamacoes: p.reclamacoes, gaps: p.gaps, elogios: p.elogios,
      })),
      temas: raw.temas ?? [],
      topUfRisco: (raw.top_uf_risco ?? []).map((u) => ({
        uf: u.uf, riscoMedio: u.risco_medio, reunioes: u.reunioes,
      })),
      topSegmentos: (raw.top_segmentos ?? []).map((s) => ({
        segmento: s.segmento, reunioes: s.reunioes, riscoMedio: s.risco_medio, oportunidadeMedia: s.oportunidade_media,
      })),
      top5Risco: (raw.top5_risco ?? []).map(toRankedMeeting),
      top5Oportunidade: (raw.top5_oportunidade ?? []).map(toRankedMeeting),
    };
  },

  async overview(): Promise<DashboardOverview> {
    const raw = await apiRequest<RawOverview>("/api/dashboard/overview");
    return {
      total: raw.total,
      analyzed: raw.analyzed,
      processing: raw.processing,
      failed: raw.failed,
      avgRisk: raw.avg_risk,
      avgOpportunity: raw.avg_opportunity,
      highRiskCount: raw.high_risk_count,
      sentiment: raw.sentiment ?? {},
      riskBuckets: raw.risk_buckets ?? { baixo: 0, medio: 0, alto: 0 },
      topProducts: raw.top_products ?? [],
      recent: (raw.recent ?? []).map(toListItem),
    };
  },

  async list(offset = 0, limit = 100): Promise<{ total: number; items: AnalysisListItem[] }> {
    const raw = await apiRequest<{ total: number; items: RawListItem[] }>(
      `/api/dashboard/meetings?offset=${offset}&limit=${limit}`,
    );
    return { total: raw.total, items: (raw.items ?? []).map(toListItem) };
  },

  async detail(analysisId: string): Promise<AnalysisDetail> {
    const raw = await apiRequest<RawDetail>(`/api/dashboard/meetings/${analysisId}`);
    return toDetail(raw);
  },

  /** Exclui a reunião: a análise, os trechos, o chat e a importação. */
  async remove(analysisId: string): Promise<void> {
    await apiRequest<void>(`/api/dashboard/meetings/${analysisId}`, { method: "DELETE" });
  },
};

/* ── helpers de apresentação ─────────────────────────────────────────── */
export const sentimentLabels: Record<SentimentClass, string> = {
  positivo: "Positivo",
  neutro: "Neutro",
  negativo: "Negativo",
  misto: "Misto",
  "não identificado": "Não identificado",
};

export const sentimentTone: Record<SentimentClass, string> = {
  positivo: "text-emerald-600 bg-emerald-50 border-emerald-200",
  neutro: "text-gray-600 bg-gray-100 border-gray-200",
  negativo: "text-rose-600 bg-rose-50 border-rose-200",
  misto: "text-amber-600 bg-amber-50 border-amber-200",
  "não identificado": "text-gray-400 bg-gray-50 border-gray-200",
};

export function riskPriority(score: number): Priority {
  if (score >= 67) return "critical";
  if (score >= 34) return "high";
  if (score >= 1) return "medium";
  return "low";
}

export function riskLabel(score: number): string {
  if (score >= 80) return "Risco crítico — ação imediata";
  if (score >= 60) return "Risco alto — monitorar de perto";
  if (score >= 34) return "Risco moderado";
  if (score >= 1) return "Risco baixo";
  return "Sem sinal de risco";
}

export function opportunityLabel(score: number): string {
  if (score >= 80) return "Alta oportunidade — priorizar ação comercial";
  if (score >= 60) return "Boa oportunidade — qualificar";
  if (score >= 34) return "Oportunidade moderada";
  if (score >= 1) return "Oportunidade incipiente";
  return "Sem oportunidade explícita";
}

const STATUS_LABELS: Record<string, string> = {
  DONE: "Concluída",
  EMBEDDING: "Indexando",
  DASHBOARD_READY: "Resumo pronto",
  ANALYZING: "Analisando",
  PROCESSING: "Processando",
  PENDING: "Na fila",
  FAILED: "Falhou",
  FAILED_ANALYSIS: "Falhou",
  DASHBOARD_READY_WITH_EMBEDDING_ERROR: "Resumo pronto (erro no índice)",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export const evidenceCategoryLabels: Record<string, string> = {
  produto: "Produto",
  persona: "Persona",
  sentimento: "Sentimento",
  churn: "Risco de churn",
  oportunidade: "Oportunidade",
  budget: "Budget",
  gap: "Gap de produto",
  problema: "Problema",
  feedback: "Feedback de produto",
  "dúvida": "Dúvida em aberto",
  "ação": "Próxima ação",
  "evidência": "Evidência",
};

/** Rótulo amigável para um tema/categoria; categorias fora do catálogo
 * controlado (evidências geradas fora do fluxo padrão) aparecem como vieram,
 * só com a inicial maiúscula — não tentamos adivinhar um nome melhor. */
export function themeLabel(tema: string): string {
  const known = evidenceCategoryLabels[tema.toLowerCase()];
  if (known) return known;
  return tema.charAt(0).toUpperCase() + tema.slice(1);
}

const MONTH_ABBR = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];

/** "2025-03" → "Mar/25". Não assume quais/quantos meses existem. */
export function formatMonthLabel(mes: string): string {
  const [year, month] = mes.split("-");
  const abbr = MONTH_ABBR[Number(month) - 1];
  return abbr ? `${abbr}/${year.slice(2)}` : mes;
}

/** 69.9 → "1h 10min"; 45 → "45 min". */
export function formatDuration(minutes: number): string {
  const rounded = Math.round(minutes);
  if (rounded < 60) return `${rounded} min`;
  const hours = Math.floor(rounded / 60);
  const rest = rounded % 60;
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}min`;
}
