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

export interface ProductMeetingItem {
  analysisId: string;
  externalMeetingId: string;
  titulo: string;
  uf: string | null;
  segmento: string | null;
  itens: string[];
}

export interface ProductMeetings {
  produto: string;
  reclamacoes: ProductMeetingItem[];
  gaps: ProductMeetingItem[];
  elogios: ProductMeetingItem[];
}

/* ── Página de Produto (GET /api/dashboard/products/{nome}/insights) ─── */

export interface ProductHealthMonth {
  /** "YYYY-MM" — meses variam conforme os dados; nunca fixo. */
  mes: string;
  reunioes: number;
  reclamacoes: number;
  gaps: number;
  elogios: number;
}

/**
 * Quantos gaps deste produto caem em cada categoria de vocabulário. Conta
 * **itens**, não reuniões — é o que dá material para um gráfico quando a
 * mediana é de uma reunião detalhada por produto. A categoria
 * "Não classificado" é parte do dado, não um erro: o tamanho dela é o aviso de
 * que a taxonomia (85,2% de cobertura na carga medida) não pega tudo.
 */
export interface ProductGapNature {
  categoria: string;
  ocorrencias: number;
}

export interface ProductPersonaCount {
  nome: string;
  ocorrencias: number;
}

/**
 * Mesma limitação de `ProductBreakdown`: só conta reunião que cita este
 * produto sozinho — ver nota em `analysis_read.product_insights` (backend).
 */
export interface ProductInsights {
  produto: string;
  /**
   * Toda reunião que cita o produto, inclusive junto com outros — a exceção à
   * regra de produto único acima, e sempre `>= reunioesDetalhadas`. É o mesmo
   * número de `ProductBreakdown.mencoes`, servido aqui para a Página de Produto
   * não precisar carregar o `/executive` inteiro por um KPI.
   */
  mencoesTotais: number;
  reunioesDetalhadas: number;
  saudeMensal: ProductHealthMonth[];
  naturezaGaps: ProductGapNature[];
  personas: ProductPersonaCount[];
}

/* ── Perfil de qualidade (GET /api/dashboard/products/{nome}/quality) ── */

export interface ProductQualityMetric {
  chave: string;
  rotulo: string;
  valor: number;
  mediaPortfolio: number;
  /** De que lado está o bom: 10 pontos acima da média é ótimo em oportunidade
   * e péssimo em risco de churn, e a barra divergente precisa saber disso. */
  maiorEMelhor: boolean;
}

/**
 * O produto em cinco métricas, cada uma contra a média do portfólio. A
 * comparação é o ponto: com mediana de uma reunião detalhada por produto, um
 * valor solto não diz nada e um desvio da média diz. Daí `reunioes` vir sempre
 * — a tela precisa poder avisar quando o número sai de uma reunião só.
 */
export interface ProductQualityProfile {
  produto: string;
  reunioes: number;
  reunioesPortfolio: number;
  metricas: ProductQualityMetric[];
}

/* ── Gap × catálogo (GET /api/dashboard/products/{nome}/gap-coverage) ── */

export type GapCoverageLevel = "provavel" | "possivel" | "sem_cobertura";

export interface GapCoverageProduct {
  nome: string;
  url: string;
  distancia: number;
}

export interface GapCoverageItem {
  gap: string;
  cobertura: GapCoverageLevel;
  distancia: number | null;
  margem: number | null;
  /** Vazio quando `cobertura` é "sem_cobertura": a tela não deve mostrar
   * palpite ao lado de um rótulo que diz que não há match. */
  produtos: GapCoverageProduct[];
}

/**
 * Quais gaps apontados neste produto já têm produto no catálogo TOTVS —
 * cross-sell quando sim, pauta de roadmap quando não. Os rótulos são
 * "provável" e "possível", nunca "coberto": o casamento é por vizinhança de
 * embedding, e a faixa do meio acertou cerca de metade na amostra manual.
 */
export interface ProductGapCoverage {
  produto: string;
  itens: GapCoverageItem[];
  resumo: Record<GapCoverageLevel, number>;
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

/* ── Régua de pontuação (pesos editáveis de churn e oportunidade) ────── */

/** Qual score o motivo alimenta. O código é chave e nunca muda; o nome, sim. */
export type MotiveSide = "CHURN" | "OPPORTUNITY";

export interface MotiveWeight {
  code: string;
  side: MotiveSide;
  name: string;
  description: string;
  points: number;
  /** Em quantas reuniões analisadas este motivo apareceu. */
  meetings: number;
  /** A mesma contagem como fração do total — calibrar sem ela é calibrar no escuro. */
  frequency: number;
  updated_at: string | null;
  updated_by: string | null;
}

export interface ScoringRuler {
  /** Sobe a cada salvamento; fica gravada junto do score de cada reunião. */
  ruler_version: number;
  analysed_meetings: number;
  /** Lados em que os dois maiores pesos já somam mais de 100 — a causa da saturação. */
  saturated_sides: MotiveSide[];
  motives: MotiveWeight[];
}

export interface ScoreDistribution {
  count: number;
  median: number | null;
  mean: number | null;
  at_100: number | null;
  at_least_90: number | null;
  zeros: number | null;
}

export interface ScoringSimulation {
  churn: ScoreDistribution;
  opportunity: ScoreDistribution;
}

export interface MotiveWeightInput {
  code: string;
  points: number;
  name?: string;
  description?: string;
}
