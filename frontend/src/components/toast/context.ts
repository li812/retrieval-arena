import { createContext, useContext } from 'react';

export type ToastKind = 'info' | 'success' | 'warning' | 'error';

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface ToastInput {
  kind?: ToastKind;
  title: string;
  message?: string;
  action?: ToastAction;
  /** Toasts with the same key replace each other (and show a ×N counter) instead of stacking. */
  dedupeKey?: string;
  /** Auto-dismiss delay; 0 keeps it until closed. Defaults: 5 s, errors 8 s. */
  durationMs?: number;
}

export interface Toast extends Required<Pick<ToastInput, 'title'>> {
  id: string;
  kind: ToastKind;
  message?: string;
  action?: ToastAction;
  dedupeKey?: string;
  durationMs: number;
  count: number;
  /** Bumped on every dedupe hit so the item restarts its timer. */
  version: number;
}

export interface ToastContextValue {
  toasts: Toast[];
  push: (input: ToastInput) => string;
  dismiss: (id: string) => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>');
  return ctx;
}
