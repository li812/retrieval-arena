import { Command as CommandIcon, ExternalLink, Menu, Monitor, Moon, Sun, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router';

import { CommandPalette } from '@/components/CommandPalette';
import { BrandMark, CLASSIC_UI_HREF, Kbd } from '@/components/Primitives';
import { THEME_LABELS, nextMode } from '@/lib/theme';
import { useTheme } from '@/lib/themeContext';

import { NAV_ITEMS, navItemFor } from './nav';
import { MOD_KEY_LABEL, useGlobalShortcuts } from './useGlobalShortcuts';

const THEME_ICON = { auto: Monitor, light: Sun, dark: Moon } as const;
const DRAWER_QUERY = '(max-width: 1023.98px)';

export function AppShell() {
  const location = useLocation();
  const { mode, cycle } = useTheme();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const menuBtnRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const mainRef = useRef<HTMLElement>(null);

  const current = navItemFor(location.pathname);
  const title = current?.label ?? 'Not found';

  useGlobalShortcuts({
    onPalette: () => setPaletteOpen((o) => !o),
    onCycleTheme: cycle,
    enabled: !paletteOpen,
  });

  useEffect(() => {
    document.title = `${title} · Retrieval Arena`;
  }, [title]);

  // Page accent: the legacy .mode-* classes retint --accent per section.
  useEffect(() => {
    const cls = `mode-${current?.accent ?? 'chroma'}`;
    document.body.classList.add(cls);
    return () => document.body.classList.remove(cls);
  }, [current?.accent]);

  // Close the drawer on navigation.
  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  const closeNav = useCallback(() => {
    setNavOpen(false);
    menuBtnRef.current?.focus();
  }, []);

  // Drawer: Esc closes, focus moves into it when opened.
  useEffect(() => {
    if (!navOpen) return;
    const nav = sidebarRef.current;
    (
      nav?.querySelector<HTMLElement>('.nav-list a[aria-current="page"]') ??
      nav?.querySelector<HTMLElement>('.nav-list a')
    )?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeNav();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [navOpen, closeNav]);

  // If the window grows past the drawer breakpoint, drop the drawer state.
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const mql = window.matchMedia(DRAWER_QUERY);
    const onChange = () => {
      if (!mql.matches) setNavOpen(false);
    };
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  const ThemeIcon = THEME_ICON[mode];

  return (
    <div className="shell" data-nav-open={navOpen}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <aside
        ref={sidebarRef}
        className="sidebar"
        id="app-sidebar"
        aria-label="Main navigation"
        data-tour="sidebar"
      >
        <div className="sidebar-top">
          <Link to="/" className="brand" aria-label="Retrieval Arena home">
            <BrandMark />
            <span className="brand-text">
              <span className="brand-title">Retrieval Arena</span>
              <span className="brand-sub">control plane · m1</span>
            </span>
          </Link>
          <button
            type="button"
            className="btn btn-ghost icon-btn sidebar-close"
            aria-label="Close navigation"
            onClick={closeNav}
          >
            <X aria-hidden="true" />
          </button>
        </div>

        <nav aria-label="Pages">
          <div className="nav-section-label">Workspace</div>
          <ul className="nav-list">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              return (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === '/'}
                    className="nav-link"
                    style={{ ['--nav-accent' as string]: `var(--accent-${item.accent})` }}
                    data-tour={`nav-${item.label.toLowerCase()}`}
                  >
                    <Icon aria-hidden="true" />
                    {item.label}
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="sidebar-footer">
          <a className="nav-link" href={CLASSIC_UI_HREF} data-tour="classic-ui">
            <ExternalLink aria-hidden="true" />
            Classic UI
            <span className="tag nav-tag">lab · chat</span>
          </a>
        </div>
      </aside>

      <button
        type="button"
        className="nav-scrim"
        aria-label="Close navigation"
        tabIndex={-1}
        onClick={closeNav}
      />

      <div className="shell-main">
        <header className="topbar">
          <button
            ref={menuBtnRef}
            type="button"
            className="btn btn-ghost icon-btn menu-toggle"
            aria-label="Open navigation"
            aria-controls="app-sidebar"
            aria-expanded={navOpen}
            onClick={() => setNavOpen(true)}
          >
            <Menu aria-hidden="true" />
          </button>
          <div className="topbar-title">
            <h1>{title}</h1>
            {current && <span className="crumb">/app{current.to === '/' ? '' : current.to}</span>}
          </div>
          <button
            type="button"
            className="palette-trigger"
            onClick={() => setPaletteOpen(true)}
            aria-label="Open command palette"
            aria-keyshortcuts="Meta+K Control+K"
            data-tour="palette"
          >
            <CommandIcon aria-hidden="true" size={15} />
            <span className="palette-trigger-label">Jump to…</span>
            <Kbd>{MOD_KEY_LABEL} K</Kbd>
          </button>
          <button
            type="button"
            className="btn icon-btn"
            onClick={cycle}
            aria-label={`Theme: ${THEME_LABELS[mode]}. Switch to ${THEME_LABELS[nextMode(mode)]}`}
            title={`Theme: ${mode} (T)`}
            aria-keyshortcuts="T"
            data-tour="theme"
          >
            <ThemeIcon aria-hidden="true" />
          </button>
        </header>

        <main id="main" ref={mainRef} className="content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
