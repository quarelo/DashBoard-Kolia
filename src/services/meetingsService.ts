import type { Meeting, SentimentTimeline } from "../types";
import meetingsData from "../data/meetings.json";

const meetings: Meeting[] = meetingsData as unknown as Meeting[];

export const meetingsService = {
  getAll(): Meeting[] {
    return meetings;
  },

  getById(id: string): Meeting | undefined {
    return meetings.find((m) => m.id === id);
  },

  getByClient(client: string): Meeting[] {
    return meetings.filter((m) =>
      m.client.toLowerCase().includes(client.toLowerCase())
    );
  },

  getRecentMeetings(count = 5): Meeting[] {
    return [...meetings]
      .sort((a, b) => b.date.localeCompare(a.date))
      .slice(0, count);
  },

  getSentimentTimeline(): SentimentTimeline[] {
    return [
      { month: "Jan", positive: 62, neutral: 25, negative: 13 },
      { month: "Fev", positive: 58, neutral: 28, negative: 14 },
      { month: "Mar", positive: 65, neutral: 22, negative: 13 },
      { month: "Abr", positive: 70, neutral: 20, negative: 10 },
      { month: "Mai", positive: 68, neutral: 21, negative: 11 },
      { month: "Jun", positive: 60, neutral: 23, negative: 17 },
    ];
  },

  getProductMentions() {
    return [
      { product: "TOTVS ERP", mentions: 45, positive: 28, negative: 17 },
      { product: "TOTVS Fluig", mentions: 32, positive: 20, negative: 12 },
      { product: "TOTVS PDV", mentions: 28, positive: 22, negative: 6 },
      { product: "TOTVS Analytics", mentions: 24, positive: 19, negative: 5 },
      { product: "TOTVS IoT", mentions: 18, positive: 15, negative: 3 },
      { product: "TOTVS WMS", mentions: 15, positive: 10, negative: 5 },
    ];
  },

  getStats() {
    const total = meetings.length;
    const positive = meetings.filter((m) => m.sentiment === "positive").length;
    const negative = meetings.filter((m) => m.sentiment === "negative").length;
    const avgDuration =
      meetings.reduce((acc, m) => acc + m.duration, 0) / total;
    const avgNps =
      meetings.filter((m) => m.nps !== null).reduce((acc, m) => acc + (m.nps ?? 0), 0) /
      meetings.filter((m) => m.nps !== null).length;
    return {
      total,
      positive,
      negative,
      avgDuration: Math.round(avgDuration),
      avgNps: Math.round(avgNps),
    };
  },
};
