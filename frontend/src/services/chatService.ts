import type { ChatMessage, ChatContext } from "../types";
import { meetingsService } from "./meetingsService";
import { insightsService, translateType } from "./insightsService";

/* ── Contextless responses ──────────────────────────────────── */
const GLOBAL_RESPONSES: Record<string, string> = {
  churn: `**Análise de Risco de Churn — Top Clientes em Alerta**

Com base nas últimas 10 reuniões analisadas, identifiquei **3 clientes com alto risco de churn**:

1. 🔴 **Grupo Vivo S.A.** (Score: 92) — Insatisfação crítica com SLA. Mencionou Claro como alternativa. Ação imediata necessária.
2. 🟠 **Embraer** (Score: 78) — VP comparando com SAP para módulos aeroespaciais. Risco de perda de escopo.
3. 🟡 **Banco Bradesco** (Score: 65) — Preocupação com LGPD e prazos BACEN. Situação contornável com ação rápida.

**Recomendação:** Acione o CSM Sênior para contato executivo com Vivo nos próximos 2 dias.`,

  reclamações: `**Produtos com Maior Volume de Reclamações**

| Produto          | Reclamações | Principal Problema               |
|------------------|------------|----------------------------------|
| TOTVS ERP        | 17         | Performance e customizações      |
| TOTVS Integração | 12         | Latência e falhas de sync        |
| TOTVS Fluig      | 9          | Interface complexa               |
| TOTVS PDV        | 6          | Delay com programa de fidelidade |

O tema **"performance em picos de demanda"** aparece em 40% das reclamações. Recomendo escalada para o squad de produto com prioridade alta.`,

  upsell: `**Oportunidades de Upsell Identificadas**

Encontrei **4 oportunidades qualificadas** com alto potencial de conversão:

1. 💰 **Petrobras Distribuidora** → TOTVS Fiscal (Score: 87 — CFO receptivo, processo manual com 8 pessoas)
2. 💰 **Ambev** → TOTVS Qualidade (Score: 81 — compliance ANVISA, ROI claro em rastreabilidade)
3. 💰 **WEG Equipamentos** → TOTVS IoT (Score: 84 — R$ 2M/mês em paradas, ROI calculável)
4. 💰 **Natura &Co** → TOTVS Analytics (Score: 79 — dados omnichannel, alta maturidade digital)

**Potencial estimado:** R$ 3.2M em novos contratos se todas as oportunidades forem convertidas.`,

  sentimento: `**Análise de Sentimento dos Clientes — Junho 2026**

📊 **Distribuição Atual:**
- ✅ Positivo: 60% das reuniões
- ⚪ Neutro: 23% das reuniões
- ❌ Negativo: 17% das reuniões

**Tendência:** Queda de 8pp no sentimento positivo vs. maio (68%).

Temas que mais impactam negativamente:
1. Tempo de resposta do suporte (6 reuniões)
2. Bugs de performance (3 reuniões)
3. Gaps vs. concorrentes (2 reuniões)

**Mais positivos:** IoT/Manufatura e BI/Analytics.
**Mais negativos:** Telecom e Aeroespacial.`,

  nps: `**NPS por Cliente — Panorama Geral**

| Cliente              | NPS | Status      |
|----------------------|-----|-------------|
| WEG Equipamentos     | 82  | Promotor ✅  |
| Ambev                | 78  | Promotor ✅  |
| Petrobras            | 71  | Promotor ✅  |
| Natura &Co           | 69  | Neutro ⚪    |
| Renner Lojas         | 64  | Neutro ⚪    |
| Banco Bradesco       | 52  | Neutro ⚪    |
| Vale S.A.            | 47  | Atenção 🟡  |
| Magazine Luiza       | 34  | Atenção 🟡  |
| Embraer              | 31  | Detrator 🔴 |
| Grupo Vivo           | 28  | Detrator 🔴 |

**NPS Médio:** 56 — Zona de melhoria. Atenção especial a Vivo e Embraer.`,

  default: `Olá! Posso ajudá-lo com análises sobre **risco de churn**, **oportunidades de upsell**, **feedbacks de produto**, **sentimento dos clientes** e **NPS**.

Você também pode selecionar uma **reunião específica** ou **insight** no seletor acima para obter respostas contextualizadas.

Experimente perguntar:
- "Quais clientes possuem maior risco de churn?"
- "Onde existem oportunidades de upsell?"
- "Como está o NPS dos clientes?"`,
};

