import { TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "../../lib/utils";

interface KpiCardProps {
  label: string;
  value: string | number;
  change?: number;
  changeLabel?: string;
  icon: React.ReactNode;
  accent?: "brand" | "emerald" | "rose" | "violet" | "blue";
}

const accentMap = {
  brand:   { iconBg: "bg-brand/10",   iconColor: "text-brand",         bar: "bg-brand" },
  emerald: { iconBg: "bg-emerald-50", iconColor: "text-emerald-600",   bar: "bg-emerald-500" },
  rose:    { iconBg: "bg-rose-50",    iconColor: "text-rose-600",      bar: "bg-rose-500" },
  violet:  { iconBg: "bg-violet-50",  iconColor: "text-violet-600",    bar: "bg-violet-500" },
  blue:    { iconBg: "bg-blue-50",    iconColor: "text-blue-600",      bar: "bg-blue-500" },
};

export function KpiCard({ label, value, change, changeLabel, icon, accent = "brand" }: KpiCardProps) {
  const a = accentMap[accent];
  const isPositive = (change ?? 0) >= 0;

  return (
    <div className="card p-5 flex flex-col gap-4 hover:shadow-card-md transition-shadow">
      <div className="flex items-start justify-between">
        <p className="text-sm font-medium text-ink-secondary">{label}</p>
        <div className={cn("p-2 rounded-lg", a.iconBg)}>
          <div className={cn("w-4 h-4 flex items-center justify-center", a.iconColor)}>
            {icon}
          </div>
        </div>
      </div>

      <div>
        <p className="text-3xl font-extrabold text-ink tracking-tight">{value}</p>
        {change !== undefined && (
          <div className={cn(
            "flex items-center gap-1 mt-1.5 text-xs font-semibold",
            isPositive ? "text-emerald-600" : "text-rose-600"
          )}>
            {isPositive ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
            <span>{isPositive ? "+" : ""}{change}% {changeLabel}</span>
          </div>
        )}
      </div>

      {/* Accent bar */}
      <div className="h-0.5 rounded-full bg-surface-border overflow-hidden">
        <div className={cn("h-full rounded-full w-3/4", a.bar)} />
      </div>
    </div>
  );
}
