import { useQuery } from '@tanstack/react-query';

import { ApiError, api } from '@/lib/api/client';
import type { Readiness } from '@/lib/api/types';

export const systemKeys = {
  readiness: ['system', 'readiness'] as const,
};

function isReadiness(body: unknown): body is Readiness {
  if (!body || typeof body !== 'object') return false;
  const checks = (body as { checks?: unknown }).checks;
  return !!checks && typeof checks === 'object';
}

/** GET /readyz. A 503 is a valid answer (some dependency is down), not a failure. */
export async function fetchReadiness(signal?: AbortSignal): Promise<Readiness> {
  const body = await api.get<unknown>('/readyz', { signal, acceptStatuses: [503] });
  if (!isReadiness(body)) {
    throw new ApiError({
      status: 503,
      detail: 'The readiness endpoint answered without any checks.',
      requestId: '',
      body,
      path: '/readyz',
    });
  }
  return body;
}

export function useReadiness() {
  return useQuery({
    queryKey: systemKeys.readiness,
    queryFn: ({ signal }) => fetchReadiness(signal),
    refetchInterval: 15_000,
    staleTime: 5_000,
    // Home renders readiness errors inline; a toast every 15 s would be noise.
    meta: { silent: true },
  });
}
