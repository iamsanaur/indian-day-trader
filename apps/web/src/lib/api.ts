// API client for the self-hosted `idt serve` server. Connection is stored per browser.

const KEY = "idt.connection";

export interface Connection {
  url: string;
  token: string;
}

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

function read(): Connection {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return JSON.parse(raw) as Connection;
  } catch {
    /* storage unavailable */
  }
  return { url: "", token: "" };
}

export function getConnection(): Connection {
  const conn = read();
  // `idt serve` prints  http://host:port/?token=...  — adopt it on first load.
  const fromUrl = new URLSearchParams(window.location.search).get("token");
  if (fromUrl) {
    const next = { url: conn.url, token: fromUrl };
    saveConnection(next);
    window.history.replaceState(null, "", window.location.pathname);
    return next;
  }
  return conn;
}

export function saveConnection(conn: Connection): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(conn));
  } catch {
    /* storage unavailable */
  }
}

/** Empty url = same origin (web app served by the API, or the Vite dev proxy). */
export function baseUrl(conn = getConnection()): string {
  return conn.url.replace(/\/+$/, "");
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const conn = getConnection();
  const { json, ...rest } = init;
  const res = await fetch(`${baseUrl(conn)}/api${path}`, {
    ...rest,
    method: rest.method ?? (json !== undefined ? "POST" : "GET"),
    headers: {
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(conn.token ? { Authorization: `Bearer ${conn.token}` } : {}),
      ...rest.headers,
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* empty body */
  }
  if (!res.ok) {
    const b = body as { error?: string; detail?: string } | null;
    const msg = b?.error ?? b?.detail ?? `HTTP ${res.status}`;
    throw new ApiError(res.status === 401 ? "Not paired: open Settings and enter the server token." : msg, res.status);
  }
  return body as T;
}

export function eventsUrl(interval = 15): string {
  const conn = getConnection();
  return `${baseUrl(conn)}/api/events?interval=${interval}&token=${encodeURIComponent(conn.token)}`;
}
