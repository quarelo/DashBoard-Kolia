import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ArrowLeft, Layers, MessageSquare, AlertTriangle, Target, Package, Users,
  Quote, HelpCircle, CheckSquare, Wallet, TriangleAlert, FileText,
} from "lucide-react";
import { useAsync } from "../lib/useAsync";
import {
  dashboardService, sentimentLabels, sentimentTone, statusLabel,
  riskLabel, opportunityLabel, evidenceCategoryLabels,
} from "../services/dashboardService";
import { PageError, PageLoader } from "../components/ui/PageState";
import { ScoreBar } from "../components/ui/ScoreBar";
import { cn } from "../lib/utils";
import type { AnalysisDetail, Evidence } from "../types";

function ListSection({
  icon, title, items, tone = "text-gray-700",
}: { icon: React.ReactNode; title: string; items: string[]; tone?: string }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-5">
      <h3 className="text-sm font-bold text-gray-900 mb-3 flex items-center gap-2">{icon}{title}</h3>
      <ul className="space-y-2">
        {items.map((text, i) => (
          <li key={i} className={cn("text-sm leading-relaxed flex gap-2", tone)}>
            <span className="text-gray-300 flex-shrink-0">•</span>
            <span>{text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ScoreCard({
  label, score, color, reason, mode,
}: { label: string; score: number; color: string; reason: string; mode: "risk" | "opportunity" }) {
  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-5">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">{label}</p>
      <div className="flex items-end gap-3 mb-3">
        <span className="text-4xl font-black" style={{ color }}>{score}</span>
        <span className="text-sm text-gray-400 mb-1">/100</span>
      </div>
      <ScoreBar score={score} showLabel={false} colorMode={mode} />
      <p className="text-xs text-gray-500 mt-2">{mode === "risk" ? riskLabel(score) : opportunityLabel(score)}</p>
      {reason && <p className="text-xs text-gray-400 mt-2 leading-relaxed italic">{reason}</p>}
    </div>
  );
}

function EvidenceGroup({ evidencias }: { evidencias: Evidence[] }) {
  if (!evidencias || evidencias.length === 0) return null;
  const groups = evidencias.reduce<Record<string, Evidence[]>>((acc, ev) => {
    (acc[ev.categoria] ??= []).push(ev);
    return acc;
  }, {});
  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-5">
      <h3 className="text-sm font-bold text-gray-900 mb-4 flex items-center gap-2">
        <Quote size={15} className="text-violet-500" />
        Evidências da Transcrição
      </h3>
      <div className="space-y-4">
        {Object.entries(groups).map(([cat, evs]) => (
          <div key={cat}>
            <p className="text-[11px] font-bold text-brand uppercase tracking-wider mb-1.5">
              {evidenceCategoryLabels[cat] ?? cat}
            </p>
            <div className="space-y-2">
              {evs.map((ev, i) => (
                <blockquote key={i} className="border-l-[3px] border-gray-200 bg-gray-50 rounded-r-lg px-3 py-2">
                  <p className="text-sm text-gray-700 italic leading-relaxed">"{ev.trecho}"</p>
                  {ev.insight && <p className="text-xs text-gray-400 mt-1">{ev.insight}</p>}
                </blockquote>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function MeetingDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [showTranscript, setShowTranscript] = useState(false);
  const { data, loading, error, reload } = useAsync<AnalysisDetail>(
    () => dashboardService.detail(id ?? ""),
    [id],
  );

  if (loading) return <PageLoader label="Carregando análise..." />;
  if (error || !data) {
    return (
      <PageError
        message={error ?? "Análise não encontrada."}
        onRetry={id ? reload : undefined}
      />
    );
  }

  const fs = data.finalSummary;
  const metadata = Object.entries(data.metadata).filter(([, v]) => v && v !== "");

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <button onClick={() => navigate("/app/meetings")} className="flex items-center gap-1.5 hover:text-brand transition-colors">
          <ArrowLeft size={15} />
          Reuniões
        </button>
        <span className="text-gray-300">/</span>
        <span className="text-gray-700 font-medium truncate">{data.title}</span>
      </div>

      {/* Header */}
      <div className="bg-white border border-gray-200 rounded-2xl p-6">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl font-bold text-gray-900 leading-tight mb-1">{data.title}</h1>
            <p className="text-sm text-gray-500 flex items-center gap-2">
              <Layers size={13} /> {statusLabel(data.status)}
            </p>
          </div>
          <div className={cn("flex items-center gap-2 px-3 py-2 rounded-xl border text-sm font-semibold flex-shrink-0", sentimentTone[data.sentiment])}>
            {sentimentLabels[data.sentiment]}
          </div>
        </div>
        {data.sentimentReason && (
          <p className="text-sm text-gray-500 pt-4 border-t border-gray-100 italic">{data.sentimentReason}</p>
        )}
        {metadata.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-4 mt-4 border-t border-gray-100">
            {metadata.map(([k, v]) => (
              <div key={k}>
                <p className="text-xs text-gray-400">{k}</p>
                <p className="text-sm font-semibold text-gray-800 truncate">{v}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {!fs && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5 text-sm text-amber-800">
          O resumo final desta análise ainda não está disponível ({statusLabel(data.status)}).
        </div>
      )}

      {fs && (
        <>
          <div className="grid md:grid-cols-2 gap-4">
            <ScoreCard label="Score de Risco de Churn" score={fs.risco_churn.score} color="#f43f5e" reason={fs.risco_churn.justificativa} mode="risk" />
            <ScoreCard label="Score de Oportunidade" score={fs.score_oportunidade.score} color="#3b82f6" reason={fs.score_oportunidade.justificativa} mode="opportunity" />
          </div>

          {(fs.produto.length > 0 || fs.persona.length > 0) && (
            <div className="grid md:grid-cols-2 gap-4">
              {fs.produto.length > 0 && (
                <div className="bg-white border border-gray-200 rounded-2xl p-5">
                  <h3 className="text-sm font-bold text-gray-900 mb-3 flex items-center gap-2">
                    <Package size={15} className="text-brand" /> Produtos Mencionados
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {fs.produto.map((p) => (
                      <span key={p} className="px-2.5 py-1 rounded-lg border border-gray-200 bg-gray-50 text-xs font-medium text-gray-700">{p}</span>
                    ))}
                  </div>
                </div>
              )}
              {fs.persona.length > 0 && (
                <div className="bg-white border border-gray-200 rounded-2xl p-5">
                  <h3 className="text-sm font-bold text-gray-900 mb-3 flex items-center gap-2">
                    <Users size={15} className="text-violet-500" /> Personas Envolvidas
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {fs.persona.map((p) => (
                      <span key={p} className="px-2.5 py-1 rounded-lg border border-gray-200 bg-gray-50 text-xs font-medium text-gray-700">{p}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {fs.budget?.identificado && (
            <div className="bg-white border border-gray-200 rounded-2xl p-5">
              <h3 className="text-sm font-bold text-gray-900 mb-2 flex items-center gap-2">
                <Wallet size={15} className="text-emerald-600" /> Budget
              </h3>
              {fs.budget.valor && <p className="text-sm text-gray-700 mb-1">{fs.budget.valor}</p>}
              {fs.budget.contexto && <p className="text-xs text-gray-400 italic leading-relaxed">{fs.budget.contexto}</p>}
            </div>
          )}

          <div className="grid md:grid-cols-2 gap-4">
            <ListSection icon={<Target size={15} className="text-blue-500" />} title="Oportunidades Comerciais" items={fs.oportunidade_comercial} />
            <ListSection icon={<TriangleAlert size={15} className="text-rose-500" />} title="Problemas Identificados" items={fs.problemas_identificados} tone="text-rose-700" />
            <ListSection icon={<AlertTriangle size={15} className="text-amber-500" />} title="Gaps de Produto" items={fs.gap_produto} />
            <ListSection icon={<MessageSquare size={15} className="text-violet-500" />} title="Feedback de Produto" items={fs.feedback_produto} />
            <ListSection icon={<CheckSquare size={15} className="text-emerald-600" />} title="Recomendações de Ação" items={fs.recomendacao_acao} tone="text-emerald-800" />
            <ListSection icon={<HelpCircle size={15} className="text-gray-500" />} title="Dúvidas em Aberto" items={fs.duvidas_em_aberto} />
          </div>

          <EvidenceGroup evidencias={fs.evidencias} />
        </>
      )}

      {data.transcription && (
        <div className="bg-white border border-gray-200 rounded-2xl p-5">
          <button
            onClick={() => setShowTranscript((v) => !v)}
            className="text-sm font-bold text-gray-900 flex items-center gap-2"
          >
            <FileText size={15} className="text-gray-400" />
            Transcrição completa {showTranscript ? "▲" : "▼"}
          </button>
          {showTranscript && (
            <pre className="mt-3 text-xs text-gray-600 whitespace-pre-wrap leading-relaxed max-h-[480px] overflow-y-auto scrollbar-thin">
              {data.transcription}
            </pre>
          )}
        </div>
      )}

      {data.ragReady && (
        <div className="bg-gradient-to-r from-brand to-brand-600 rounded-2xl p-5 flex items-center justify-between gap-4">
          <div>
            <p className="font-bold text-white mb-0.5">Conversar sobre esta reunião</p>
            <p className="text-white/80 text-sm">Faça perguntas com base nos trechos desta transcrição.</p>
          </div>
          <Link
            to={`/app/chat?analysisId=${data.analysisId}`}
            className="flex items-center gap-2 px-5 py-2.5 bg-white text-brand font-semibold rounded-xl hover:bg-white/90 transition-all text-sm flex-shrink-0 shadow-md"
          >
            <MessageSquare size={15} /> Abrir Chat
          </Link>
        </div>
      )}
    </div>
  );
}
