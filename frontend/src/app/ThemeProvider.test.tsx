import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { useTheme } from '@/lib/themeContext';

import { ThemeProvider } from './ThemeProvider';

function Probe() {
  const { mode, resolved, cycle, setMode } = useTheme();
  return (
    <div>
      <span data-testid="mode">{mode}</span>
      <span data-testid="resolved">{resolved}</span>
      <button onClick={cycle}>cycle</button>
      <button onClick={() => setMode('dark')}>dark</button>
    </div>
  );
}

/** matchMedia whose listeners we can fire. */
function controllableMatchMedia(initialLight: boolean) {
  const listeners = new Set<(e: MediaQueryListEvent) => void>();
  const state = { matches: initialLight };
  window.matchMedia = vi.fn((query: string) => ({
    get matches() {
      return state.matches;
    },
    media: query,
    onchange: null,
    addEventListener: (_: string, l: (e: MediaQueryListEvent) => void) => listeners.add(l),
    removeEventListener: (_: string, l: (e: MediaQueryListEvent) => void) => listeners.delete(l),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
  return (light: boolean) => {
    state.matches = light;
    listeners.forEach((l) => l({ matches: light } as MediaQueryListEvent));
  };
}

describe('ThemeProvider', () => {
  it('starts from the stored preference and sets data-theme', () => {
    window.localStorage.setItem('arena.theme', 'light');
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId('mode')).toHaveTextContent('light');
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('follows the OS live while in auto', () => {
    const setSystemLight = controllableMatchMedia(false);
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(document.documentElement.dataset.theme).toBe('dark');
    act(() => setSystemLight(true));
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(screen.getByTestId('mode')).toHaveTextContent('auto');
  });

  it('cycles and persists the choice', async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    await user.click(screen.getByText('cycle'));
    expect(screen.getByTestId('mode')).toHaveTextContent('light');
    expect(window.localStorage.getItem('arena.theme')).toBe('light');
    await user.click(screen.getByText('dark'));
    expect(window.localStorage.getItem('arena.theme')).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('picks up a change made in another tab (e.g. the classic UI)', () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: 'arena.theme', newValue: 'light' }));
    });
    expect(screen.getByTestId('mode')).toHaveTextContent('light');
    expect(document.documentElement.dataset.theme).toBe('light');
  });
});
