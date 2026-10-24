import { describe, expect, it } from 'vitest';

import {
  THEME_STORAGE_KEY,
  applyTheme,
  isThemeMode,
  nextMode,
  readStoredMode,
  resolveTheme,
  storeMode,
} from './theme';

describe('theme mode resolution', () => {
  it('auto follows the system preference, dark unless the OS asks for light', () => {
    expect(resolveTheme('auto', true)).toBe('light');
    expect(resolveTheme('auto', false)).toBe('dark');
  });

  it('explicit modes ignore the system', () => {
    expect(resolveTheme('light', false)).toBe('light');
    expect(resolveTheme('dark', true)).toBe('dark');
  });

  it('cycles auto → light → dark → auto like the classic UI', () => {
    expect(nextMode('auto')).toBe('light');
    expect(nextMode('light')).toBe('dark');
    expect(nextMode('dark')).toBe('auto');
  });

  it('validates modes', () => {
    expect(isThemeMode('dark')).toBe(true);
    expect(isThemeMode('sepia')).toBe(false);
    expect(isThemeMode(null)).toBe(false);
  });
});

describe('theme persistence', () => {
  it('uses the shared arena.theme key with a raw string value', () => {
    storeMode('light');
    expect(window.localStorage.getItem('arena.theme')).toBe('light');
    expect(THEME_STORAGE_KEY).toBe('arena.theme');
    expect(readStoredMode()).toBe('light');
  });

  it('defaults to auto when nothing or garbage is stored', () => {
    expect(readStoredMode()).toBe('auto');
    window.localStorage.setItem('arena.theme', '"dark"'); // JSON-encoded is not what the classic UI writes
    expect(readStoredMode()).toBe('auto');
  });

  it('survives blocked storage', () => {
    const original = Object.getOwnPropertyDescriptor(window, 'localStorage');
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get() {
        throw new Error('SecurityError');
      },
    });
    try {
      expect(readStoredMode()).toBe('auto');
      expect(() => storeMode('dark')).not.toThrow();
    } finally {
      if (original) Object.defineProperty(window, 'localStorage', original);
    }
  });

  it('applies the resolved theme to <html data-theme>', () => {
    applyTheme('light');
    expect(document.documentElement.dataset.theme).toBe('light');
  });
});
