import { Bot, Boxes, Library, RotateCw } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';

import { HelpTip } from '@/components/HelpTip';
import { InlineError } from '@/components/InlineError';
import { ClassicUiLink, Skeleton, StatusDot, type StatusState } from '@/components/Primitives';
import { useBots } from '@/features/bots/api';
import { useCollections } from '@/features/collections/api';
import { useReadiness } from '@/features/system/api';
import { isApiError } from '@/lib/api/client';
import type { ReadinessCheck } from '@/lib/api/types';
import { CHECK_INFO } from '@/features/system/checks';

import { PageHeader } from './PageHeader';

const KNOWN_CHECKS = Object.keys(CHECK_INFO);

function checkState(check: ReadinessCheck | undefined): StatusState {
  if (!check) return 'unknown';
  return check.ok ? 'ok' : 'down';
}

const STATE_TEXT: Record<StatusState, string> = {
  ok: 'Operational',
  down: 'Unavailable',
  unknown: 'Not reported',
  loading: 'Checking…',
};

function ReadinessPanel() {
  const readiness = useReadiness();
  const { data, error, isPending, isFetching, refetch, dataUpdatedAt } = readiness;

  const names = data
    ? [...KNOWN_CHECKS, ...Object.keys(data.checks).filter((n) => !KNOWN_CHECKS.includes(n))]
    : KNOWN_CHECKS;
  const allOk = data ? names.every((n) => data.checks[n]?.ok) : false;

  let body: ReactNode;
  if (isPending) {
    body = (
      <ul className="check-list" aria-busy="true" aria-label="Loading readiness checks">
        {KNOWN_CHECKS.map((n) => (
          <li key={n} className="check" data-state="loading">
            <div className="check-head">
              <StatusDot state="loading" />
              <span className="check-name">{CHECK_INFO[n]?.label}</span>
            </div>
            <Skeleton width="60%" />
          </li>
        ))}
      </ul>
    );
  } else if (error && !data) {
    if (isApiError(error) && error.status === 404) {
      body = (
        <InlineError
          tone="warn"
          title="Health checks aren’t available on this backend yet"
          message="This API version has no /readyz endpoint, so per-service status can’t be shown. Update the backend, then retry."
          onRetry={() => void refetch()}
          retrying={isFetching}
        />
      );
    } else if (isApiError(error) && error.isUnreachable) {
      body = (
        <InlineError
          title="Can’t reach the API server"
          error={error}
          message={
            <>
              {error.detail} With Docker, run <code>docker compose up</code> in the project folder.
            </>
          }
          onRetry={() => void refetch()}
          retrying={isFetching}
        />
      );
    } else {
      body = (
        <InlineError
          title="Couldn’t check readiness"
          error={error}
          onRetry={() => void refetch()}
          retrying={isFetching}
        />
      );
    }
  } else {
    body = (
      <ul className="check-list">
        {names.map((name) => {
          const check = data.checks[name];
          const state = checkState(check);
          const info = CHECK_INFO[name] ?? {
            label: name,
            help: `Dependency check “${name}” reported by the backend.`,
          };
          return (
            <li key={name} className="check" data-state={state} data-testid={`check-${name}`}>
              <div className="check-head">
                <StatusDot state={state} />
                <span className="check-name">{info.label}</span>
                <HelpTip label={info.label}>{info.help}</HelpTip>
              </div>
              <div className="check-meta">
                <span>{STATE_TEXT[state]}</span>
                {check?.latency_ms != null && (
                  <span className="check-latency">{Math.round(check.latency_ms)} ms</span>
                )}
              </div>
              {check && !check.ok && check.error && (
                <div className="check-error">{check.error}</div>
              )}
            </li>
          );
        })}
      </ul>
    );
  }

  const overall: StatusState = isPending ? 'loading' : data ? (allOk ? 'ok' : 'down') : 'unknown';
  const overallText = isPending
    ? 'Checking'
    : data
      ? allOk
        ? 'All systems go'
        : 'Degraded'
      : 'Unavailable';

  return (
    <section className="panel" aria-labelledby="readiness-title" data-tour="readiness">
      <div className="panel-header">
        <h3 className="panel-title" id="readiness-title">
          Readiness
        </h3>
        <HelpTip label="readiness">
          Whether the API can reach each service it depends on right now. Checked every 15 seconds
          while this page is open.
        </HelpTip>
        <div className="panel-actions">
          <span
            className="badge"
            data-tone={overall === 'loading' ? undefined : overall}
            role="status"
          >
            <StatusDot state={overall} />
            {overallText}
          </span>
          <button
            type="button"
            className="btn btn-ghost icon-btn"
            aria-label="Re-check readiness now"
            title="Re-check now"
            onClick={() => void refetch()}
            disabled={isFetching}
          >
            <RotateCw aria-hidden="true" />
          </button>
        </div>
      </div>
      <div className="panel-body">
        {body}
        {data && dataUpdatedAt > 0 && (
          <p className="empty-hint" style={{ marginTop: 12 }}>
            Last checked {new Date(dataUpdatedAt).toLocaleTimeString()}
          </p>
        )}
      </div>
    </section>
  );
}

