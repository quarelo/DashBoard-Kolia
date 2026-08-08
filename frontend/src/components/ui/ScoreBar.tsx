import { cn } from "../../lib/utils";

interface ScoreBarProps {
  score: number;
  showLabel?: boolean;
  size?: "xs" | "sm" | "md";
  colorMode?: "risk" | "opportunity" | "nps";
}

function getColor(score: number, mode: ScoreBarProps["colorMode"]) {
  if (mode === "opportunity") {
    if (score >= 80) return "bg-brand";
    if (score >= 60) return "bg-brand/70";
    if (score >= 40) return "bg-brand/50";
    return "bg-slate-300";
  }
  if (mode === "nps") {
    if (score >= 70) return "bg-emerald-500";
    if (score >= 50) return "bg-blue-500";
    if (score >= 30) return "bg-amber-400";
    return "bg-rose-500";
  }
  // risk (default)
  if (score >= 80) return "bg-rose-500";
  if (score >= 65) return "bg-orange-400";
  if (score >= 50) return "bg-amber-400";
  return "bg-emerald-500";
}

const heightMap = { xs: "h-1", sm: "h-1.5", md: "h-2" };

export function ScoreBar({ score, showLabel = true, size = "md", colorMode = "risk" }: ScoreBarProps) {
  return (
    <div className="flex items-center gap-2">
      <div className={cn("bg-surface-border rounded-full overflow-hidden flex-1", heightMap[size])}>
        <div
          className={cn("h-full rounded-full transition-all duration-500", getColor(score, colorMode))}
          style={{ width: `${score}%` }}
        />
      </div>
      {showLabel && (
        <span className="text-xs font-bold text-ink w-7 text-right tabular-nums">{score}</span>
      )}
    </div>
  );
}
