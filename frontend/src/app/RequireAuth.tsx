import type { ReactNode } from 'react';

/**
 * Auth guard. M1 has no accounts, so it passes through; M2 (UI-2 / AUTH-*) wires it to the
 * session and redirects to /login when there is none.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
