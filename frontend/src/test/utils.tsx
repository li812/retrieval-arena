import { render } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { vi } from 'vitest';

import { AppProviders } from '@/app/providers';
import { routes } from '@/app/router';

export function jsonResponse(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

type Handler = Response | ((init: RequestInit | undefined) => Response | Promise<Response>);

/** Route fetch calls by pathname; unknown paths get a 404 like FastAPI. */
export function mockFetch(handlers: Record<string, Handler>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const path = new URL(url, 'http://localhost').pathname;
    const h = handlers[path];
    if (!h) return jsonResponse({ detail: 'Not Found' }, 404);
    return typeof h === 'function' ? h(init) : h.clone();
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

export function renderApp(path = '/') {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const utils = render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...utils, router };
}

export const READY_OK = {
  status: 'ok',
  checks: {
    sqlite: { ok: true, latency_ms: 1.2, error: null },
    chroma: { ok: true, latency_ms: 8, error: null },
    neo4j: { ok: true, latency_ms: 14, error: null },
  },
};
