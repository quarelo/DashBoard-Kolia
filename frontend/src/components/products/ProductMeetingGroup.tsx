import type { ProductMeetingItem } from "../../types";

/** Lista de reuniões por trás de uma reclamação/gap/elogio de produto —
 * usado no modal do Gráfico de Produto (Dashboard) e na Página de Produto. */
export function ProductMeetingGroup({ label, color, dot, items, onOpen, emptyLabel }: {
  label: string;
  color: string;
  dot: string;
  items: ProductMeetingItem[];
  onOpen: (analysisId: string) => void;
  emptyLabel: string;
}) {
  return (
    <div>
      <h3 className={`text-xs font-bold uppercase tracking-wide flex items-center gap-1.5 mb-2 ${color}`}>
        <span className={`w-2 h-2 rounded-full ${dot}`} />
        {label} ({items.length})
      </h3>
      {items.length === 0 ? (
        <p className="text-xs text-ink-muted">{emptyLabel}</p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div
              key={item.analysisId}
              onClick={() => onOpen(item.analysisId)}
              className="px-3 py-2 rounded-lg border border-surface-border hover:bg-surface cursor-pointer transition-colors"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-ink truncate">
                  Reunião {item.externalMeetingId}
                  {(item.uf || item.segmento) && (
                    <span className="text-ink-secondary font-normal">
                      {" "}({[item.uf, item.segmento].filter(Boolean).join(" · ")})
                    </span>
                  )}
                </p>
              </div>
              <ul className="mt-1 space-y-0.5">
                {item.itens.map((texto, i) => (
                  <li key={i} className="text-xs text-ink-secondary line-clamp-2">• {texto}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
