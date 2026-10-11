import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Package } from "lucide-react";
import { Card } from "../components/ui/Card";
import { Pagination } from "../components/ui/Pagination";
import { PageError, PageLoader, EmptyState } from "../components/ui/PageState";
import { dashboardService } from "../services/dashboardService";
import { useAsync } from "../lib/useAsync";
import { meetingMarkLabel } from "../lib/utils";
import type { ProductBreakdown } from "../types";

// A rota devolve o catálogo citado inteiro de uma vez (são ~100 linhas de
// contagem, não reuniões), então a paginação é só de tela.
const PAGE_SIZE = 24;

export function Products() {
  const { data, loading, error, reload } = useAsync(() => dashboardService.products(), []);
  const [page, setPage] = useState(0);

  if (loading) return <PageLoader label="Carregando produtos..." />;
  if (error || !data) return <PageError message={error ?? "Sem dados."} onRetry={reload} />;

  const pageCount = Math.max(1, Math.ceil(data.items.length / PAGE_SIZE));
  const items = data.items.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-extrabold text-ink">Produtos</h1>
        <p className="text-sm text-ink-secondary mt-0.5">
          {data.total} produtos citados nas reuniões analisadas, do mais ao menos citado — clique num card para ver o detalhe
        </p>
      </div>

      {items.length === 0 ? (
        <EmptyState
          title="Nenhum produto citado no período."
          hint="Assim que reuniões analisadas citarem produtos, eles aparecem aqui."
        />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {items.map((product) => (
            <ProductCard key={product.nome} product={product} />
          ))}
        </div>
      )}

      <Pagination page={page} pageCount={pageCount} onPageChange={setPage} />
    </div>
  );
}

function ProductCard({ product }: { product: ProductBreakdown }) {
  const navigate = useNavigate();
  const { nome, mencoes, reclamacoes, gaps, elogios } = product;
  const hasDetail = reclamacoes != null || gaps != null || elogios != null;
  // Denominador das fatias, não um total de reuniões — as três marcas se
  // sobrepõem. Mesma observação do `ProductBar` do Dashboard.
  const total = (reclamacoes ?? 0) + (gaps ?? 0) + (elogios ?? 0);

  return (
    <Card
      hover
      onClick={() => navigate(`/app/products/${encodeURIComponent(nome)}`)}
      className="p-5 flex flex-col gap-3"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="p-2 rounded-lg bg-brand/10 text-brand flex-shrink-0">
          <Package size={16} />
        </div>
        <span className="text-xs text-ink-muted tabular-nums flex-shrink-0 pt-1">
          {mencoes} menç{mencoes === 1 ? "ão" : "ões"}
        </span>
      </div>

      <h3 className="text-sm font-bold text-ink leading-snug line-clamp-2 min-h-[2.5rem]" title={nome}>
        {nome}
      </h3>

      {hasDetail && total > 0 ? (
        <div className="space-y-1.5">
          <div className="h-2.5 rounded-full bg-surface overflow-hidden flex">
            {(reclamacoes ?? 0) > 0 && (
              <div
                className="h-full bg-rose-500"
                style={{ width: `${((reclamacoes ?? 0) / total) * 100}%` }}
                title={meetingMarkLabel(reclamacoes ?? 0, "reclamação")}
              />
            )}
            {(gaps ?? 0) > 0 && (
              <div
                className="h-full bg-amber-400"
                style={{ width: `${((gaps ?? 0) / total) * 100}%` }}
                title={meetingMarkLabel(gaps ?? 0, "gap")}
              />
            )}
            {(elogios ?? 0) > 0 && (
              <div
                className="h-full bg-emerald-500"
                style={{ width: `${((elogios ?? 0) / total) * 100}%` }}
                title={meetingMarkLabel(elogios ?? 0, "elogio")}
              />
            )}
          </div>
          {/* O qualificador vai numa linha própria, e não colado em cada
              número, porque o card ocupa um terço da grade no desktop e
              "3 reuniões com recl." em três colunas não cabe sem quebrar. */}
          <p className="text-[10px] text-ink-muted leading-none">Reuniões com</p>
          <div className="flex items-center gap-3 text-[11px]">
            <span className="text-rose-600 font-semibold">{reclamacoes ?? 0} recl.</span>
            <span className="text-amber-600 font-semibold">{gaps ?? 0} gaps</span>
            <span className="text-emerald-600 font-semibold">{elogios ?? 0} elog.</span>
          </div>
        </div>
      ) : (
        <p className="text-[11px] text-ink-muted">Sem detalhamento por reclamação/gap/elogio.</p>
      )}
    </Card>
  );
}
