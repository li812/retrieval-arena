import { AlertTriangle, RotateCw, ServerCrash } from 'lucide-react';
import type { ReactNode } from 'react';

import { errorText, isApiError } from '@/lib/api/client';

interface InlineErrorProps {
  title: string;
  error?: unknown;
  /** Overrides the text derived from `error`. */
  message?: ReactNode;
  onRetry?: () => void;
  retrying?: boolean;
  /** A link/button to wherever the problem gets fixed (UX-7). */
  fix?: ReactNode;
  tone?: 'error' | 'warn';
}

export function InlineError({
  title,
  error,
  message,
  onRetry,
  retrying,
  fix,
  tone = 'error',
}: InlineErrorProps) {
  const Icon = tone === 'warn' ? AlertTriangle : ServerCrash;
  const requestId = isApiError(error) && error.requestId ? error.requestId : null;
  return (
    <div className="inline-error" data-tone={tone} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon aria-hidden="true" />
      <div className="inline-error-body">
        <div className="inline-error-title">{title}</div>
        <div className="inline-error-text">{message ?? errorText(error)}</div>
        {requestId && (
          <div className="inline-error-text mono" style={{ fontSize: 11 }}>
            request id: {requestId}
          </div>
        )}
        {(onRetry || fix) && (
          <div className="inline-error-actions">
            {onRetry && (
              <button type="button" className="btn" onClick={onRetry} disabled={retrying}>
                <RotateCw aria-hidden="true" />
                {retrying ? 'Retrying…' : 'Retry'}
              </button>
            )}
            {fix}
          </div>
        )}
      </div>
    </div>
  );
}
