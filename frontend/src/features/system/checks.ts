export interface CheckInfo {
  label: string;
  help: string;
}

/** Plain-language explanations for each /readyz check (UX-3). */
export const CHECK_INFO: Record<string, CheckInfo> = {
  sqlite: {
    label: 'SQLite',
    help: 'The app database: provider keys, bots, conversations and query history. If it is down nothing can be saved — usually a full disk or wrong permissions on the data volume.',
  },
  chroma: {
    label: 'Chroma',
    help: 'The vector database holding your document chunks for similarity search. If it is down, ingest and Chroma queries fail. Check that the chroma container is running.',
  },
  neo4j: {
    label: 'Neo4j',
    help: 'The graph database holding entities and relations extracted from your documents. If it is down, graph queries and graph ingest fail; plain vector search still works.',
  },
};
