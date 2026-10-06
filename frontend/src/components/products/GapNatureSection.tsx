import { Card, CardContent, CardHeader, CardSubtitle, CardTitle } from "../ui/Card";
import { EmptyChart } from "../ui/EmptyChart";
import type { ProductGapNature } from "../../types";

/** Resíduo da taxonomia, não uma categoria — pintado em cinza e sempre por
 * último, para que a fatia leia como "o que a regra não pega". */
const UNCLASSIFIED = "Não classificado";

/**
 * Natureza dos gaps de um produto: barras horizontais ordenadas por volume.
 *
 * Barra horizontal porque os rótulos são frases ("Controle e rastreabilidade")
 * e girar o texto para caber num eixo X é o que estraga esse gráfico. Hue único
 * (âmbar, o mesmo que a tela já usa para gap) porque isto é **magnitude de uma
 * série**, não identidade: dez cores aqui sugeririam que a cor significa algo,
 * e passariam do limite em que uma paleta categórica ainda é distinguível.
 * Valor direto na ponta de cada barra, então a leitura não depende de eixo nem
 * de cor.
 */
export function GapNatureSection({ items }: { items: ProductGapNature[] }) {
  const total = items.reduce((sum, item) => sum + item.ocorrencias, 0);
  const max = Math.max(1, ...items.map((item) => item.ocorrencias));

  return (
    <Card className="h-full flex flex-col">
      <CardHeader>
        <CardTitle>Natureza dos Gaps</CardTitle>
        <CardSubtitle>
          {total > 0
            ? `${total} ${total === 1 ? "gap apontado" : "gaps apontados"} neste produto, por tipo de lacuna`
            : "Tipo de lacuna apontada nas reuniões deste produto"}
        </CardSubtitle>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col justify-center">
        {items.length === 0 ? (
          <EmptyChart label="Nenhum gap de produto registrado para este produto." />
        ) : (
          /* `gap-2.5` é o piso de espaçamento e `justify-evenly` reparte a
             altura que sobrar — então 2 categorias ficam arejadas no meio em
             vez de uma grudada no topo e outra no rodapé, e 8 continuam
             legíveis. `max-h` em cada linha impede que uma barra de 12px fique
             perdida no meio de uma faixa alta demais num card muito esticado. */
          <div className="flex-1 flex flex-col justify-evenly gap-2.5 py-1">
            {items.map((item) => (
              <GapNatureRow key={item.categoria} item={item} max={max} total={total} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function GapNatureRow({ item, max, total }: {
  item: ProductGapNature;
  max: number;
  total: number;
}) {
  const residual = item.categoria === UNCLASSIFIED;
  const share = Math.round((item.ocorrencias / total) * 100);
  return (
    <div
      className="flex items-center gap-3 flex-shrink-0 max-h-10"
      title={`${item.categoria}: ${item.ocorrencias} de ${total} gaps (${share}%)`}
    >
      {/* 12rem cabe "Customização e parametrização", o rótulo mais longo da
          taxonomia com 29 caracteres; abaixo disso a categoria mais específica
          é justamente a que some no truncamento. */}
      <span
        className={`text-xs w-48 flex-shrink-0 truncate ${
          residual ? "text-ink-muted italic" : "font-semibold text-ink"
        }`}
      >
        {item.categoria}
      </span>
      <div className="flex-1 h-3 rounded-full bg-surface overflow-hidden">
        <div
          className={`h-full rounded-full ${residual ? "bg-slate-500" : "bg-amber-600"}`}
          style={{ width: `${(item.ocorrencias / max) * 100}%` }}
        />
      </div>
      <span className="text-xs font-bold text-ink tabular-nums w-6 text-right flex-shrink-0">
        {item.ocorrencias}
      </span>
    </div>
  );
}