interface StatTileProps {
  label: string;
  icon: typeof Bot;
  accent: string;
  help: string;
  isPending: boolean;
  error: unknown;
  onRetry: () => void;
  value: number | undefined;
  detail: ReactNode;
  empty: ReactNode;
  footer?: ReactNode;
  tour: string;
  wide?: boolean;
}

function StatTile(p: StatTileProps) {
  const Icon = p.icon;
  let content: ReactNode;
  if (p.isPending) {
    content = (
      <>
        <Skeleton width={64} height={36} style={{ margin: '4px 0' }} />
        <Skeleton width="70%" />
      </>
    );
  } else if (isApiError(p.error) && p.error.isUnreachable) {
    // The readiness panel already explains the outage; keep the tiles quiet.
    content = (
      <>
        <div className="stat-value" aria-label="unknown">
          —
        </div>
        <div className="stat-detail">Waiting for the API server…</div>
      </>
    );
  } else if (p.error) {
    content = (
      <InlineError
        title={`Couldn’t load ${p.label.toLowerCase()}`}
        error={p.error}
        onRetry={p.onRetry}
      />
    );
  } else if (p.value === 0) {
    content = (
      <>
        <div className="stat-value">0</div>
        {p.empty}
      </>
    );
  } else {
    content = (
      <>
        <div className="stat-value">{p.value}</div>
        <div className="stat-detail">{p.detail}</div>
        {p.footer && <div className="stat-foot">{p.footer}</div>}
      </>
    );
  }
  return (
    <section
      className={`panel stat${p.wide ? ' stat-wide' : ''}`}
      style={{ ['--stat-accent' as string]: p.accent }}
      aria-label={p.label}
      aria-busy={p.isPending}
      data-tour={p.tour}
    >
      <div className="stat-label">
        <Icon aria-hidden="true" />
        {p.label}
        <HelpTip label={p.label}>{p.help}</HelpTip>
      </div>
      {content}
    </section>
  );
}

export default function Home() {
  const collections = useCollections();
  const bots = useBots();

  const cols = collections.data;
  const totalChunks = cols?.reduce((sum, c) => sum + c.chunks, 0) ?? 0;
  const graphCols = cols?.filter((c) => (c.entities ?? 0) > 0).length ?? 0;
  const totalEntities = cols?.reduce((sum, c) => sum + (c.entities ?? 0), 0) ?? 0;

  return (
    <div className="page">
      <PageHeader eyebrow="Overview" title="System overview">
        Health of the services behind Retrieval Arena and what’s in it.
      </PageHeader>

      <ReadinessPanel />

      <div className="grid grid-3">
        <StatTile
          label="Collections"
          icon={Library}
          accent="var(--accent-graph)"
          help="A collection is a set of documents you ingested, searchable as vectors and optionally as a knowledge graph."
          isPending={collections.isPending}
          error={collections.error}
          onRetry={() => void collections.refetch()}
          value={cols?.length}
          detail={graphCols > 0 ? `${graphCols} with a knowledge graph` : 'Vector search only'}
          empty={
            <div className="stat-foot">
              <span className="stat-detail">No collections yet.</span>
              <ClassicUiLink>Ingest documents</ClassicUiLink>
            </div>
          }
          footer={
            <Link className="btn" to="/collections">
              View collections
            </Link>
          }
          tour="stat-collections"
        />
        <StatTile
          label="Chunks indexed"
          icon={Boxes}
          accent="var(--accent-chroma)"
          help="Documents are split into chunks before embedding; retrieval returns the best-matching chunks. Entities are things the graph extractor found."
          isPending={collections.isPending}
          error={collections.error}
          onRetry={() => void collections.refetch()}
          value={cols ? totalChunks : undefined}
          detail={`${totalEntities.toLocaleString()} graph entities`}
          empty={<span className="stat-detail">Chunks appear once you ingest a document.</span>}
          tour="stat-chunks"
        />
        <StatTile
          label="Bots"
          icon={Bot}
          accent="var(--accent-chat)"
          help="Bots are chat assistants that answer from a collection with their own prompt, model and tools."
          isPending={bots.isPending}
          error={bots.error}
          onRetry={() => void bots.refetch()}
          value={bots.data?.length}
          detail={bots.data
            ?.slice(0, 3)
            .map((b) => `${b.emoji} ${b.name}`)
            .join(' · ')}
          empty={
            <div className="stat-foot">
              <span className="stat-detail">No bots yet.</span>
              <ClassicUiLink>Create your first bot</ClassicUiLink>
            </div>
          }
          footer={
            <Link className="btn" to="/bots">
              View bots
            </Link>
          }
          tour="stat-bots"
          wide
        />
      </div>
    </div>
  );
}
