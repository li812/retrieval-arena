import { FlaskConical } from 'lucide-react';

import { EmptyState } from '@/components/EmptyState';
import { ClassicUiLink } from '@/components/Primitives';

import { PageHeader } from './PageHeader';

export default function Lab() {
  return (
    <div className="page">
      <PageHeader eyebrow="Experiment" title="Retrieval Lab">
        Ask a question and watch how Chroma, the knowledge graph, or both side by side retrieve and
        answer.
      </PageHeader>
      <section className="panel" data-tour="lab-empty">
        <EmptyState
          icon={FlaskConical}
          title="The Lab is in the classic UI for now"
          action={<ClassicUiLink>Open the Lab</ClassicUiLink>}
          hint="Search modes, reranking and Compare all work there today."
        >
          The Retrieval Lab is being rebuilt for this dashboard. Until it lands, run your
          experiments in the classic interface.
        </EmptyState>
      </section>
    </div>
  );
}
