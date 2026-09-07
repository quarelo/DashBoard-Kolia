import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { KoliaLogo } from "../components/ui/KoliaLogo";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../lib/api";
import { roleLabels } from "../services/authService";
import type { Role } from "../types";

const ROLES: Role[] = ["SALES_DIRECTOR", "USER"];

export function Register() {
  const { register, login, user } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("SALES_DIRECTOR");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to="/app/dashboard" replace />;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError("A senha precisa ter ao menos 8 caracteres.");
      return;
    }

    setSubmitting(true);
    try {
      await register({ name, email, role, password });
      await login(email, password);
      navigate("/app/dashboard", { replace: true });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Não foi possível criar a conta. Tente novamente.",
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
        <h1 className="text-xl font-extrabold text-ink mb-1">Criar conta</h1>
        <p className="text-sm text-ink-secondary mb-6">
          Cadastre-se para acessar a plataforma KOLIA.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="name" className="block text-xs font-semibold text-ink mb-1.5">
              Nome
            </label>
            <input
              id="name"
              type="text"
              required
              autoComplete="name"
              className="input-base"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

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
            <label htmlFor="role" className="block text-xs font-semibold text-ink mb-1.5">
              Perfil
            </label>
            <select
              id="role"
              className="input-base"
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {roleLabels[r]}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="password" className="block text-xs font-semibold text-ink mb-1.5">
              Senha
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              className="input-base"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <p className="text-[11px] text-ink-muted mt-1">Mínimo de 8 caracteres.</p>
          </div>

          {error && (
            <p className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button type="submit" disabled={submitting} className="btn-primary w-full justify-center disabled:opacity-60">
            {submitting ? "Criando conta..." : "Criar conta"}
            {!submitting && <ArrowRight size={16} />}
          </button>
        </form>

        <p className="text-sm text-ink-secondary mt-6 text-center">
          Já tem conta?{" "}
          <Link to="/login" className="font-semibold text-brand hover:underline">
            Entrar
          </Link>
        </p>
      </div>
    </div>
  );
}
