import { Library } from 'lucide-react';

import { EmptyState } from '@/components/EmptyState';
import { ClassicUiLink } from '@/components/Primitives';
import { useCollections } from '@/features/collections/api';

import { PageHeader } from './PageHeader';

export default function Collections() {
  const collections = useCollections();
  const count = collections.data?.length;
  return (
    <div className="page">
      <PageHeader eyebrow="Knowledge" title="Collections">
        Collections hold your ingested documents as vectors (Chroma) and, optionally, a knowledge
        graph (Neo4j).
      </PageHeader>
      <section className="panel" data-tour="collections-empty">
        <EmptyState
          icon={Library}
          title="Ingest documents in the classic UI"
          action={<ClassicUiLink>Open classic UI to ingest</ClassicUiLink>}
          hint={
            count === undefined
              ? undefined
              : count === 0
                ? 'No collections yet — upload a .txt or .pdf to create one.'
                : `${count} ${count === 1 ? 'collection' : 'collections'} found; browsing them here arrives with the new Collections page.`
          }
        >
          Uploading files, choosing a chunking strategy and building graphs happen in the classic
          interface for now.
        </EmptyState>
      </section>
    </div>
  );
}
