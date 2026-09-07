import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { KoliaLogo } from "../components/ui/KoliaLogo";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../lib/api";

interface LocationState {
  from?: { pathname: string };
}

export function Login() {
  const { login, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo =
    (location.state as LocationState | null)?.from?.pathname ?? "/app/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to={redirectTo} replace />;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Não foi possível entrar. Tente novamente.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-surface flex flex-col items-center justify-center px-6 py-12">
      <Link to="/" className="mb-8">
        <KoliaLogo variant="horizontal-dark" height={30} />
      </Link>

      <div className="card w-full max-w-sm p-8">
        <h1 className="text-xl font-extrabold text-ink mb-1">Entrar na plataforma</h1>
        <p className="text-sm text-ink-secondary mb-6">
          Acesse o painel de inteligência comercial da KOLIA.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-xs font-semibold text-ink mb-1.5">
              E-mail
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              className="input-base"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-xs font-semibold text-ink mb-1.5">
              Senha
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              className="input-base"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {error && (
            <p className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button type="submit" disabled={submitting} className="btn-primary w-full justify-center disabled:opacity-60">
            {submitting ? "Entrando..." : "Entrar"}
            {!submitting && <ArrowRight size={16} />}
          </button>
        </form>

        <p className="text-sm text-ink-secondary mt-6 text-center">
          Não tem conta?{" "}
          <Link to="/register" className="font-semibold text-brand hover:underline">
            Criar conta
          </Link>
        </p>
      </div>
    </div>
  );
}
