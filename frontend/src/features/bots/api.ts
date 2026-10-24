import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { Bot } from '@/lib/api/types';

export const botKeys = {
  all: ['bots'] as const,
};

export function fetchBots(signal?: AbortSignal): Promise<Bot[]> {
  return api.get<Bot[]>('/bots', { signal });
}

export function useBots() {
  return useQuery({
    queryKey: botKeys.all,
    queryFn: ({ signal }) => fetchBots(signal),
    meta: { errorTitle: "Couldn't load bots" },
  });
}
