import { TriangleAlert } from "lucide-react";
import { Card, CardContent, CardHeader, CardSubtitle, CardTitle } from "../ui/Card";
import { EmptyChart } from "../ui/EmptyChart";
import type { ProductQualityMetric, ProductQualityProfile } from "../../types";

/**
 * O produto em cinco métricas, cada uma como desvio da média do portfólio.
 *
 * Barra divergente, e não radar: as cinco métricas têm unidades diferentes
 * (dois scores de 0 a 100, um percentual e duas contagens por reunião), e um
 * radar só funciona com eixos de escala comum — normalizar as cinco para caber
 * num polígono inventaria uma escala que o dado não tem. Aqui cada linha tem a
 * própria escala, e o que se compara é o **desvio**, que é adimensional.
 *
 * Esse enquadramento é o que faz o gráfico sobreviver a uma reunião só, que é a
 * mediana por produto nesta carga: um valor solto com n=1 não diz nada, "20
 * pontos de risco acima da média do portfólio" diz. Por isso também o aviso de
 * amostra pequena é parte do componente, não um detalhe.
 *
 * A polaridade vem de `maiorEMelhor` e é codificada três vezes — pelo lado da
 * barra, pela cor e pelo número — porque a separação entre os dois polos cai na
 * faixa limítrofe para protanopia, onde a cor sozinha não basta.
 */
export function QualityProfileSection({ profile }: { profile: ProductQualityProfile }) {
  const { metricas, reunioes, reunioesPortfolio } = profile;

  return (
    <Card className="h-full flex flex-col">
      <CardHeader>
        <CardTitle>Qualidade do Produto vs. Portfólio</CardTitle>
        <CardSubtitle>
          {reunioes > 0
            ? `${reunioes} ${reunioes === 1 ? "reunião deste produto" : "reuniões deste produto"} contra ${reunioesPortfolio} do portfólio`
            : "Comparação com a média das reuniões de produto único"}
        </CardSubtitle>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col justify-center">
        {reunioes === 0 ? (
          <EmptyChart label="Nenhuma reunião cita este produto sozinho — sem base para comparar." />
        ) : (
          <>
            {reunioes < 3 && (
              <p className="flex items-start gap-1.5 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5 mb-3">
                <TriangleAlert size={13} className="flex-shrink-0 mt-px" />
                <span>
                  Base de {reunioes} {reunioes === 1 ? "reunião" : "reuniões"}: leia como indício,
                  não como tendência.
                </span>
              </p>
            )}
            {/* Mesmo tratamento do card de Natureza dos Gaps, para os dois se
                comportarem igual quando o outro é o mais alto da linha. Com as
                cinco métricas este card quase sempre é o mais alto, então aqui
                não sobra altura e o `justify-evenly` não faz nada — é para o
                caso contrário não ficar com um vão no rodapé. */}
            <div className="flex-1 flex flex-col justify-evenly gap-3">
              {metricas.map((metric) => <QualityRow key={metric.chave} metric={metric} />)}
            </div>
            <div className="flex items-center gap-4 pt-3 mt-1 border-t border-surface-border text-[11px] text-ink-secondary">
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-sm bg-emerald-700" /> Melhor que a média
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-sm bg-rose-600" /> Pior que a média
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-px h-3 bg-ink-muted" /> Média do portfólio
              </span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function QualityRow({ metric }: { metric: ProductQualityMetric }) {
  const { rotulo, valor, mediaPortfolio, maiorEMelhor } = metric;
  const delta = valor - mediaPortfolio;
  // A barra é relativa à própria métrica, não às outras: 10 pontos de risco e
  // 0,4 gap por reunião não são comparáveis em pixels, e fingir que são é o
  // mesmo erro de um eixo duplo. A referência é a maior das duas pontas.
  const scale = Math.max(Math.abs(mediaPortfolio), Math.abs(valor), 1);
  // Piso de 1,5%: um desvio pequeno mas real (0,08 gap por reunião sobre uma
  // média de 2) renderizaria uma barra de menos de um pixel, e desvio zero e
  // desvio mínimo ficariam indistinguíveis — que é a única coisa que esta
  // barra existe para separar. O teto de 50 é metade da trilha, porque o
  // centro é a média.
  const width = delta === 0 ? 0 : Math.min(50, Math.max(1.5, (Math.abs(delta) / scale) * 50));
  const better = delta === 0 ? null : (delta > 0) === maiorEMelhor;
  const fill = better === null ? "bg-ink-muted" : better ? "bg-emerald-700" : "bg-rose-600";

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 mb-1">
        <span className="text-xs font-semibold text-ink truncate pr-2" title={rotulo}>{rotulo}</span>
        <span className="text-xs tabular-nums flex-shrink-0">
          <span className="font-bold text-ink">{valor}</span>
          <span className="text-ink-muted"> · média {mediaPortfolio}</span>
        </span>
      </div>
      <div className="relative h-3 rounded-full bg-surface overflow-hidden">
        {/* O zero fica no centro: a linha é a média do portfólio. */}
        <div className="absolute inset-y-0 left-1/2 w-px bg-ink-muted/60 z-10" />
        <div
          className={`absolute inset-y-0 ${fill}`}
          style={
            delta >= 0
              ? { left: "50%", width: `${width}%` }
              : { right: "50%", width: `${width}%` }
          }
          title={`${delta > 0 ? "+" : ""}${Math.round(delta * 100) / 100} vs. média do portfólio`}
        />
      </div>
      <p className="text-[11px] text-ink-secondary mt-0.5 tabular-nums">
        {delta === 0 ? (
          "Na média do portfólio"
        ) : (
          <>
            {delta > 0 ? "+" : "−"}{Math.abs(Math.round(delta * 100) / 100)}{" "}
            {better ? "a favor" : "contra"}
          </>
        )}
      </p>
    </div>
  );
}
