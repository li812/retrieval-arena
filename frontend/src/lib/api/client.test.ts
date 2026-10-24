import { describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockFetch } from '@/test/utils';

import { API_BASE, ApiError, api, extractDetail, request } from './client';

describe('api client', () => {
  it('defaults to same-origin legacy paths', () => {
    expect(API_BASE).toBe('');
  });

  it('returns parsed JSON and sends X-Request-ID', async () => {
    const fetchMock = mockFetch({ '/bots': jsonResponse([{ id: 1 }]) });
    await expect(api.get('/bots')).resolves.toEqual([{ id: 1 }]);
    const init = fetchMock.mock.calls[0]![1]!;
    const headers = init.headers as Record<string, string>;
    expect(headers['X-Request-ID']).toMatch(/.{8,}/);
    expect(init.credentials).toBe('same-origin');
    expect(fetchMock.mock.calls[0]![0]).toBe('/bots');
  });

  it('serialises JSON bodies', async () => {
    const fetchMock = mockFetch({ '/bots': jsonResponse({ id: 2 }) });
    await api.post('/bots', { name: 'x' });
    const init = fetchMock.mock.calls[0]![1]!;
    expect(init.method).toBe('POST');
    expect(init.body).toBe('{"name":"x"}');
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json');
  });

  it('throws ApiError with the FastAPI detail on non-2xx', async () => {
    mockFetch({
      '/bots': jsonResponse({ detail: "A bot named 'x' already exists" }, 409, {
        'X-Request-ID': 'abc',
      }),
    });
    const err = await api.post('/bots', {}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      status: 409,
      detail: "A bot named 'x' already exists",
      requestId: 'abc',
    });
  });

  it('turns network failures into status 0 with a fix-it message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    );
    const err = (await api.get('/bots').catch((e: unknown) => e)) as ApiError;
    expect(err.status).toBe(0);
    expect(err.isUnreachable).toBe(true);
    expect(err.detail).toMatch(/backend is running/);
  });

  it('can accept a non-2xx status as data', async () => {
    mockFetch({ '/readyz': jsonResponse({ status: 'degraded', checks: {} }, 503) });
    await expect(request('/readyz', { acceptStatuses: [503] })).resolves.toEqual({
      status: 'degraded',
      checks: {},
    });
  });

  it('falls back to the status line for empty bodies', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(new Response(null, { status: 500, statusText: 'Internal Server Error' })),
      ),
    );
    await expect(api.get('/x')).rejects.toMatchObject({ detail: '500 Internal Server Error' });
  });
});

describe('extractDetail', () => {
  it('reads FastAPI validation errors', () => {
    expect(
      extractDetail(
        { detail: [{ loc: ['body', 'name'], msg: 'Field required', type: 'missing' }] },
        'x',
      ),
    ).toBe('name: Field required');
  });
  it('reads the v1 error envelope', () => {
    expect(extractDetail({ error: { type: 'rate_limited', message: 'Slow down' } }, 'x')).toBe(
      'Slow down',
    );
  });
  it('uses plain text and the fallback', () => {
    expect(extractDetail('Bad gateway', 'x')).toBe('Bad gateway');
    expect(extractDetail(null, 'fallback')).toBe('fallback');
  });
});
