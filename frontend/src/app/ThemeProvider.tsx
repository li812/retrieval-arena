import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';

import { ThemeContext, type ThemeContextValue } from '@/lib/themeContext';
import {
  LIGHT_QUERY,
  THEME_STORAGE_KEY,
  applyTheme,
  isThemeMode,
  nextMode,
  readStoredMode,
  resolveTheme,
  storeMode,
  systemPrefersLight,
  type ThemeMode,
} from '@/lib/theme';

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readStoredMode);
  const [prefersLight, setPrefersLight] = useState<boolean>(systemPrefersLight);

  // Follow the OS live (only matters in auto, but tracking it always is cheap).
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const mql = window.matchMedia(LIGHT_QUERY);
    const onChange = (e: MediaQueryListEvent) => setPrefersLight(e.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  // Another tab (e.g. the classic UI) changed the preference.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== THEME_STORAGE_KEY) return;
      setModeState(isThemeMode(e.newValue) ? e.newValue : 'auto');
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const resolved = resolveTheme(mode, prefersLight);

  useEffect(() => {
    applyTheme(resolved);
  }, [resolved]);

  const setMode = useCallback((next: ThemeMode) => {
    storeMode(next);
    setModeState(next);
  }, []);

  const cycle = useCallback(() => {
    setModeState((current) => {
      const next = nextMode(current);
      storeMode(next);
      return next;
    });
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ mode, resolved, setMode, cycle }),
    [mode, resolved, setMode, cycle],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
