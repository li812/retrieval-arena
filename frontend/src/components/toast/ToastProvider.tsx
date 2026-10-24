import { useCallback, useMemo, useReducer, useRef, type ReactNode } from 'react';

import { ToastContext, type Toast, type ToastContextValue, type ToastInput } from './context';
import { Toaster } from './Toaster';

const MAX_VISIBLE = 4;

type Action = { type: 'push'; toast: Toast } | { type: 'dismiss'; id: string };

function reducer(state: Toast[], action: Action): Toast[] {
  switch (action.type) {
    case 'push': {
      const t = action.toast;
      if (t.dedupeKey) {
        const existing = state.find((x) => x.dedupeKey === t.dedupeKey);
        if (existing) {
          const merged: Toast = {
            ...t,
            id: existing.id,
            count: existing.count + 1,
            version: existing.version + 1,
          };
          return [...state.filter((x) => x.id !== existing.id), merged];
        }
      }
      return [...state, t].slice(-MAX_VISIBLE);
    }
    case 'dismiss':
      return state.filter((x) => x.id !== action.id);
  }
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, dispatch] = useReducer(reducer, []);
  const seq = useRef(0);

  const push = useCallback((input: ToastInput) => {
    seq.current += 1;
    const id = `toast-${seq.current}`;
    const kind = input.kind ?? 'info';
    dispatch({
      type: 'push',
      toast: {
        id,
        kind,
        title: input.title,
        message: input.message,
        action: input.action,
        dedupeKey: input.dedupeKey,
        durationMs: input.durationMs ?? (kind === 'error' ? 8000 : 5000),
        count: 1,
        version: 0,
      },
    });
    return id;
  }, []);

  const dismiss = useCallback((id: string) => dispatch({ type: 'dismiss', id }), []);

  const value = useMemo<ToastContextValue>(
    () => ({ toasts, push, dismiss }),
    [toasts, push, dismiss],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <Toaster toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}
