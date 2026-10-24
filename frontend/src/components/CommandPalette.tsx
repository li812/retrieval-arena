import { ExternalLink, Monitor, Moon, Palette, Search, Sun, type LucideIcon } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router';

import { NAV_ITEMS } from '@/app/nav';
import { MOD_KEY_LABEL } from '@/app/useGlobalShortcuts';
import { THEME_LABELS, nextMode, type ThemeMode } from '@/lib/theme';
import { useTheme } from '@/lib/themeContext';

import { filterCommands, type Command } from './commands';
import { Kbd } from './Primitives';

const THEME_ICONS: Record<ThemeMode, LucideIcon> = { auto: Monitor, light: Sun, dark: Moon };

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  if (!open) return null;
  return createPortal(<PaletteDialog onClose={onClose} />, document.body);
}

function PaletteDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const { mode, setMode, cycle } = useTheme();
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef<Element | null>(null);
  const baseId = useId();
  const listId = `${baseId}-list`;

  const commands = useMemo<Command[]>(
    () => [
      ...NAV_ITEMS.map<Command>((n) => ({
        id: `go:${n.to}`,
        group: 'Go to',
        label: n.label,
        hint: n.description,
        keywords: n.keywords,
        icon: n.icon,
        run: () => void navigate(n.to),
      })),
      {
        id: 'theme:cycle',
        group: 'Theme',
        label: `Cycle theme (now: ${mode})`,
        hint: `next: ${nextMode(mode)} · T`,
        keywords: 'appearance dark light auto toggle switch',
        icon: Palette,
        run: cycle,
      },
      ...(['auto', 'light', 'dark'] as const).map<Command>((m) => ({
        id: `theme:${m}`,
        group: 'Theme',
        label: `Theme: ${THEME_LABELS[m]}`,
        hint: m === mode ? 'current' : undefined,
        keywords: 'appearance',
        icon: THEME_ICONS[m],
        run: () => setMode(m),
      })),
      {
        id: 'link:classic',
        group: 'Links',
        label: 'Open classic UI',
        hint: 'Lab, chat, Bot Studio',
        keywords: 'legacy alpine old',
        icon: ExternalLink,
        run: () => window.location.assign('/'),
      },
    ],
    [navigate, mode, cycle, setMode],
  );

  const results = useMemo(() => filterCommands(commands, query), [commands, query]);
  const activeIndex = Math.min(active, Math.max(0, results.length - 1));
  const activeCommand = results[activeIndex];
  const optionId = (c: Command) => `${baseId}-opt-${c.id}`;

  // Remember and restore focus; lock background scroll while open.
  useEffect(() => {
    returnFocus.current = document.activeElement;
    inputRef.current?.focus();
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prevOverflow;
      if (returnFocus.current instanceof HTMLElement) returnFocus.current.focus();
    };
  }, []);

  const activeId = activeCommand ? optionId(activeCommand) : undefined;
  useEffect(() => {
    if (!activeId) return;
    const el = document.getElementById(activeId);
    if (el && typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'nearest' });
  }, [activeId]);

  const runCommand = (c: Command | undefined) => {
    if (!c) return;
    onClose();
    c.run();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const n = results.length;
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        if (n) setActive((activeIndex + 1) % n);
        break;
      case 'ArrowUp':
        e.preventDefault();
        if (n) setActive((activeIndex - 1 + n) % n);
        break;
      case 'Home':
        if (e.ctrlKey || e.metaKey || !query) {
          e.preventDefault();
          setActive(0);
        }
        break;
      case 'End':
        if (e.ctrlKey || e.metaKey || !query) {
          e.preventDefault();
          setActive(Math.max(0, n - 1));
        }
        break;
      case 'Enter':
        e.preventDefault();
        runCommand(activeCommand);
        break;
      case 'Escape':
        e.preventDefault();
        e.stopPropagation();
        onClose();
        break;
      case 'Tab': {
        // Focus trap: cycle between the search input and the close button.
        e.preventDefault();
        const next =
          document.activeElement === inputRef.current ? closeRef.current : inputRef.current;
        next?.focus();
        break;
      }
    }
  };

  let lastGroup: string | null = null;

  return (
    <div
      className="palette-overlay"
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onKeyDown={onKeyDown}
      >
        <div className="palette-input-row">
          <Search aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            role="combobox"
            aria-label="Search commands"
            aria-expanded="true"
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={activeId}
            placeholder="Search pages and commands…"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
          />
          <button
            ref={closeRef}
            type="button"
            className="btn btn-ghost icon-btn"
            aria-label="Close command palette"
            onClick={onClose}
          >
            <Kbd>Esc</Kbd>
          </button>
        </div>
        <ul id={listId} role="listbox" aria-label="Commands" className="palette-list">
          {results.map((c, i) => {
            const header = c.group !== lastGroup ? c.group : null;
            lastGroup = c.group;
            const Icon = c.icon;
            return (
              <li key={c.id} role="presentation">
                {header && (
                  <div className="palette-group-label" role="presentation" aria-hidden="true">
                    {header}
                  </div>
                )}
                <div
                  id={optionId(c)}
                  role="option"
                  aria-selected={i === activeIndex}
                  className="palette-item"
                  onPointerMove={() => {
                    if (i !== activeIndex) setActive(i);
                  }}
                  onClick={() => runCommand(c)}
                >
                  <Icon aria-hidden="true" />
                  <span className="palette-label">
                    <span className="sr-only">{c.group}: </span>
                    {c.label}
                  </span>
                  {c.hint && <span className="palette-hint">{c.hint}</span>}
                </div>
              </li>
            );
          })}
        </ul>
        {results.length === 0 && <div className="palette-empty">No commands match “{query}”.</div>}
        <div className="sr-only" role="status" aria-live="polite">
          {results.length} {results.length === 1 ? 'result' : 'results'}
        </div>
        <div className="palette-footer" aria-hidden="true">
          <span>
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> navigate
          </span>
          <span>
            <Kbd>Enter</Kbd> run
          </span>
          <span>
            <Kbd>Esc</Kbd> close
          </span>
          <span style={{ marginLeft: 'auto' }}>
            <Kbd>{MOD_KEY_LABEL} K</Kbd> toggle
          </span>
        </div>
      </div>
    </div>
  );
}
