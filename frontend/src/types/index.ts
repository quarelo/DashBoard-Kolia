export type Role = "SALES_DIRECTOR" | "USER";

export interface AuthUser {
  id: number;
  name: string;
  email: string;
  role: Role;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in_days: number;
}

/* ── Análises reais (vindas do banco via /api/dashboard) ─────────────── */

/** Classificação de sentimento que a IA produz. */
export type SentimentClass =
  | "positivo"
  | "neutro"
  | "negativo"
  | "misto"
  | "não identificado";

/** Categorias de evidência que a IA associa a cada trecho. */
export type EvidenceCategory =
  | "produto"
  | "persona"
  | "sentimento"
  | "churn"
  | "oportunidade"
  | "budget"
  | "gap"
  | "problema"
  | "dúvida"
  | "ação"
  | "evidência";

export interface Evidence {
  categoria: string;
  insight: string;
  trecho: string;
}

export interface FinalSummary {
  produto: string[];
  persona: string[];
  sentimento: { classificacao: SentimentClass; justificativa: string };
  risco_churn: { score: number; justificativa: string };
  score_oportunidade: { score: number; justificativa: string };
  oportunidade_comercial: string[];
  budget: { identificado: boolean; valor: string; contexto: string };
  gap_produto: string[];
  problemas_identificados: string[];
  feedback_produto: string[];
  evidencias: Evidence[];
  recomendacao_acao: string[];
  duvidas_em_aberto: string[];
}

/** Item da listagem de análises — projeção enxuta do backend. */
export interface AnalysisListItem {
  analysisId: string;
  externalMeetingId: string;
  meetingId: string | null;
  title: string;
  status: string;
  summaryStage: string;
  summaryIsFinal: boolean;
  totalChunks: number;
  createdAt: string;
  updatedAt: string;
  riskScore: number;
  riskReason: string;
  opportunityScore: number;
  opportunityReason: string;
  sentiment: SentimentClass;
  sentimentReason: string;
  products: string[];
  personas: string[];
  /** Metadados brutos da importação (colunas extras do CSV), quando houver. */
  metadata: Record<string, string>;
}

export interface AnalysisDetail extends AnalysisListItem {
  finalSummary: FinalSummary | null;
  transcription: string | null;
  totalTokens: number;
  errorMessage: string | null;
  summaryReady: boolean;
  ragReady: boolean;
}

export interface DashboardOverview {
  total: number;
  analyzed: number;
  processing: number;
  failed: number;
  avgRisk: number;
  avgOpportunity: number;
  highRiskCount: number;
  sentiment: Record<string, number>;
  riskBuckets: { baixo: number; medio: number; alto: number };
  topProducts: { name: string; count: number }[];
  recent: AnalysisListItem[];
}

/* ── Dashboard Executiva (GET /api/dashboard/executive) ──────────────── */

export interface ExecutiveKpis {
  totalReunioes: number;
  /** null quando nenhuma reunião do período tem DURACAO_MEETING numérico. */
  duracaoMediaMinutos: number | null;
  produtoMaisCitado: string | null;
  mencoesProdutoMaisCitado: number | null;
}

export interface MonthlyComparison {
  /** "YYYY-MM" — meses variam conforme os dados; nunca fixo. */
  mes: string;
  reunioes: number;
  riscoMedio: number;
  oportunidadeMedia: number;
}

/**
 * reclamacoes/gaps/elogios só existem quando a reunião cita exatamente um
 * produto (ver nota em `analysis_read.executive_overview`, backend) — em
 * reuniões com vários produtos citados não há como saber a qual eles se
 * referem, então os três campos vêm ausentes (não zerados).
 */
export interface ProductBreakdown {
  nome: string;
  mencoes: number;
  reclamacoes?: number;
  gaps?: number;
  elogios?: number;
}

export interface ThemeRanking {
  tema: string;
  ocorrencias: number;
}

export interface UfRisk {
  uf: string;
  riscoMedio: number;
  reunioes: number;
}

export interface SegmentRiskOpportunity {
  segmento: string;
  reunioes: number;
  riscoMedio: number;
  oportunidadeMedia: number;
}

export interface RankedMeeting {
  analysisId: string;
  externalMeetingId: string;
  /** Título da reunião — não há coluna de razão social/cliente na fonte. */
  titulo: string;
  uf: string | null;
  segmento: string | null;
  score: number;
  motivo: string;
}

export interface ExecutiveDashboard {
  kpis: ExecutiveKpis;
  comparativoMensal: MonthlyComparison[];
  topProdutos: ProductBreakdown[];
  temas: ThemeRanking[];
  topUfRisco: UfRisk[];
  topSegmentos: SegmentRiskOpportunity[];
  top5Risco: RankedMeeting[];
  top5Oportunidade: RankedMeeting[];
}

/* ── Insights derivados (a IA não tem entidade própria de insight) ───── */

export type Priority = "critical" | "high" | "medium" | "low";
export type InsightType =
  | "churn_risk"
  | "upsell_opportunity"
  | "product_feedback"
  | "sentiment_alert"
  | "competitive_mention";

/** Um insight = uma evidência/sinal extraído de uma análise. */
export interface DerivedInsight {
  id: string;
  analysisId: string;
  meetingTitle: string;
  type: InsightType;
  priority: Priority;
  score: number;
  category: string;
  summary: string;
  evidence: string;
  relatedProducts: string[];
  date: string;
}

/* ── Chat ───────────────────────────────────────────────────────────── */

export interface ChatCitation {
  chunk_id: string;
  chunk_index: number;
  excerpt: string;
  similarity: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  citations?: ChatCitation[];
  grounded?: boolean;
}
