import { describe, expect, it } from 'vitest';

import { jsonResponse, mockFetch, READY_OK } from '@/test/utils';

import { fetchReadiness } from './api';

describe('fetchReadiness', () => {
  it('returns the checks on 200', async () => {
    mockFetch({ '/readyz': jsonResponse(READY_OK) });
    await expect(fetchReadiness()).resolves.toEqual(READY_OK);
  });

  it('treats 503 with checks as data, not an error', async () => {
    const body = {
      status: 'unavailable',
      checks: { neo4j: { ok: false, latency_ms: 2000, error: 'timeout' } },
    };
    mockFetch({ '/readyz': jsonResponse(body, 503) });
    await expect(fetchReadiness()).resolves.toEqual(body);
  });

  it('throws on 404 (backend without /readyz)', async () => {
    mockFetch({});
    await expect(fetchReadiness()).rejects.toMatchObject({ status: 404 });
  });

  it('throws on a 503 that is not a readiness body', async () => {
    mockFetch({ '/readyz': new Response('frontend not built', { status: 503 }) });
    await expect(fetchReadiness()).rejects.toMatchObject({ status: 503 });
  });
});
