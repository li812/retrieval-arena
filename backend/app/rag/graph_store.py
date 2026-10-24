from neo4j import GraphDatabase


class GraphStore:
    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def verify_connectivity(self) -> None:
        self._driver.verify_connectivity()

    def merge_triples(self, graph: str, chunk_id: str, triples: list[dict]) -> None:
        def _write(tx, triples):
            for triple in triples:
                tx.run(
                    """
                    MERGE (s:Entity {name: $subject, graph: $graph})
                    MERGE (o:Entity {name: $object, graph: $graph})
                    MERGE (s)-[r:RELATES {type: $relation, graph: $graph, chunk_id: $chunk_id}]->(o)
                    """,
                    subject=triple["subject"],
                    object=triple["object"],
                    relation=triple["relation"],
                    graph=graph,
                    chunk_id=chunk_id,
                )

        with self._driver.session() as session:
            session.execute_write(_write, triples)

    # exact: same name ignoring case · contains: entity name contains the query term
    # fuzzy: containment in either direction, so "Apollo 11 mission" still finds "Apollo 11"
    _MATCH_CLAUSES = {
        "exact": "toLower(e.name) = toLower($name)",
        "contains": "toLower(e.name) CONTAINS toLower($name)",
        "fuzzy": "toLower(e.name) CONTAINS toLower($name) OR toLower($name) CONTAINS toLower(e.name)",
    }

    def find_entities(self, graph: str, names: list[str], mode: str = "contains") -> list[str]:
        clause = self._MATCH_CLAUSES.get(mode, self._MATCH_CLAUSES["contains"])

        def _read(tx, names):
            matched = []
            for name in names:
                result = tx.run(
                    f"""
                    MATCH (e:Entity {{graph: $graph}})
                    WHERE {clause}
                    RETURN e.name AS name
                    """,
                    graph=graph,
                    name=name,
                )
                matched.extend(record["name"] for record in result)
            return list(dict.fromkeys(matched))

        with self._driver.session() as session:
            return session.execute_read(_read, names)

    def traverse(
        self, graph: str, seed_entities: list[str], hops: int, triple_limit: int, direction: str = "out"
    ) -> list[dict]:
        # "both" also follows incoming edges, so entities that only appear as objects still expand
        pattern = "-[r:RELATES]->" if direction == "out" else "-[r:RELATES]-"
        all_triples: list[dict] = []
        seen: set[tuple] = set()
        current_seeds = list(seed_entities)

        for _hop in range(hops):
            if not current_seeds:
                break

            def _read(tx, seeds):
                result = tx.run(
                    f"""
                    MATCH (a:Entity {{graph: $graph}}){pattern}(b:Entity {{graph: $graph}})
                    WHERE a.name IN $seeds
                    RETURN startNode(r).name AS subject, r.type AS relation, endNode(r).name AS object,
                           b.name AS neighbor
                    LIMIT $triple_limit
                    """,
                    graph=graph,
                    seeds=seeds,
                    triple_limit=triple_limit,
                )
                return [
                    {
                        "subject": rec["subject"],
                        "relation": rec["relation"],
                        "object": rec["object"],
                        "neighbor": rec["neighbor"],
                    }
                    for rec in result
                ]

            with self._driver.session() as session:
                hop_triples = session.execute_read(_read, current_seeds)

            next_seeds: set[str] = set()
            for triple in hop_triples:
                key = (triple["subject"], triple["relation"], triple["object"])
                if key not in seen:
                    seen.add(key)
                    all_triples.append(triple)
                next_seeds.add(triple["neighbor"])

            current_seeds = list(next_seeds - set(seed_entities))
            if len(all_triples) >= triple_limit:
                break

        return all_triples[:triple_limit]

    def entities_for_chunks(self, graph: str, chunk_ids: list[str]) -> dict[str, list[str]]:
        """Entities mentioned in each chunk's extracted triples, for keyword chips on chunk cards."""

        def _read(tx):
            result = tx.run(
                """
                MATCH (s:Entity)-[r:RELATES {graph: $graph}]->(o:Entity)
                WHERE r.chunk_id IN $ids
                RETURN r.chunk_id AS chunk_id, collect(DISTINCT s.name) + collect(DISTINCT o.name) AS names
                """,
                graph=graph,
                ids=chunk_ids,
            )
            return {rec["chunk_id"]: list(dict.fromkeys(rec["names"])) for rec in result}

        with self._driver.session() as session:
            return session.execute_read(_read)

    def stats(self, graph: str) -> dict:
        def _read(tx):
            rec = tx.run(
                """
                OPTIONAL MATCH (e:Entity {graph: $graph})
                WITH count(e) AS entities
                OPTIONAL MATCH ()-[r:RELATES {graph: $graph}]->()
                RETURN entities, count(r) AS triples
                """,
                graph=graph,
            ).single()
            return {"entities": rec["entities"], "triples": rec["triples"]}

        with self._driver.session() as session:
            return session.execute_read(_read)

    def delete_graph(self, graph: str) -> None:
        def _write(tx):
            tx.run("MATCH (e:Entity {graph: $graph}) DETACH DELETE e", graph=graph)

        with self._driver.session() as session:
            session.execute_write(_write)

    def close(self) -> None:
        self._driver.close()
