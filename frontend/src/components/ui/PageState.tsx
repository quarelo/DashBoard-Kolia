import { Loader2, AlertTriangle, Inbox } from "lucide-react";

export function PageLoader({ label = "Carregando..." }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-3 text-ink-muted">
      <Loader2 size={22} className="animate-spin text-brand" />
      <p className="text-sm">{label}</p>
    </div>
  );
}

export function PageError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-3 text-center">
      <AlertTriangle size={22} className="text-rose-500" />
      <p className="text-sm text-ink-secondary max-w-sm">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="text-brand text-sm font-semibold hover:underline">
          Tentar novamente
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-3 text-center bg-white rounded-xl border border-gray-200">
      <Inbox size={22} className="text-gray-300" />
      <p className="text-sm font-medium text-ink-secondary">{title}</p>
      {hint && <p className="text-xs text-ink-muted max-w-sm">{hint}</p>}
    </div>
  );
}
