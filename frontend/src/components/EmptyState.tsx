import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
  /** Exactly one primary next action (UX-4). */
  action: ReactNode;
  hint?: ReactNode;
  tour?: string;
}

export function EmptyState({ icon: Icon, title, children, action, hint, tour }: EmptyStateProps) {
  return (
    <div className="empty-state" data-tour={tour}>
      <div className="empty-icon" aria-hidden="true">
        <Icon />
      </div>
      <h2 className="empty-title">{title}</h2>
      <p className="empty-text">{children}</p>
      <div>{action}</div>
      {hint && <p className="empty-hint">{hint}</p>}
    </div>
  );
}
