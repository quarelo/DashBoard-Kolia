import { useMemo, useState } from "react";
import { AlertTriangle, Check, RotateCcw, Save, SlidersHorizontal } from "lucide-react";
import { useAsync } from "../lib/useAsync";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../lib/api";
import {
  fetchScoringRuler, saveScoringRuler, sideLabels, simulateScoringRuler,
} from "../services/scoringService";
import { PageError, PageLoader } from "../components/ui/PageState";
import type {
  MotiveSide, MotiveWeight, MotiveWeightInput, ScoringSimulation,
} from "../types";

const sides: MotiveSide[] = ["CHURN", "OPPORTUNITY"];

/** O peso é uma fatia de um score de 0 a 100; fora disso o backend recusa. */
function clampPoints(value: string): number {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed)) return 0;
  return Math.min(100, Math.max(0, parsed));
}

function toInput(motives: MotiveWeight[], points: Record<string, number>): MotiveWeightInput[] {
  return motives.map((motive) => ({ code: motive.code, points: points[motive.code] ?? motive.points }));
}

function Distribution({ title, stats }: { title: string; stats: ScoringSimulation["churn"] }) {
  const rows: [string, string | number][] = [
    ["Mediana", stats.median ?? "—"],
    ["Média", stats.mean ?? "—"],
    ["Acima de 90", stats.at_least_90 ?? "—"],
    ["No teto (100)", stats.at_100 ?? "—"],
    ["Zerados", stats.zeros ?? "—"],
  ];
  return (
    <div className="rounded-lg border border-gray-200 p-4">
      <p className="text-xs font-semibold text-ink-secondary mb-3">{title}</p>
      <dl className="space-y-1.5">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-4">
            <dt className="text-xs text-ink-muted">{label}</dt>
            <dd className="text-sm font-semibold text-ink-primary tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function Settings() {
  const { user } = useAuth();
  const { data, loading, error, reload } = useAsync(fetchScoringRuler);
  const [points, setPoints] = useState<Record<string, number>>({});
  const [simulation, setSimulation] = useState<ScoringSimulation | null>(null);
  const [busy, setBusy] = useState<"simulate" | "save" | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const canEdit = user?.role === "SALES_DIRECTOR";
  const motives = data?.motives ?? [];
  const current = useMemo(
    () => (motive: MotiveWeight) => points[motive.code] ?? motive.points,
    [points],
  );
  const dirty = motives.some((motive) => current(motive) !== motive.points);

  async function run(kind: "simulate" | "save") {
    if (!data) return;
    setBusy(kind);
    setMessage(null);
    try {
      const body = toInput(motives, points);
      if (kind === "simulate") {
        setSimulation(await simulateScoringRuler(body));
      } else {
        await saveScoringRuler(body);
        setPoints({});
        setSimulation(null);
        setMessage({ kind: "ok", text: "Pesos salvos. As reuniões já analisadas mantêm o número com que foram medidas." });
        reload();
      }
    } catch (err) {
      setMessage({
        kind: "error",
        text: err instanceof ApiError ? err.message : "Não foi possível falar com o servidor.",
      });
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <PageLoader label="Carregando a pontuação..." />;
  if (error || !data) return <PageError message={error ?? "Pontuação indisponível."} onRetry={reload} />;

  return (
    <div className="space-y-6 max-w-5xl">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-ink-primary flex items-center gap-2">
          <SlidersHorizontal size={18} className="text-brand" />
          Pontuação das reuniões
        </h1>
        <p className="text-sm text-ink-muted">
          Quanto cada sinal encontrado numa reunião vale no score. A frequência ao lado de cada
          sinal é real, medida nas {data.analysed_meetings} reuniões já analisadas: um sinal que
          aparece em quase todas separa pouco e merece peso menor.
        </p>
        <p className="text-xs text-ink-muted">
          Régua em vigor: versão {data.ruler_version}. Mudar um peso vale para as próximas
          análises; as antigas guardam o número com que foram medidas.
        </p>
      </header>

      {!canEdit && (
        <p className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800">
          <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
          Só o Diretor Comercial pode salvar. Você pode simular à vontade — a simulação não grava nada.
        </p>
      )}

      {data.saturated_sides.length > 0 && (
        <p className="flex items-start gap-2 rounded-lg bg-rose-50 border border-rose-200 p-3 text-xs text-rose-800">
          <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
          Em {data.saturated_sides.map((side) => sideLabels[side]).join(" e ")}, os dois maiores
          pesos já somam mais de 100. Duas reuniões diferentes vão parar no teto e o score deixa
          de ordenar.
        </p>
      )}

      {message && (
        <p className={`flex items-start gap-2 rounded-lg border p-3 text-xs ${
          message.kind === "ok"
            ? "bg-emerald-50 border-emerald-200 text-emerald-800"
            : "bg-rose-50 border-rose-200 text-rose-800"
        }`}>
          {message.kind === "ok" ? <Check size={14} className="mt-0.5" /> : <AlertTriangle size={14} className="mt-0.5" />}
          {message.text}
        </p>
      )}

      {sides.map((side) => (
        <section key={side} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <h2 className="px-4 py-3 text-sm font-semibold text-ink-primary border-b border-gray-200">
            {sideLabels[side]}
          </h2>
          <ul className="divide-y divide-gray-100">
            {motives.filter((motive) => motive.side === side).map((motive) => (
              <li key={motive.code} className="flex items-center gap-4 px-4 py-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-ink-primary">{motive.name}</p>
                  <p className="text-xs text-ink-muted">{motive.description}</p>
                  <p className="text-xs text-ink-muted mt-0.5">
                    Aparece em {Math.round(motive.frequency * 100)}% das reuniões analisadas
                    {" "}({motive.meetings} de {data.analysed_meetings})
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {/* `sr-only` é `position:absolute`, e sem ancestral posicionado ele se
                      ancora no documento: dentro do `<main>` que rola, os rótulos ficavam
                      em coordenadas abaixo da dobra e esticavam a altura da página, o que
                      punha uma faixa branca sob o app inteiro. `aria-label` não ocupa caixa. */}
                  <input
                    type="number"
                    aria-label={`Pontos de ${motive.name}`}
                    min={0}
                    max={100}
                    value={current(motive)}
                    disabled={!canEdit}
                    onChange={(event) =>
                      setPoints((previous) => ({
                        ...previous,
                        [motive.code]: clampPoints(event.target.value),
                      }))
                    }
                    className="w-20 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-right
                               tabular-nums focus:outline-none focus:ring-2 focus:border-orange-400
                               disabled:bg-gray-50 disabled:text-ink-muted"
                    style={{ "--tw-ring-color": "rgba(231,107,56,0.25)" } as React.CSSProperties}
                  />
                  <span className="text-xs text-ink-muted w-10">pontos</span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ))}

      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={() => run("simulate")}
          disabled={busy !== null}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2
                     text-sm font-semibold text-ink-secondary hover:bg-gray-50 disabled:opacity-50"
        >
          <SlidersHorizontal size={14} />
          {busy === "simulate" ? "Simulando..." : "Simular"}
        </button>
        <button
          onClick={() => run("save")}
          disabled={!canEdit || !dirty || busy !== null}
          className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold
                     text-white disabled:opacity-50"
          style={{ backgroundColor: "#E76B38" }}
        >
          <Save size={14} />
          {busy === "save" ? "Salvando..." : "Salvar"}
        </button>
        <button
          onClick={() => {
            setPoints({});
            setSimulation(null);
            setMessage(null);
          }}
          disabled={!dirty || busy !== null}
          className="inline-flex items-center gap-2 text-sm font-semibold text-ink-muted
                     hover:text-ink-secondary disabled:opacity-50"
        >
          <RotateCcw size={14} />
          Desfazer alterações
        </button>
      </div>

      {simulation && (
        <section className="bg-white rounded-xl border border-gray-200 p-4 space-y-3">
          <div>
            <h2 className="text-sm font-semibold text-ink-primary">Como ficaria</h2>
            <p className="text-xs text-ink-muted">
              Distribuição desta régua sobre as reuniões já analisadas, calculada sem reprocessar
              nada e sem gravar. Nenhum score do dashboard muda até salvar.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Distribution title={sideLabels.CHURN} stats={simulation.churn} />
            <Distribution title={sideLabels.OPPORTUNITY} stats={simulation.opportunity} />
          </div>
        </section>
      )}
    </div>
  );
}
