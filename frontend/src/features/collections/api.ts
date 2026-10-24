import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api/client';
import type { CollectionSummary } from '@/lib/api/types';

export const collectionKeys = {
  all: ['collections'] as const,
};

export function fetchCollections(signal?: AbortSignal): Promise<CollectionSummary[]> {
  return api.get<CollectionSummary[]>('/collections', { signal });
}

export function useCollections() {
  return useQuery({
    queryKey: collectionKeys.all,
    queryFn: ({ signal }) => fetchCollections(signal),
    meta: { errorTitle: "Couldn't load collections" },
  });
}
