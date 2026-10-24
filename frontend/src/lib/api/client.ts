/**
 * Typed fetch wrapper for the backend.
 *
 * - Base URL comes from `VITE_API_BASE` (default `''` = same origin, legacy paths). M2 moves the
 *   dashboard API under `/api`; that is a one-line env change.
 * - Every request carries an `X-Request-ID` so a UI error can be matched to a backend log line.
 * - Non-2xx responses (and network failures) throw `ApiError` with a human-readable `detail`.
 * - Cookies are sent same-origin; the session/CSRF header is wired in M2.
 */

export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly requestId: string;
  readonly body: unknown;
  readonly path: string;

  constructor(opts: {
    status: number;
    detail: string;
    requestId: string;
    body?: unknown;
    path: string;
  }) {
    super(opts.detail);
    this.name = 'ApiError';
    this.status = opts.status;
    this.detail = opts.detail;
    this.requestId = opts.requestId;
    this.body = opts.body;
    this.path = opts.path;
  }

  /** Status 0 = the request never got an HTTP answer (server down, offline, CORS). */
  get isNetworkError(): boolean {
    return this.status === 0;
  }

  /** The API server itself is unreachable (directly, or via the dev proxy's 502). */
  get isUnreachable(): boolean {
    return this.status === 0 || this.status === 502 || this.status === 504;
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

/** Human-readable message for any thrown value. */
export function errorText(error: unknown): string {
  if (isApiError(error)) return error.detail;
  if (error instanceof Error) return error.message;
  return 'Something went wrong.';
}

export function newRequestId(): string {
  const c = globalThis.crypto as Crypto | undefined;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  return `req-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function apiUrl(path: string): string {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

/** Pull a readable message out of FastAPI (`{detail}`), v1 (`{error:{message}}`) or plain-text bodies. */
export function extractDetail(body: unknown, fallback: string): string {
  if (typeof body === 'string') return body.trim() || fallback;
  if (body && typeof body === 'object') {
    const rec = body as Record<string, unknown>;
    const detail = rec.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (Array.isArray(detail)) {
      // FastAPI validation errors: [{loc, msg, type}, …]
      const msgs = detail
        .map((d: unknown) => {
          if (!d || typeof d !== 'object') return null;
          const item = d as { msg?: unknown; loc?: unknown };
          const loc = Array.isArray(item.loc) ? item.loc.filter((x) => x !== 'body').join('.') : '';
          return typeof item.msg === 'string' ? (loc ? `${loc}: ${item.msg}` : item.msg) : null;
        })
        .filter((m): m is string => !!m);
      if (msgs.length) return msgs.join('; ');
    }
    const err = rec.error;
    if (
      err &&
      typeof err === 'object' &&
      typeof (err as { message?: unknown }).message === 'string'
    ) {
      return (err as { message: string }).message;
    }
    if (typeof rec.message === 'string' && rec.message) return rec.message;
  }
  return fallback;
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  /** Serialized as JSON unless it is FormData. */
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
  /** Non-2xx statuses whose body should be returned instead of thrown (e.g. 503 from /readyz). */
  acceptStatuses?: readonly number[];
}

async function readBody(res: Response): Promise<unknown> {
  if (res.status === 204) return null;
  const text = await res.text();
  if (!text) return null;
  const type = res.headers.get('content-type') ?? '';
  if (type.includes('json')) {
    try {
      return JSON.parse(text) as unknown;
    } catch {
      return text;
    }
  }
  return text;
}

export async function rawRequest(path: string, opts: RequestOptions = {}): Promise<Response> {
  const requestId = newRequestId();
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'X-Request-ID': requestId,
    ...opts.headers,
  };
  let body: BodyInit | undefined;
  if (opts.body instanceof FormData) body = opts.body;
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.body);
  }
  try {
    return await fetch(apiUrl(path), {
      method: opts.method ?? 'GET',
      headers,
      body,
      signal: opts.signal,
      credentials: 'same-origin',
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    throw new ApiError({
      status: 0,
      detail: 'Could not reach the API server. Check that the backend is running, then retry.',
      requestId,
      path,
    });
  }
}

export async function toApiError(res: Response, path: string): Promise<ApiError> {
  const body = await readBody(res).catch(() => null);
  const fallback = `${res.status} ${res.statusText || 'Request failed'}`.trim();
  return new ApiError({
    status: res.status,
    detail: extractDetail(body, fallback),
    requestId: res.headers.get('x-request-id') ?? '',
    body,
    path,
  });
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await rawRequest(path, opts);
  if (!res.ok && !opts.acceptStatuses?.includes(res.status)) {
    throw await toApiError(res, path);
  }
  return (await readBody(res)) as T;
}

export const api = {
  get: <T>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'GET' }),
  post: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'POST', body }),
  put: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'PUT', body }),
  delete: <T>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'DELETE' }),
};
