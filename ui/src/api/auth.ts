/**
 * Cuentas: registro, sesión y cierre de sesión.
 *
 * La sesión vive en una cookie HttpOnly que pone el backend — este módulo
 * NUNCA ve el token, así que no hay nada que guardar en localStorage (ni nada
 * que un XSS pueda robar). Por eso todas las llamadas van con
 * `credentials: "include"`: sin eso el navegador no manda la cookie cuando la
 * UI corre en otro puerto que el backend (desarrollo).
 */

const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface Account {
  email: string;
}

/** El backend respondió 401: no hay sesión (o venció). */
export class SessionRequiredError extends Error {
  constructor(message = "Necesitas iniciar sesión para investigar.") {
    super(message);
    this.name = "SessionRequiredError";
  }
}

async function readDetail(res: Response, fallback: string): Promise<string> {
  try {
    return ((await res.json()) as { detail?: unknown }).detail as string | undefined ?? fallback;
  } catch {
    return fallback;
  }
}

async function post(path: string, body?: unknown): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/** Cuenta de la sesión vigente, o null si no hay ninguna. */
export async function fetchSession(): Promise<Account | null> {
  try {
    const res = await fetch(`${API_URL}/auth/me`, { credentials: "include" });
    if (!res.ok) return null;
    return (await res.json()) as Account;
  } catch {
    // Backend caído al cargar: se trata como "sin sesión". El usuario verá el
    // error real cuando intente investigar, no un mensaje al abrir la página.
    return null;
  }
}

export async function register(email: string, password: string): Promise<Account> {
  const res = await post("/auth/register", { email, password });
  if (!res.ok) {
    // 422 = el backend validó el formato (correo inválido, contraseña corta) y
    // devuelve el detalle de Pydantic, ilegible para una persona.
    throw new Error(
      res.status === 422
        ? "Revisa el correo y usa una contraseña de al menos 8 caracteres."
        : await readDetail(res, "No pudimos crear la cuenta. Intenta de nuevo."),
    );
  }
  return (await res.json()) as Account;
}

export async function login(email: string, password: string): Promise<Account> {
  const res = await post("/auth/login", { email, password });
  if (!res.ok) {
    throw new Error(
      res.status === 422
        ? "Revisa el correo y la contraseña."
        : await readDetail(res, "No pudimos iniciar sesión. Intenta de nuevo."),
    );
  }
  return (await res.json()) as Account;
}

export async function logout(): Promise<void> {
  await post("/auth/logout");
}
