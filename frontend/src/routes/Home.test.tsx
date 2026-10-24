import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { jsonResponse, mockFetch, READY_OK, renderApp } from '@/test/utils';

const COLLECTIONS = [
  {
    name: 'docs',
    chunks: 40,
    entities: 12,
    triples: 9,
    sentiment: null,
    sources: [],
    embed_provider: null,
    embed_model: null,
    embed_dim: null,
  },
  {
    name: 'notes',
    chunks: 2,
    entities: null,
    triples: null,
    sentiment: null,
    sources: [],
    embed_provider: null,
    embed_model: null,
    embed_dim: null,
  },
];
const BOTS = [{ id: 1, name: 'Librarian', emoji: '📚' }];

describe('Home', () => {
  it('shows every readiness check, counts and the overall status', async () => {
    mockFetch({
      '/readyz': jsonResponse(READY_OK),
      '/collections': jsonResponse(COLLECTIONS),
      '/bots': jsonResponse(BOTS),
    });
    renderApp('/');
    for (const name of ['sqlite', 'chroma', 'neo4j']) {
      expect(await screen.findByTestId(`check-${name}`)).toHaveAttribute('data-state', 'ok');
    }
    expect(screen.getByText('All systems go')).toBeInTheDocument();
    const cols = screen.getByRole('region', { name: 'Collections' });
    expect(within(cols).getByText('2')).toBeInTheDocument();
    expect(within(cols).getByText('1 with a knowledge graph')).toBeInTheDocument();
    expect(
      within(screen.getByRole('region', { name: 'Chunks indexed' })).getByText('42'),
    ).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Bots' })).getByText('1')).toBeInTheDocument();
  });

  it('marks a failing dependency from a 503 and shows its error', async () => {
    const degraded = {
      status: 'unavailable',
      checks: {
        ...READY_OK.checks,
        neo4j: { ok: false, latency_ms: 2000, error: 'ServiceUnavailable: connection refused' },
      },
    };
    mockFetch({
      '/readyz': jsonResponse(degraded, 503),
      '/collections': jsonResponse([]),
      '/bots': jsonResponse([]),
    });
    renderApp('/');
    const neo = await screen.findByTestId('check-neo4j');
    expect(neo).toHaveAttribute('data-state', 'down');
    expect(neo).toHaveTextContent('connection refused');
    expect(screen.getByText('Degraded')).toBeInTheDocument();
  });

  it('every check has a "?" tooltip in plain language, reachable by keyboard', async () => {
    mockFetch({
      '/readyz': jsonResponse(READY_OK),
      '/collections': jsonResponse([]),
      '/bots': jsonResponse([]),
    });
    const user = userEvent.setup();
    renderApp('/');
    await screen.findByTestId('check-sqlite');
    for (const label of ['SQLite', 'Chroma', 'Neo4j']) {
      const btn = screen.getByRole('button', { name: `About ${label}` });
      const tipId = btn.getAttribute('aria-describedby')!;
      expect(document.getElementById(tipId)).toHaveAttribute('role', 'tooltip');
      expect(document.getElementById(tipId)!.textContent.length).toBeGreaterThan(40);
    }
    const sqlite = screen.getByRole('button', { name: 'About SQLite' });
    await user.click(sqlite); // tap/click pins it open
    const tip = document.getElementById(sqlite.getAttribute('aria-describedby')!)!;
    expect(tip).toBeVisible();
    await user.keyboard('{Escape}');
    expect(tip).not.toBeVisible();
  });

  it('explains a backend without /readyz instead of crashing', async () => {
    mockFetch({ '/collections': jsonResponse([]), '/bots': jsonResponse([]) });
    renderApp('/');
    expect(await screen.findByText(/Health checks aren’t available/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('shows a clear unreachable state and a toast when the API is down', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    );
    renderApp('/');
    expect(
      await screen.findByText('Can’t reach the API server', {}, { timeout: 4000 }),
    ).toBeInTheDocument();
    const toasts = await screen.findByRole('list', { name: 'Notifications' }, { timeout: 4000 });
    await waitFor(
      () => expect(within(toasts).getByText('Backend unreachable')).toBeInTheDocument(),
      { timeout: 4000 },
    );
    // Collections and bots both fail, but the toast is deduplicated.
    expect(within(toasts).getAllByRole('alert')).toHaveLength(1);
  });

  it('shows empty states with one next action when there is no data', async () => {
    mockFetch({
      '/readyz': jsonResponse(READY_OK),
      '/collections': jsonResponse([]),
      '/bots': jsonResponse([]),
    });
    renderApp('/');
    expect(await screen.findByText('No collections yet.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Ingest documents/ })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: /Create your first bot/ })).toHaveAttribute(
      'href',
      '/',
    );
  });

  it('surfaces non-network API errors as a toast with the backend detail', async () => {
    mockFetch({
      '/readyz': jsonResponse(READY_OK),
      '/collections': jsonResponse([]),
      '/bots': jsonResponse({ detail: 'database is locked' }, 500),
    });
    renderApp('/');
    const toasts = await screen.findByRole('list', { name: 'Notifications' });
    await waitFor(
      () => expect(within(toasts).getByText("Couldn't load bots")).toBeInTheDocument(),
      { timeout: 4000 },
    );
    expect(within(toasts).getByText('database is locked')).toBeInTheDocument();
  });
});
