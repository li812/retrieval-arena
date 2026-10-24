import { QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense, useRef, useState, type ReactNode } from 'react';

import { ToastProvider } from '@/components/toast/ToastProvider';
import { useToast } from '@/components/toast/context';
import { createQueryClient } from '@/lib/queryClient';

import { ThemeProvider } from './ThemeProvider';

// Devtools are dev-only: this import is dropped from production builds.
const ReactQueryDevtools = import.meta.env.DEV
  ? lazy(() =>
      import('@tanstack/react-query-devtools').then((m) => ({ default: m.ReactQueryDevtools })),
    )
  : null;

function QueryProvider({ children }: { children: ReactNode }) {
  const { push } = useToast();
  const pushRef = useRef(push);
  pushRef.current = push;

  const [client] = useState(() =>
    createQueryClient((notice) => {
      pushRef.current({
        kind: 'error',
        title: notice.title,
        message: notice.message,
        dedupeKey: notice.dedupeKey,
        action: {
          label: 'Retry',
          onClick: () => void client.refetchQueries({ type: 'active' }),
        },
      });
    }),
  );

  return (
    <QueryClientProvider client={client}>
      {children}
      {ReactQueryDevtools && import.meta.env.MODE !== 'test' && (
        <Suspense fallback={null}>
          <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-right" />
        </Suspense>
      )}
    </QueryClientProvider>
  );
}

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <ToastProvider>
        <QueryProvider>{children}</QueryProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}
