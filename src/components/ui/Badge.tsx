import { cn } from "../../lib/utils";
import type { Priority, InsightType } from "../../types";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "default" | "priority" | "type";
  priority?: Priority;
  type?: InsightType;
  className?: string;
}

export const priorityConfig: Record<Priority, { label: string; className: string; dot: string }> = {
  critical: {
    label: "Crítico",
    className: "bg-rose-50 text-rose-700 border-rose-200",
    dot: "bg-rose-500",
  },
  high: {
    label: "Alto",
    className: "bg-orange-50 text-orange-700 border-orange-200",
    dot: "bg-orange-500",
  },
  medium: {
    label: "Médio",
    className: "bg-amber-50 text-amber-700 border-amber-200",
    dot: "bg-amber-400",
  },
  low: {
    label: "Baixo",
    className: "bg-emerald-50 text-emerald-700 border-emerald-200",
    dot: "bg-emerald-500",
  },
};

export const typeConfig: Record<InsightType, { className: string }> = {
  churn_risk:          { className: "bg-rose-50 text-rose-700 border-rose-200" },
  upsell_opportunity:  { className: "bg-blue-50 text-blue-700 border-blue-200" },
  product_feedback:    { className: "bg-violet-50 text-violet-700 border-violet-200" },
  sentiment_alert:     { className: "bg-amber-50 text-amber-700 border-amber-200" },
  competitive_mention: { className: "bg-slate-50 text-slate-600 border-slate-200" },
};

export function Badge({ children, variant = "default", priority, type, className }: BadgeProps) {
  const base = "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium border";

  const styles =
    variant === "priority" && priority ? priorityConfig[priority].className
    : variant === "type"  && type     ? typeConfig[type].className
    : "bg-surface text-ink-secondary border-surface-border";

  return <span className={cn(base, styles, className)}>{children}</span>;
}

export function PriorityDot({ priority, size = "md" }: { priority: Priority; size?: "sm" | "md" }) {
  const s = size === "sm" ? "w-1.5 h-1.5" : "w-2 h-2";
  return (
    <span className={cn("rounded-full inline-block flex-shrink-0", s, priorityConfig[priority].dot)} />
  );
}
