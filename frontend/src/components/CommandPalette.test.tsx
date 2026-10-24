import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { jsonResponse, mockFetch, READY_OK, renderApp } from '@/test/utils';

import type { Command } from './commands';
import { filterCommands } from './commands';

beforeEach(() => {
  mockFetch({
    '/readyz': jsonResponse(READY_OK),
    '/collections': jsonResponse([]),
    '/bots': jsonResponse([]),
  });
});

async function openPalette() {
  const user = userEvent.setup();
  renderApp('/');
  await screen.findByRole('heading', { name: 'System overview' });
  await user.keyboard('{Control>}k{/Control}');
  const dialog = await screen.findByRole('dialog', { name: 'Command palette' });
  return { user, dialog };
}

describe('CommandPalette', () => {
  it('opens with Ctrl+K and focuses the search box', async () => {
    const { dialog } = await openPalette();
    const input = within(dialog).getByRole('combobox', { name: 'Search commands' });
    expect(input).toHaveFocus();
    expect(within(dialog).getAllByRole('option').length).toBeGreaterThanOrEqual(5);
    expect(dialog).toHaveAttribute('aria-modal', 'true');
  });

  it('opens with ⌘K (iPad / Mac hardware keyboard)', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await user.keyboard('{Meta>}k{/Meta}');
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('arrow keys move the active option and Enter runs it', async () => {
    const { user, dialog } = await openPalette();
    const input = within(dialog).getByRole('combobox');
    const options = within(dialog).getAllByRole('option');
    expect(options[0]).toHaveAttribute('aria-selected', 'true');
    expect(input).toHaveAttribute('aria-activedescendant', options[0]!.id);

    await user.keyboard('{ArrowDown}');
    expect(options[1]).toHaveAttribute('aria-selected', 'true');
    expect(input).toHaveAttribute('aria-activedescendant', options[1]!.id);

    await user.keyboard('{ArrowUp}{ArrowUp}'); // wraps to the last item
    expect(options[options.length - 1]).toHaveAttribute('aria-selected', 'true');

    await user.keyboard('{Home}{ArrowDown}{Enter}'); // → Bots
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(await screen.findByRole('heading', { name: 'Bots', level: 2 })).toBeInTheDocument();
  });

  it('filters as you type and runs the match', async () => {
    const { user, dialog } = await openPalette();
    await user.keyboard('sett');
    const options = within(dialog).getAllByRole('option');
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveTextContent('Settings');
    await user.keyboard('{Enter}');
    expect(await screen.findByRole('heading', { name: 'Settings', level: 2 })).toBeInTheDocument();
  });

  it('shows an empty message when nothing matches', async () => {
    const { user, dialog } = await openPalette();
    await user.keyboard('zzzz');
    expect(within(dialog).queryAllByRole('option')).toHaveLength(0);
    expect(dialog).toHaveTextContent('No commands match');
  });

  it('cycles the theme from the palette', async () => {
    const { user } = await openPalette();
    await user.keyboard('cycle{Enter}');
    expect(window.localStorage.getItem('arena.theme')).toBe('light');
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('Esc closes and returns focus to where it was', async () => {
    const user = userEvent.setup();
    renderApp('/');
    const trigger = await screen.findByRole('button', { name: 'Open command palette' });
    await user.click(trigger);
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('traps Tab inside the dialog', async () => {
    const { user, dialog } = await openPalette();
    const input = within(dialog).getByRole('combobox');
    const close = within(dialog).getByRole('button', { name: 'Close command palette' });
    await user.tab();
    expect(close).toHaveFocus();
    await user.tab();
    expect(input).toHaveFocus();
    await user.tab({ shift: true });
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
  });

  it('Ctrl+K toggles it closed again', async () => {
    const { user } = await openPalette();
    await user.keyboard('{Control>}k{/Control}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('filterCommands', () => {
  const cmd = (label: string, keywords = ''): Command => ({
    id: label,
    group: 'Go to',
    label,
    keywords,
    icon: (() => null) as unknown as Command['icon'],
    run: () => undefined,
  });
  it('matches every term across label and keywords, case-insensitively', () => {
    const list = [cmd('Home', 'overview status'), cmd('Bots', 'chat'), cmd('Lab', 'retrieval')];
    expect(filterCommands(list, 'STATUS').map((c) => c.label)).toEqual(['Home']);
    expect(filterCommands(list, 'go chat').map((c) => c.label)).toEqual(['Bots']);
    expect(filterCommands(list, '  ')).toHaveLength(3);
  });
});
