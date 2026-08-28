import type { Insight, InsightType, Priority } from "../types";
import insightsData from "../data/insights.json";

const insights: Insight[] = insightsData as Insight[];

export const insightsService = {
  getAll(): Insight[] {
    return insights;
  },

  getById(id: string): Insight | undefined {
    return insights.find((i) => i.id === id);
  },

  getByType(type: InsightType): Insight[] {
    return insights.filter((i) => i.type === type);
  },

  getByPriority(priority: Priority): Insight[] {
    return insights.filter((i) => i.priority === priority);
  },

  getByClient(client: string): Insight[] {
    return insights.filter((i) =>
      i.client.toLowerCase().includes(client.toLowerCase())
    );
  },

  getByDateRange(from: string, to: string): Insight[] {
    return insights.filter((i) => i.date >= from && i.date <= to);
  },

  getChurnRisks(): Insight[] {
    return insights.filter((i) => i.type === "churn_risk");
  },

  getOpportunities(): Insight[] {
    return insights.filter((i) => i.type === "upsell_opportunity");
  },

  getKpis() {
    const total = insights.length;
    const churnRisks = insights.filter((i) => i.type === "churn_risk").length;
    const opportunities = insights.filter(
      (i) => i.type === "upsell_opportunity"
    ).length;
    const avgScore =
      insights.reduce((acc, i) => acc + i.score, 0) / total;

    return {
      total,
      churnRisks,
      opportunities,
      avgScore: Math.round(avgScore),
    };
  },

  getRiskDistribution() {
    const critical = insights.filter((i) => i.priority === "critical").length;
    const high = insights.filter((i) => i.priority === "high").length;
    const medium = insights.filter((i) => i.priority === "medium").length;
    const low = insights.filter((i) => i.priority === "low").length;

    return [
      { name: "Crítico", value: critical, fill: "#ef4444" },
      { name: "Alto", value: high, fill: "#f97316" },
      { name: "Médio", value: medium, fill: "#eab308" },
      { name: "Baixo", value: low, fill: "#22c55e" },
    ];
  },

  getOpportunitiesByCategory() {
    const typeMap: Record<string, { count: number; value: number }> = {};
    insights.forEach((i) => {
      const label = translateType(i.type);
      if (!typeMap[label]) typeMap[label] = { count: 0, value: 0 };
      typeMap[label].count += 1;
      typeMap[label].value += i.score;
    });
    return Object.entries(typeMap).map(([category, data]) => ({
      category,
      count: data.count,
      value: Math.round(data.value / data.count),
    }));
  },
};

export function translateType(type: InsightType): string {
  const map: Record<InsightType, string> = {
    churn_risk: "Risco de Churn",
    upsell_opportunity: "Oportunidade",
    product_feedback: "Feedback Produto",
    sentiment_alert: "Alerta Sentimento",
    competitive_mention: "Menção Concorrente",
  };
  return map[type];
}

export function translatePriority(priority: Priority): string {
  const map: Record<Priority, string> = {
    critical: "Crítico",
    high: "Alto",
    medium: "Médio",
    low: "Baixo",
  };
  return map[priority];
}