/* ── Context-aware responses ────────────────────────────────── */
function buildMeetingResponse(meetingId: string, question: string): string {
  const meeting = meetingsService.getById(meetingId);
  if (!meeting) return GLOBAL_RESPONSES.default;

  const lower = question.toLowerCase();

  if (lower.includes("risco") || lower.includes("churn")) {
    return `**Análise de Risco — ${meeting.client}**

Com base na reunião "${meeting.title}" (${new Date(meeting.date).toLocaleDateString("pt-BR")}):

📊 **Score de Risco:** ${meeting.riskScore}/100 ${meeting.riskScore >= 80 ? "🔴 CRÍTICO" : meeting.riskScore >= 60 ? "🟠 ALTO" : "🟡 MODERADO"}

**Palavras-chave de alerta identificadas:**
${meeting.keywords.map((k) => `- ${k}`).join("\n")}

**Sentimento da reunião:** ${meeting.sentiment === "negative" ? "❌ Negativo" : meeting.sentiment === "positive" ? "✅ Positivo" : "⚪ Neutro"}

**NPS atual:** ${meeting.nps ?? "Não informado"}

${meeting.riskScore >= 70
  ? `⚠️ **Ação urgente recomendada:** Agendar reunião executiva com ${meeting.totvsSalesperson} e liderança do cliente nas próximas 48h.`
  : "Monitoramento contínuo recomendado. Próximo passo: acompanhamento de NPS."}`;
  }

  if (lower.includes("oportunidade") || lower.includes("upsell")) {
    const insights = meeting.insightIds
      .map((id) => insightsService.getById(id))
      .filter(Boolean)
      .filter((i) => i?.type === "upsell_opportunity");

    return `**Oportunidades — ${meeting.client}**

Score de Oportunidade desta reunião: **${meeting.opportunityScore}/100**

${insights.length > 0
  ? insights.map((i) => `💰 **${translateType(i!.type)}** (Score: ${i!.score})\n${i!.summary}`).join("\n\n")
  : "Nenhuma oportunidade de upsell direta identificada. Potencial em: " + meeting.keywords.slice(0, 3).join(", ") + "."}

**Responsável TOTVS:** ${meeting.totvsSalesperson} (${meeting.totvsRole})`;
  }

  if (lower.includes("sentimento") || lower.includes("nps")) {
    return `**Sentimento & NPS — ${meeting.client}**

**Reunião:** ${meeting.title}
**Data:** ${new Date(meeting.date).toLocaleDateString("pt-BR")}
**Sentimento geral:** ${meeting.sentiment === "negative" ? "❌ Negativo" : meeting.sentiment === "positive" ? "✅ Positivo" : "⚪ Neutro"}
**NPS registrado:** ${meeting.nps ?? "Não informado"}

**Trecho relevante da transcrição:**
> "${meeting.transcriptSnippet}"

**Palavras-chave do contexto:**
${meeting.keywords.slice(0, 5).map((k) => `• ${k}`).join("\n")}`;
  }

  // General meeting summary
  return `**Resumo da Reunião — ${meeting.client}**

**Título:** ${meeting.title}
**Data:** ${new Date(meeting.date).toLocaleDateString("pt-BR")}
**Duração:** ${meeting.duration} minutos
**Responsável TOTVS:** ${meeting.totvsSalesperson} (${meeting.totvsRole})
**Segmento:** ${meeting.segment}

**Sentimento:** ${meeting.sentiment === "negative" ? "❌ Negativo" : meeting.sentiment === "positive" ? "✅ Positivo" : "⚪ Neutro"} | **NPS:** ${meeting.nps ?? "N/A"}
**Risco:** ${meeting.riskScore}/100 | **Oportunidade:** ${meeting.opportunityScore}/100

**Transcrição:**
> "${meeting.transcriptSnippet}"

**Palavras-chave identificadas:** ${meeting.keywords.join(", ")}

**Insights vinculados:** ${meeting.insightIds.length} insight(s) gerados.

O que você gostaria de aprofundar? Posso analisar riscos, oportunidades ou sentimento desta reunião.`;
}

