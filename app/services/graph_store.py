from neo4j import GraphDatabase
from app.config import settings


class GraphStore:
    def __init__(self):
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

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

    def find_entities(self, graph: str, names: list[str]) -> list[str]:
        def _read(tx, names):
            matched = []
            for name in names:
                result = tx.run(
                    """
                    MATCH (e:Entity {graph: $graph})
                    WHERE toLower(e.name) CONTAINS toLower($name)
                    RETURN e.name AS name
                    """,
                    graph=graph,
                    name=name,
                )
                matched.extend(record["name"] for record in result)
            return matched

        with self._driver.session() as session:
            return session.execute_read(_read, names)

    def traverse(
        self, graph: str, seed_entities: list[str], hops: int, triple_limit: int
    ) -> list[dict]:
        all_triples: list[dict] = []
        seen: set[tuple] = set()
        current_seeds = list(seed_entities)

        for hop in range(hops):
            if not current_seeds:
                break

            def _read(tx, seeds):
                result = tx.run(
                    """
                    MATCH (s:Entity {graph: $graph})-[r:RELATES]->(o:Entity {graph: $graph})
                    WHERE s.name IN $seeds
                    RETURN s.name AS subject, r.type AS relation, o.name AS object
                    LIMIT $triple_limit
                    """,
                    graph=graph,
                    seeds=seeds,
                    triple_limit=triple_limit,
                )
                return [
                    {"subject": rec["subject"], "relation": rec["relation"], "object": rec["object"]}
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
                next_seeds.add(triple["object"])

            current_seeds = list(next_seeds - set(seed_entities))
            if len(all_triples) >= triple_limit:
                break

        return all_triples[:triple_limit]

    def close(self) -> None:
        self._driver.close()
