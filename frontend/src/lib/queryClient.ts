import { QueryCache, QueryClient, type Query } from '@tanstack/react-query';

import { isApiError } from './api/client';

declare module '@tanstack/react-query' {
  interface Register {
    queryMeta: {
      /** Toast title when this query fails, e.g. "Couldn't load bots". */
      errorTitle?: string;
      /** Don't toast failures — the page shows the error inline. */
      silent?: boolean;
    };
  }
}

export interface QueryErrorNotice {
  title: string;
  message: string;
  dedupeKey: string;
  unreachable: boolean;
}

/** Turn a failed query into the toast text. Exported for tests. */
export function describeQueryError(error: unknown, query: Pick<Query, 'meta'>): QueryErrorNotice {
  if (isApiError(error) && error.isUnreachable) {
    return {
      title: 'Backend unreachable',
      message: error.detail,
      dedupeKey: 'api-unreachable',
      unreachable: true,
    };
  }
  const title = query.meta?.errorTitle ?? 'Request failed';
  const message = error instanceof Error ? error.message : 'Unknown error';
  return { title, message, dedupeKey: `${title}:${message}`, unreachable: false };
}

export function shouldRetry(failureCount: number, error: unknown): boolean {
  // Client errors won't fix themselves; everything else gets one retry.
  if (isApiError(error) && error.status >= 400 && error.status < 500) return false;
  return failureCount < 1;
}

export function createQueryClient(onError?: (notice: QueryErrorNotice) => void): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (query.meta?.silent) return;
        onError?.(describeQueryError(error, query));
      },
    }),
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        staleTime: 30_000,
        refetchOnWindowFocus: true,
      },
    },
  });
}
