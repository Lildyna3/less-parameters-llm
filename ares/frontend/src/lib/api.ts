/* In production the backend serves this bundle, so same-origin relative URLs
   are correct and no API host is baked in. During `vite dev` the backend runs
   on :8000, which VITE_API_BASE (or the dev default) points at. */
const DEV_FALLBACK = "http://127.0.0.1:8000";
const BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? DEV_FALLBACK : "");

const TOKEN_KEY = "ares.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* private mode: the session just won't persist */ }
}

/** The resolved API origin: same-origin in production, the dev backend during
    `vite dev`. Exported so callers can reach the real API rather than the dev
    server when they need a raw fetch. */
export const apiUrl = (path: string): string => `${BASE}${path}`;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { "content-type": "application/json" };
  // The token is supplied by the user at runtime — never compiled into the bundle.
  if (token) headers["X-ARES-Token"] = token;

  const resp = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...headers, ...(init?.headers as Record<string, string> | undefined) },
  });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new ApiError(resp.status, (body as { detail?: string }).detail ?? resp.statusText);
  }
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(data ?? {}) }),
  patch: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(data ?? {}) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  wsUrl: () => {
    // Browsers cannot set headers on a WebSocket, so the token rides as a query
    // parameter (over TLS in production).
    const origin = BASE || window.location.origin;
    const url = new URL("/ws", origin);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    const token = getToken();
    if (token) url.searchParams.set("access_token", token);
    return url.toString();
  },
};
