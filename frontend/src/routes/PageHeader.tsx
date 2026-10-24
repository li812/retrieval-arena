import type { ReactNode } from 'react';

export function PageHeader({
  eyebrow,
  title,
  children,
  actions,
}: {
  eyebrow: string;
  title: string;
  children?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h2 className="page-title">{title}</h2>
        {children && <p className="page-lede">{children}</p>}
      </div>
      {actions}
    </header>
  );
}
