import { useNavigate } from "react-router-dom";
import { Package } from "lucide-react";
import { Card } from "../components/ui/Card";
import { PageError, PageLoader, EmptyState } from "../components/ui/PageState";
import { dashboardService } from "../services/dashboardService";
import { useAsync } from "../lib/useAsync";
import type { ProductBreakdown } from "../types";

export function Products() {
  const { data, loading, error, reload } = useAsync(() => dashboardService.executive(), []);

  if (loading) return <PageLoader label="Carregando produtos..." />;
  if (error || !data) return <PageError message={error ?? "Sem dados."} onRetry={reload} />;

  const items = data.topProdutos;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-extrabold text-ink">Produtos</h1>
        <p className="text-sm text-ink-secondary mt-0.5">
          Os 10 produtos mais citados nas reuniões analisadas — clique num card para ver o detalhe
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
    </div>
  );
}

function ProductCard({ product }: { product: ProductBreakdown }) {
  const navigate = useNavigate();
  const { nome, mencoes, reclamacoes, gaps, elogios } = product;
  const hasDetail = reclamacoes != null || gaps != null || elogios != null;
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
                title={`${reclamacoes} reclamações`}
              />
            )}
            {(gaps ?? 0) > 0 && (
              <div
                className="h-full bg-amber-400"
                style={{ width: `${((gaps ?? 0) / total) * 100}%` }}
                title={`${gaps} gaps`}
              />
            )}
            {(elogios ?? 0) > 0 && (
              <div
                className="h-full bg-emerald-500"
                style={{ width: `${((elogios ?? 0) / total) * 100}%` }}
                title={`${elogios} elogios`}
              />
            )}
          </div>
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
