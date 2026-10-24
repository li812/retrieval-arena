/// <reference types="vitest/config" />
import type { ServerResponse } from 'node:http';
import { fileURLToPath, URL } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv, type ProxyOptions } from 'vite';

/**
 * Legacy API paths served by the FastAPI app. During `npm run dev` they are proxied to the
 * backend so the SPA can call them same-origin, exactly as it will when served from `/app/`.
 */
export const PROXIED_PATHS = [
  '/keys',
  '/ingest',
  '/query',
  '/collections',
  '/history',
  '/analyze',
  '/bots',
  '/conversations',
  '/messages',
  '/chat',
  '/mcp-servers',
  '/mcp-tools',
  '/config',
  '/mcp',
  '/healthz',
  '/readyz',
  '/static',
] as const;

function proxyEntry(target: string): ProxyOptions {
  return {
    target,
    changeOrigin: true,
    // SSE (/query, /chat) must stream through untouched.
    configure(proxy) {
      // When the backend is down, answer with a JSON 502 the API client can explain,
      // instead of an opaque empty 500.
      proxy.on('error', (err: NodeJS.ErrnoException, _req, res) => {
        const out = res as ServerResponse | undefined;
        if (!out || !('writeHead' in out) || out.headersSent || out.writableEnded) return;
        out.writeHead(502, { 'Content-Type': 'application/json' });
        out.end(
          JSON.stringify({
            detail: `The API server at ${target} is not reachable (${err.code ?? (err.message || 'connection failed')}). Start the backend and retry.`,
          }),
        );
      });
    },
  };
}

function isTruthy(value: string | undefined): boolean {
  return value !== undefined && ['1', 'true', 'yes', 'on'].includes(value.toLowerCase());
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  // Inside Docker (compose `web` service) this is http://api:8000.
  const target = process.env.VITE_PROXY_TARGET || env.VITE_PROXY_TARGET || 'http://localhost:8000';
  // Docker bind mounts on macOS don't deliver fs events; poll when asked to.
  const usePolling =
    isTruthy(process.env.CHOKIDAR_USEPOLLING) || isTruthy(process.env.VITE_USE_POLLING);

  const proxy: Record<string, ProxyOptions> = {};
  for (const path of PROXIED_PATHS) proxy[path] = proxyEntry(target);
  // The classic (Alpine) UI lives at "/" — proxy exactly "/" so "Open classic UI" works in dev.
  proxy['^/$'] = proxyEntry(target);

  return {
    base: '/app/',
    plugins: [react()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      host: true,
      port: 5173,
      strictPort: false,
      watch: usePolling ? { usePolling: true, interval: 300 } : undefined,
      proxy,
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
      target: 'es2022',
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      css: false,
      restoreMocks: true,
      include: ['src/**/*.test.{ts,tsx}'],
    },
  };
});
