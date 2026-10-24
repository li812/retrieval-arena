/**
 * Hand-written types for the legacy (M1) responses the SPA uses.
 * Source of truth: app/main.py, app/schemas.py, app/services/bot_store.py.
 */

export type Provider = 'gemini' | 'nvidia' | (string & {});

/** GET /collections → CollectionSummary[] (app/main.py `_collection_summary`). */
export interface CollectionSummary {
  name: string;
  chunks: number;
  entities: number | null;
  triples: number | null;
  sentiment: Record<string, number> | null;
  sources: { name: string; chunks: number }[];
  embed_provider: string | null;
  embed_model: string | null;
  embed_dim: number | null;
}

/** GET /bots → Bot[] (bot_store `_BOT_COLUMNS`, JSON fields decoded). */
export interface Bot {
  id: number;
  name: string;
  emoji: string;
  description: string;
  system_prompt: string;
  collection: string;
  backend: 'chroma' | 'graph' | 'both';
  provider: Provider;
  gen_model: string;
  embedding_model: string;
  key_id: number | null;
  tuning: Record<string, unknown>;
  greeting: string;
  starters: string[];
  tools: string[];
  created_at: string;
  updated_at: string;
}

/** GET /readyz (B10). 200 when every check is ok, 503 otherwise — same body either way. */
export interface ReadinessCheck {
  ok: boolean;
  latency_ms: number | null;
  error: string | null;
}

export interface Readiness {
  status: string;
  checks: Record<string, ReadinessCheck>;
}

/** GET /healthz (B10). */
export interface Health {
  status: 'ok';
}
