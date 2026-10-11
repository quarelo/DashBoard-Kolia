import { ChevronLeft, ChevronRight, MoreHorizontal } from "lucide-react";
import { cn } from "../../lib/utils";

interface PaginationProps {
  /** Página atual, a partir de 0. */
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
  disabled?: boolean;
}

/** Primeira, última e a atual com uma vizinha de cada lado; o resto vira "…". */
function pageItems(page: number, pageCount: number): (number | "gap")[] {
  const keep = new Set([0, pageCount - 1, page - 1, page, page + 1]);
  const items: (number | "gap")[] = [];
  for (let p = 0; p < pageCount; p++) {
    if (keep.has(p)) items.push(p);
    else if (items[items.length - 1] !== "gap") items.push("gap");
  }
  return items;
}

const itemClass =
  "inline-flex items-center justify-center gap-1 h-9 min-w-9 px-2.5 rounded-lg text-sm font-medium " +
  "transition-colors disabled:pointer-events-none disabled:opacity-40";

/** No molde da paginação do shadcn/ui: botões fantasmas, página atual com borda. */
export function Pagination({ page, pageCount, onPageChange, disabled }: PaginationProps) {
  if (pageCount <= 1) return null;

  return (
    <nav aria-label="Paginação" className="flex justify-center">
      <ul className="flex items-center gap-1">
        <li>
          <button
            type="button"
            aria-label="Página anterior"
            onClick={() => onPageChange(page - 1)}
            disabled={disabled || page === 0}
            className={cn(itemClass, "text-ink-secondary hover:bg-surface hover:text-ink")}
          >
            <ChevronLeft size={16} />
            <span className="hidden sm:inline">Anterior</span>
          </button>
        </li>

        {/* No celular os números não cabem: fica só "3 / 7" entre as setas. */}
        <li className="sm:hidden px-2 text-sm text-ink-secondary tabular-nums">
          {page + 1} / {pageCount}
        </li>

        {pageItems(page, pageCount).map((item, index) =>
          item === "gap" ? (
            <li key={`gap-${index}`} aria-hidden className="hidden sm:flex h-9 w-9 items-center justify-center text-ink-muted">
              <MoreHorizontal size={16} />
            </li>
          ) : (
            <li key={item} className="hidden sm:block">
              <button
                type="button"
                aria-current={item === page ? "page" : undefined}
                onClick={() => onPageChange(item)}
                disabled={disabled}
                className={cn(
                  itemClass,
                  "tabular-nums",
                  item === page
                    ? "border border-surface-border bg-white text-ink shadow-card"
                    : "text-ink-secondary hover:bg-surface hover:text-ink",
                )}
              >
                {item + 1}
              </button>
            </li>
          ),
        )}

        <li>
          <button
            type="button"
            aria-label="Próxima página"
            onClick={() => onPageChange(page + 1)}
            disabled={disabled || page + 1 >= pageCount}
            className={cn(itemClass, "text-ink-secondary hover:bg-surface hover:text-ink")}
          >
            <span className="hidden sm:inline">Próxima</span>
            <ChevronRight size={16} />
          </button>
        </li>
      </ul>
    </nav>
  );
}
