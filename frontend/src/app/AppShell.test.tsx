import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { jsonResponse, mockFetch, READY_OK, renderApp } from '@/test/utils';

beforeEach(() => {
  mockFetch({
    '/readyz': jsonResponse(READY_OK),
    '/collections': jsonResponse([]),
    '/bots': jsonResponse([]),
  });
});

describe('AppShell and routes', () => {
  it.each([
    ['/bots', 'Bots', /Open Bot Studio/],
    ['/collections', 'Collections', /Open classic UI to ingest/],
    ['/lab', 'Retrieval Lab', /Open the Lab/],
  ])(
    '%s is a placeholder with an empty state and one primary action',
    async (path, heading, action) => {
      renderApp(path);
      expect(await screen.findByRole('heading', { name: heading, level: 2 })).toBeInTheDocument();
      const main = screen.getByRole('main');
      const primaries = main.querySelectorAll('.btn-primary');
      expect(primaries).toHaveLength(1);
      expect(within(main).getByRole('link', { name: action })).toHaveAttribute('href', '/');
    },
  );

  it('marks the current page in the sidebar nav', async () => {
    renderApp('/collections');
    const nav = await screen.findByRole('navigation', { name: 'Pages' });
    expect(within(nav).getByRole('link', { name: 'Collections' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(nav).getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current');
  });

  it('unknown routes show the 404 page with a way home', async () => {
    renderApp('/does/not/exist');
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to Home' })).toBeInTheDocument();
  });

  it('settings switches theme with a radio group', async () => {
    const user = userEvent.setup();
    renderApp('/settings');
    const group = await screen.findByRole('radiogroup', { name: /Theme/ });
    await user.click(within(group).getByRole('radio', { name: /Light/ }));
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(window.localStorage.getItem('arena.theme')).toBe('light');
  });

  it('T cycles the theme, but not while typing', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await screen.findByRole('heading', { name: 'System overview' });
    await user.keyboard('t');
    expect(window.localStorage.getItem('arena.theme')).toBe('light');
    await user.keyboard('{Control>}k{/Control}');
    await user.keyboard('t');
    expect(window.localStorage.getItem('arena.theme')).toBe('light');
  });

  it('the theme button and nav toggle are reachable without shortcuts', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await user.click(await screen.findByRole('button', { name: /^Theme:/ }));
    expect(window.localStorage.getItem('arena.theme')).toBe('light');
    const menu = screen.getByRole('button', { name: 'Open navigation' });
    await user.click(menu);
    expect(menu).toHaveAttribute('aria-expanded', 'true');
    await user.keyboard('{Escape}');
    expect(menu).toHaveAttribute('aria-expanded', 'false');
    expect(menu).toHaveFocus();
  });
});
