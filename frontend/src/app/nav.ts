import { Bot, FlaskConical, Gauge, Library, Settings, type LucideIcon } from 'lucide-react';

export type Accent = 'chroma' | 'graph' | 'chat';

export interface NavItem {
  /** Path relative to the /app basename. */
  to: string;
  label: string;
  description: string;
  icon: LucideIcon;
  /** Which legacy accent tints this page (`.mode-*` classes from tokens.css). */
  accent: Accent;
  keywords: string;
}

export const NAV_ITEMS: readonly NavItem[] = [
  {
    to: '/',
    label: 'Home',
    description: 'System status and overview',
    icon: Gauge,
    accent: 'chroma',
    keywords: 'overview dashboard status health readiness',
  },
  {
    to: '/bots',
    label: 'Bots',
    description: 'Chat bots built on your collections',
    icon: Bot,
    accent: 'chat',
    keywords: 'chat studio assistant',
  },
  {
    to: '/collections',
    label: 'Collections',
    description: 'Ingested documents and knowledge graphs',
    icon: Library,
    accent: 'graph',
    keywords: 'documents knowledge ingest graph vectors',
  },
  {
    to: '/lab',
    label: 'Lab',
    description: 'Retrieval experiments: Chroma, Graph, Compare',
    icon: FlaskConical,
    accent: 'chroma',
    keywords: 'retrieval query compare arena experiment',
  },
  {
    to: '/settings',
    label: 'Settings',
    description: 'Appearance and provider keys',
    icon: Settings,
    accent: 'chroma',
    keywords: 'preferences theme keys config',
  },
];

export function navItemFor(pathname: string): NavItem | undefined {
  if (pathname === '/' || pathname === '') return NAV_ITEMS[0];
  return NAV_ITEMS.find(
    (n) => n.to !== '/' && (pathname === n.to || pathname.startsWith(`${n.to}/`)),
  );
}
