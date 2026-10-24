import { Bot } from 'lucide-react';

import { EmptyState } from '@/components/EmptyState';
import { ClassicUiLink } from '@/components/Primitives';
import { useBots } from '@/features/bots/api';

import { PageHeader } from './PageHeader';

export default function Bots() {
  const bots = useBots();
  const count = bots.data?.length;
  return (
    <div className="page">
      <PageHeader eyebrow="Build" title="Bots">
        Chat bots answer from your collections with their own prompt, model and tools.
      </PageHeader>
      <section className="panel" data-tour="bots-empty">
        <EmptyState
          icon={Bot}
          title="Bot Studio is still in the classic UI"
          action={<ClassicUiLink>Open Bot Studio</ClassicUiLink>}
          hint={
            count === undefined
              ? undefined
              : count === 0
                ? 'You have no bots yet — create your first one there.'
                : `You have ${count} ${count === 1 ? 'bot' : 'bots'}; they will show up here when the new Studio ships.`
          }
        >
          Creating, editing and chatting with bots moves to this dashboard in a later release. Until
          then, use Bot Studio in the classic interface — everything you make there will carry over.
        </EmptyState>
      </section>
    </div>
  );
}
