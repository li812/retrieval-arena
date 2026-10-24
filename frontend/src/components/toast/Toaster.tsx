import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import type { Toast, ToastKind } from './context';

const ICONS: Record<ToastKind, typeof Info> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
};

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: string) => void }) {
  const [paused, setPaused] = useState(false);
  const remaining = useRef(toast.durationMs);
  const started = useRef(0);

  // Reset the countdown when a duplicate refreshes this toast.
  useEffect(() => {
    remaining.current = toast.durationMs;
  }, [toast.version, toast.durationMs]);

  useEffect(() => {
    if (paused || toast.durationMs <= 0) return;
    started.current = Date.now();
    const timer = window.setTimeout(() => onDismiss(toast.id), remaining.current);
    return () => {
      window.clearTimeout(timer);
      remaining.current = Math.max(0, remaining.current - (Date.now() - started.current));
    };
  }, [paused, toast.id, toast.version, toast.durationMs, onDismiss]);

  const Icon = ICONS[toast.kind];
  const urgent = toast.kind === 'error';

  return (
    <li
      className="toast"
      data-kind={toast.kind}
      role={urgent ? 'alert' : 'status'}
      aria-live={urgent ? 'assertive' : 'polite'}
      aria-atomic="true"
      onPointerEnter={(e) => {
        if (e.pointerType === 'mouse') setPaused(true);
      }}
      onPointerLeave={(e) => {
        if (e.pointerType === 'mouse') setPaused(false);
      }}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <Icon className="toast-icon" aria-hidden="true" />
      <div className="toast-body">
        <div className="toast-title">
          {toast.title}
          {toast.count > 1 && (
            <span className="toast-count" aria-label={`${toast.count} times`}>
              ×{toast.count}
            </span>
          )}
        </div>
        {toast.message && <div className="toast-message">{toast.message}</div>}
        {toast.action && (
          <div className="toast-actions">
            <button
              type="button"
              className="btn"
              onClick={() => {
                toast.action?.onClick();
                onDismiss(toast.id);
              }}
            >
              {toast.action.label}
            </button>
          </div>
        )}
      </div>
      <button
        type="button"
        className="btn btn-ghost icon-btn toast-close"
        aria-label="Dismiss notification"
        onClick={() => onDismiss(toast.id)}
      >
        <X aria-hidden="true" />
      </button>
    </li>
  );
}

export function Toaster({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: string) => void;
}) {
  return (
    <ol className="toast-viewport" aria-label="Notifications">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </ol>
  );
}
