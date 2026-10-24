import type { LucideIcon } from 'lucide-react';

export interface Command {
  id: string;
  group: 'Go to' | 'Theme' | 'Links';
  label: string;
  hint?: string;
  keywords?: string;
  icon: LucideIcon;
  run: () => void;
}

/** Every whitespace-separated term must appear somewhere in the command's text. */
export function filterCommands(commands: readonly Command[], query: string): Command[] {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return [...commands];
  return commands.filter((c) => {
    const hay = `${c.group} ${c.label} ${c.keywords ?? ''} ${c.hint ?? ''}`.toLowerCase();
    return terms.every((t) => hay.includes(t));
  });
}
