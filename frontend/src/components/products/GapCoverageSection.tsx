import { ExternalLink, PackageSearch } from "lucide-react";
import { Card, CardContent, CardHeader, CardSubtitle, CardTitle } from "../ui/Card";
import { EmptyChart } from "../ui/EmptyChart";
import type { GapCoverageLevel, ProductGapCoverage } from "../../types";

/* Paleta de estado (não categórica): há produto / talvez / não há. O cinza de
 * "sem cobertura" é deliberado — ali o significado é ausência, e é o único
 * lugar em que um tom neutro é a cor certa em vez de uma falha de saturação.
 * Os três passaram pelo validador de paleta em contraste e separação para
 * daltonismo, e cada um vem com rótulo escrito, nunca cor sozinha. */
const LEVELS: { key: GapCoverageLevel; label: string; bar: string; chip: string }[] = [
  { key: "provavel", label: "Produto provável", bar: "bg-emerald-700", chip: "text-emerald-800 bg-emerald-50 border-emerald-200" },
  { key: "possivel", label: "Vale olhar", bar: "bg-amber-600", chip: "text-amber-800 bg-amber-50 border-amber-200" },
  { key: "sem_cobertura", label: "Sem cobertura", bar: "bg-slate-500", chip: "text-slate-700 bg-slate-50 border-slate-200" },
];

/**
 * Gap × catálogo: dos gaps que o cliente apontou neste produto, quais já têm
 * produto TOTVS que resolve.
 *
 * É cross-sell de um lado e pauta de roadmap do outro, e é o único gráfico da
 * página que cruza as reuniões com uma fonte externa a elas (os 302 produtos de
 * `ai.products`, com embedding).
 *
 * Uma barra empilhada só para o total, porque a pergunta de abertura é de
 * proporção ("quanto do que ele pediu a gente já vende?"), e abaixo a lista dos
 * casos com produto, porque a resposta útil é o nome do produto, não a
 * contagem. Os "sem cobertura" não entram na lista: ali não há o que mostrar, e
 * o número na barra já os representa.
 *
 * Os rótulos dizem "provável" e "vale olhar", nunca "coberto". O casamento é
 * por vizinhança de embedding e a faixa do meio acertou cerca de metade na
 * inspeção manual, então a tela mostra o produto e deixa a decisão com quem lê
 * — por isso cada sugestão é um link para a página do produto.
 */
export function GapCoverageSection({ coverage }: { coverage: ProductGapCoverage }) {
  const { resumo, itens } = coverage;
  const total = LEVELS.reduce((sum, level) => sum + (resumo[level.key] ?? 0), 0);
  const comProduto = itens.filter((item) => item.produtos.length > 0);
  // Faixa sem nenhum item sai da barra e da legenda. Isso importa porque a
  // faixa do meio ("Vale olhar") está desligada no serviço de IA até a busca
  // ser corrigida, e sem este filtro ela ficaria presa na legenda marcando
  // zero para sempre. Quando `total > 0`, ao menos uma faixa sobra — os gaps
  // vão todos para alguma —, então a legenda nunca fica vazia.
  const presentes = LEVELS.filter((level) => (resumo[level.key] ?? 0) > 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Gaps com Produto no Catálogo</CardTitle>
        <CardSubtitle>
          Cada gap apontado contra os produtos TOTVS — o que já existe é venda, o resto é roadmap
        </CardSubtitle>
      </CardHeader>
      <CardContent>
        {total === 0 ? (
          <EmptyChart label="Nenhum gap de produto registrado para este produto." />
        ) : (
          <>
            <div className="flex h-3 rounded-full bg-surface overflow-hidden gap-px mb-2">
              {presentes.map((level) => (
                <div
                  key={level.key}
                  className={level.bar}
                  style={{ width: `${((resumo[level.key] ?? 0) / total) * 100}%` }}
                  title={`${resumo[level.key]} de ${total}: ${level.label}`}
                />
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-ink-secondary mb-4">
              {presentes.map((level) => (
                <span key={level.key} className="flex items-center gap-1.5">
                  <span className={`w-2.5 h-2.5 rounded-sm ${level.bar}`} />
                  {level.label}
                  <span className="font-bold text-ink tabular-nums">{resumo[level.key] ?? 0}</span>
                </span>
              ))}
            </div>

            {comProduto.length === 0 ? (
              <p className="flex items-start gap-1.5 text-xs text-ink-secondary">
                <PackageSearch size={14} className="flex-shrink-0 mt-px text-ink-muted" />
                <span>
                  Nenhum dos {total} {total === 1 ? "gap" : "gaps"} tem produto próximo no catálogo
                  — tudo aqui é pauta de roadmap, não de cross-sell.
                </span>
              </p>
            ) : (
              <div className="space-y-2.5 max-h-[320px] overflow-y-auto pr-1">
                {comProduto.map((item) => {
                  const level = LEVELS.find((l) => l.key === item.cobertura) ?? LEVELS[2];
                  return (
                    <div key={item.gap} className="rounded-lg border border-surface-border px-3 py-2">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xs text-ink leading-snug">{item.gap}</p>
                        <span
                          className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border flex-shrink-0 ${level.chip}`}
                        >
                          {level.label}
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1.5">
                        {item.produtos.map((produto) => (
                          <a
                            key={produto.url}
                            href={produto.url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1 text-[11px] font-semibold text-brand hover:underline"
                            title={`Distância de embedding: ${produto.distancia}`}
                          >
                            {produto.nome}
                            <ExternalLink size={10} />
                          </a>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
