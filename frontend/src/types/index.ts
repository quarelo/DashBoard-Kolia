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

export type Priority = "critical" | "high" | "medium" | "low";
export type InsightType =
  | "churn_risk"
  | "upsell_opportunity"
  | "product_feedback"
  | "sentiment_alert"
  | "competitive_mention";

export type Sentiment = "positive" | "neutral" | "negative";

export interface Insight {
  id: string;
  client: string;
  clientLogo?: string;
  type: InsightType;
  score: number;
  priority: Priority;
  date: string;
  summary: string;
  transcriptEvidence: string;
  relatedProducts: string[];
  aiRecommendation: string;
  meetingId: string;
  segment: string;
}

export interface MeetingParticipant {
  name: string;
  role: string;
  company: "TOTVS" | "CLIENT";
}

export interface Meeting {
  id: string;
  title: string;
  client: string;
  segment: string;
  date: string;
  duration: number;
  /** Responsável TOTVS principal */
  totvsSalesperson: string;
  totvsRole: string;
  participants: MeetingParticipant[];
  transcriptSnippet: string;
  sentiment: Sentiment;
  nps: number | null;
  riskScore: number;
  opportunityScore: number;
  /** Palavras-chave extraídas por TF-IDF */
  keywords: string[];
  insightIds: string[];
  tags: string[];
}

export interface TfidfTerm {
  term: string;
  weight: number;
  category: string;
  meetingIds: string[];
}

export interface KpiCard {
  label: string;
  value: string | number;
  change: number;
  changeLabel: string;
  icon: string;
  color: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface ChatContext {
  type: "none" | "meeting" | "insight";
  id: string | null;
  label: string;
}

export interface RiskDistribution {
  name: string;
  value: number;
  fill: string;
}

export interface OpportunityByCategory {
  category: string;
  count: number;
  value: number;
}

export interface SentimentTimeline {
  month: string;
  positive: number;
  neutral: number;
  negative: number;
}

export interface ProductMention {
  product: string;
  mentions: number;
  positive: number;
  negative: number;
}
