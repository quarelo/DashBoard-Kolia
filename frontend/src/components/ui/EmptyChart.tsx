/** Placeholder centralizado para um gráfico/lista sem dados suficientes no período. */
export function EmptyChart({ label }: { label: string }) {
  return (
    <div className="h-[120px] flex items-center justify-center text-xs text-ink-muted text-center px-4">
      {label}
    </div>
  );
}
