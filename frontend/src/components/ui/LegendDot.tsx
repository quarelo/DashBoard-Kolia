/** Bolinha colorida + rótulo, para legendas de gráfico (ex: "Reclamações", "Gaps"). */
export function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={`w-2 h-2 rounded-full ${color}`} />
      {label}
    </span>
  );
}
