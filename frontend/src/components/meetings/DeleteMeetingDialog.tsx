import { useEffect, useState } from "react";
import { AlertTriangle, Loader2, Trash2 } from "lucide-react";
import { ApiError } from "../../lib/api";
import { dashboardService } from "../../services/dashboardService";

interface DeleteMeetingDialogProps {
  analysisId: string;
  title: string;
  onClose: () => void;
  onDeleted: () => void;
}

/** Confirma e executa a exclusão de uma reunião. O erro fica no próprio diálogo:
 *  a exclusão é uma transação só no backend, então uma falha não apaga nada e o
 *  usuário pode tentar de novo. */
export function DeleteMeetingDialog({ analysisId, title, onClose, onDeleted }: DeleteMeetingDialogProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await dashboardService.remove(analysisId);
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível excluir a reunião.");
      setBusy(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/25 backdrop-blur-[2px] z-40 animate-fade-in" onClick={() => !busy && onClose()} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-meeting-title"
          className="pointer-events-auto w-full max-w-md bg-white border border-gray-200 rounded-2xl shadow-2xl p-6"
        >
          <div className="flex items-start gap-3 mb-4">
            <div className="p-2 rounded-xl bg-rose-50 text-rose-600 flex-shrink-0">
              <Trash2 size={18} />
            </div>
            <div className="min-w-0">
              <h2 id="delete-meeting-title" className="text-base font-bold text-gray-900">Excluir reunião?</h2>
              <p className="text-sm text-gray-500 mt-1 leading-relaxed">
                <span className="font-medium text-gray-700">{title}</span> será excluída junto com a análise,
                os trechos e a conversa do chat. Essa ação não pode ser desfeita.
              </p>
            </div>
          </div>

          {error && (
            <p className="flex items-start gap-2 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2 mb-4">
              <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={busy}
              className="px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:border-gray-300 transition-all disabled:opacity-50"
            >
              Cancelar
            </button>
            <button
              type="button"
              onClick={confirm}
              disabled={busy}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white bg-rose-600 rounded-lg hover:bg-rose-700 transition-all disabled:opacity-60"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
              Excluir
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
