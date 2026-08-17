import { useState } from "react";
import type { Account } from "../api/auth";
import { login, register } from "../api/auth";

const MIN_PASSWORD_LENGTH = 8; // espejo de auth.service.MIN_PASSWORD_LENGTH

interface AuthFormProps {
  /** Pregunta que el usuario alcanzó a escribir; se retoma al entrar. */
  pendingQuestion?: string;
  onAuthenticated: (account: Account) => void;
  onCancel: () => void;
}

/** Pantalla de cuenta: crear una o entrar con la que ya existe.
 *
 * Aparece cuando alguien pide investigar sin sesión — nunca antes: la portada
 * y el expediente de ejemplo son públicos a propósito.
 */
export function AuthForm({ pendingQuestion, onAuthenticated, onCancel }: AuthFormProps) {
  const [mode, setMode] = useState<"register" | "login">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isRegister = mode === "register";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const account = isRegister
        ? await register(email.trim(), password)
        : await login(email.trim(), password);
      onAuthenticated(account);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No pudimos completar la operación.");
      setBusy(false);
    }
  }

  return (
    <section className="auth">
      <h2 className="auth-title">
        {isRegister ? "Crea una cuenta para investigar" : "Entra a tu cuenta"}
      </h2>
      <p className="auth-sub">
        Cada investigación consulta fuentes oficiales y tiene un costo real. La cuenta es para
        cuidar ese cupo — leer la portada y el expediente de ejemplo no la necesita.
      </p>

      {pendingQuestion && (
        <p className="auth-pending">
          <span className="auth-pending-label">Tu pregunta te espera:</span> {pendingQuestion}
        </p>
      )}

      <form className="auth-form" onSubmit={submit}>
        <label className="auth-label" htmlFor="auth-email">
          Correo
        </label>
        <input
          id="auth-email"
          className="auth-input"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
          autoFocus
        />

        <label className="auth-label" htmlFor="auth-password">
          Contraseña
        </label>
        <input
          id="auth-password"
          className="auth-input"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete={isRegister ? "new-password" : "current-password"}
          minLength={MIN_PASSWORD_LENGTH}
          required
        />
        {isRegister && (
          <p className="auth-hint">Mínimo {MIN_PASSWORD_LENGTH} caracteres.</p>
        )}

        {error && (
          <p className="auth-error" role="alert">
            {error}
          </p>
        )}

        <div className="auth-actions">
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? "Un momento…" : isRegister ? "Crear cuenta" : "Entrar"}
          </button>
          <button type="button" className="btn-secondary" onClick={onCancel} disabled={busy}>
            Volver
          </button>
        </div>
      </form>

      <p className="auth-switch">
        {isRegister ? "¿Ya tienes cuenta?" : "¿Primera vez aquí?"}{" "}
        <button
          type="button"
          className="auth-link"
          onClick={() => {
            setMode(isRegister ? "login" : "register");
            setError(null);
          }}
        >
          {isRegister ? "Inicia sesión" : "Crea una cuenta"}
        </button>
      </p>
    </section>
  );
}
