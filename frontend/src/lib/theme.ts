/**
 * Theme preference: `auto` follows the OS, `light`/`dark` are explicit.
 * Stored as a raw string under `arena.theme` — the same key and format as the classic
 * Alpine UI, so the preference is shared between `/` and `/app/`.
 */
export type ThemeMode = 'auto' | 'light' | 'dark';
export type ResolvedTheme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'arena.theme';
export const THEME_MODES: readonly ThemeMode[] = ['auto', 'light', 'dark'];
export const LIGHT_QUERY = '(prefers-color-scheme: light)';

export function isThemeMode(value: unknown): value is ThemeMode {
  return value === 'auto' || value === 'light' || value === 'dark';
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null; // blocked storage (privacy mode, sandboxed iframe)
  }
}

export function readStoredMode(): ThemeMode {
  try {
    const value = storage()?.getItem(THEME_STORAGE_KEY);
    return isThemeMode(value) ? value : 'auto';
  } catch {
    return 'auto';
  }
}

export function storeMode(mode: ThemeMode): void {
  try {
    storage()?.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    /* preference just won't persist */
  }
}

/** Matches the classic UI: auto is dark unless the OS explicitly prefers light. */
export function resolveTheme(mode: ThemeMode, systemPrefersLight: boolean): ResolvedTheme {
  if (mode === 'auto') return systemPrefersLight ? 'light' : 'dark';
  return mode;
}

export function systemPrefersLight(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia(LIGHT_QUERY).matches;
}

export function nextMode(mode: ThemeMode): ThemeMode {
  const i = THEME_MODES.indexOf(mode);
  return THEME_MODES[(i + 1) % THEME_MODES.length] ?? 'auto';
}

export function applyTheme(
  theme: ResolvedTheme,
  root: HTMLElement = document.documentElement,
): void {
  root.dataset.theme = theme;
}

export const THEME_LABELS: Record<ThemeMode, string> = {
  auto: 'Auto (follow system)',
  light: 'Light',
  dark: 'Dark',
};