function buildInsightResponse(insightId: string, question: string): string {
  const insight = insightsService.getById(insightId);
  if (!insight) return GLOBAL_RESPONSES.default;

  const lower = question.toLowerCase();

  if (lower.includes("recomend") || lower.includes("ação") || lower.includes("fazer")) {
    return `**Recomendação de Ação — ${insight.client}**

**Insight:** ${translateType(insight.type)} (Score: ${insight.score}/100)
**Prioridade:** ${insight.priority.toUpperCase()}

**Resumo:**
${insight.summary}

**Evidência da transcrição:**
> "${insight.transcriptEvidence}"

**Recomendação da IA:**
${insight.aiRecommendation}

**Produtos envolvidos:** ${insight.relatedProducts.join(", ")}`;
  }

  return `**Análise do Insight — ${insight.client}**

**Tipo:** ${translateType(insight.type)}
**Score:** ${insight.score}/100
**Prioridade:** ${insight.priority.toUpperCase()}
**Segmento:** ${insight.segment}
**Data:** ${new Date(insight.date).toLocaleDateString("pt-BR")}

**Resumo:**
${insight.summary}

**Evidência da Transcrição:**
> "${insight.transcriptEvidence}"

**Produtos Relacionados:** ${insight.relatedProducts.join(", ")}

**Recomendação da IA:**
${insight.aiRecommendation}

Posso detalhar a recomendação de ação ou comparar com outros insights do mesmo cliente. O que prefere?`;
}

function getGlobalKey(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes("churn") || lower.includes("risco")) return "churn";
  if (lower.includes("reclamação") || lower.includes("reclamações") || lower.includes("produto")) return "reclamações";
  if (lower.includes("upsell") || lower.includes("oportunidade")) return "upsell";
  if (lower.includes("sentimento") || lower.includes("sentiment")) return "sentimento";
  if (lower.includes("nps") || lower.includes("satisfação")) return "nps";
  return "default";
}

/* ── Service ────────────────────────────────────────────────── */
export const chatService = {
  getInitialMessages(context: ChatContext): ChatMessage[] {
    let greeting = "Olá! Sou a **KOLIA IA**, sua assistente de inteligência comercial. 🤖\n\nAnalisei **10 reuniões** recentes e tenho insights prontos. Como posso ajudá-lo?";

    if (context.type === "meeting" && context.id) {
      const m = meetingsService.getById(context.id);
      if (m) {
        greeting = `Contexto carregado: **${m.title}** (${m.client}).\n\nPosso analisar os riscos, oportunidades, sentimento e NPS desta reunião. O que deseja saber?`;
      }
    } else if (context.type === "insight" && context.id) {
      const i = insightsService.getById(context.id);
      if (i) {
        greeting = `Contexto carregado: Insight **${translateType(i.type)}** de **${i.client}** (Score: ${i.score}).\n\nPosso detalhar a análise, recomendação de ação e evidências. O que deseja?`;
      }
    }

    return [
      {
        id: "init-1",
        role: "assistant",
        content: greeting,
        timestamp: new Date().toISOString(),
      },
    ];
  },

  async sendMessage(content: string, context: ChatContext): Promise<ChatMessage> {
    await new Promise((resolve) => setTimeout(resolve, 1000 + Math.random() * 800));

    let responseContent: string;
    if (context.type === "meeting" && context.id) {
      responseContent = buildMeetingResponse(context.id, content);
    } else if (context.type === "insight" && context.id) {
      responseContent = buildInsightResponse(context.id, content);
    } else {
      responseContent = GLOBAL_RESPONSES[getGlobalKey(content)];
    }

    return {
      id: `msg-${Date.now()}`,
      role: "assistant",
      content: responseContent,
      timestamp: new Date().toISOString(),
    };
  },

  getSuggestedQuestions(context: ChatContext): string[] {
    if (context.type === "meeting") {
      return [
        "Qual o risco de churn nesta reunião?",
        "Há oportunidades de upsell identificadas?",
        "Como foi o sentimento e o NPS?",
        "Faça um resumo executivo desta reunião",
      ];
    }
    if (context.type === "insight") {
      return [
        "Qual a recomendação de ação para este insight?",
        "Mostre a evidência da transcrição",
        "Quais produtos estão relacionados?",
        "Qual a prioridade deste insight?",
      ];
    }
    return [
      "Quais clientes possuem maior risco de churn?",
      "Quais produtos recebem mais reclamações?",
      "Onde existem oportunidades de upsell?",
      "Como está o NPS dos clientes?",
    ];
  },

  getContextOptions() {
    const meetings = meetingsService.getAll().map((m) => ({
      type: "meeting" as const,
      id: m.id,
      label: `📅 ${m.client} — ${m.title}`,
    }));

    const insights = insightsService.getAll().map((i) => ({
      type: "insight" as const,
      id: i.id,
      label: `💡 ${i.client} — ${translateType(i.type)} (Score: ${i.score})`,
    }));

    return { meetings, insights };
  },
};
