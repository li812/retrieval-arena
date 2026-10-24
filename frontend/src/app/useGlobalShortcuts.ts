import { useEffect, useRef } from 'react';

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (tag === 'INPUT') {
    const type = (target as HTMLInputElement).type;
    return !['button', 'checkbox', 'radio', 'range', 'submit', 'reset', 'color'].includes(type);
  }
  return false;
}

interface Shortcuts {
  /** Ctrl+K / ⌘K (also works from an iPad hardware keyboard). */
  onPalette: () => void;
  /** "T" when not typing — same key as the classic UI. */
  onCycleTheme: () => void;
  enabled?: boolean;
}

export function useGlobalShortcuts({ onPalette, onCycleTheme, enabled = true }: Shortcuts) {
  const handlers = useRef({ onPalette, onCycleTheme });
  useEffect(() => {
    handlers.current = { onPalette, onCycleTheme };
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        handlers.current.onPalette();
        return;
      }
      if (!enabled || e.defaultPrevented) return;
      if (e.metaKey || e.ctrlKey || e.altKey || isTypingTarget(e.target)) return;
      if (e.key === 't' || e.key === 'T') {
        e.preventDefault();
        handlers.current.onCycleTheme();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [enabled]);
}

export const IS_APPLE =
  typeof navigator !== 'undefined' && /Mac|iPhone|iPad|iPod/i.test(navigator.userAgent);

export const MOD_KEY_LABEL = IS_APPLE ? '⌘' : 'Ctrl';
