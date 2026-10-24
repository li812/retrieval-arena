import { ExternalLink } from 'lucide-react';
import type { CSSProperties, ReactNode } from 'react';

export function BrandMark() {
  return <span className="brand-mark" aria-hidden="true" />;
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}

export function Skeleton({
  width,
  height = 14,
  style,
}: {
  width?: number | string;
  height?: number;
  style?: CSSProperties;
}) {
  return (
    <span
      className="skeleton"
      aria-hidden="true"
      style={{ width: width ?? '100%', height, ...style }}
    />
  );
}

export type StatusState = 'ok' | 'down' | 'unknown' | 'loading';

export function StatusDot({ state }: { state: StatusState }) {
  return <span className="status-dot" data-state={state} aria-hidden="true" />;
}

/** The Alpine UI at "/" (outside the SPA's /app basename, so a plain anchor). */
export const CLASSIC_UI_HREF = '/';

export function ClassicUiLink({
  children = 'Open classic UI',
  primary = true,
}: {
  children?: ReactNode;
  primary?: boolean;
}) {
  return (
    <a className={primary ? 'btn btn-primary' : 'btn'} href={CLASSIC_UI_HREF}>
      {children}
      <ExternalLink aria-hidden="true" />
    </a>
  );
}
