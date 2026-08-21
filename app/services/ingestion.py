import logging
import time

from app.schemas import IngestResult

logger = logging.getLogger(__name__)


class IngestionAgent:
    def __init__(self, chunking, embedding_agent, vector_store, graph_store, extraction_agent):
        self._chunking = chunking
        self._embedding_agent = embedding_agent
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._extraction_agent = extraction_agent

    def ingest(
        self,
        text: str,
        collection: str,
        tuning,
        api_key: str,
        embedding_model: str,
        gen_model: str,
        chunk_id_prefix: str = "",
    ) -> IngestResult:
        if not chunk_id_prefix:
            chunk_id_prefix = f"{collection}_chunk"

        logger.info(
            "[ingest] start collection=%s prefix=%s text_len=%d",
            collection, chunk_id_prefix, len(text),
        )

        t0 = time.perf_counter()
        chunks = self._chunking.chunk(
            text,
            strategy=tuning.chunking_strategy,
            chunk_size=tuning.chunk_size,
            chunk_overlap=tuning.chunk_overlap,
        )
        logger.info("[ingest] chunking done chunks=%d (%.1fs)", len(chunks), time.perf_counter() - t0)

        t1 = time.perf_counter()
        embeddings = self._embedding_agent.embed_documents(chunks, api_key, embedding_model)
        logger.info(
            "[ingest] embedding done embeddings=%d (%.1fs)",
            len(embeddings), time.perf_counter() - t1,
        )

        ids = [f"{chunk_id_prefix}_{i:04d}" for i in range(len(chunks))]
        self._vector_store.add_chunks(collection, chunks, embeddings, ids)
        logger.info("[ingest] vector store upsert done chunks=%d", len(chunks))

        total_triples = 0
        t2 = time.perf_counter()
        for idx, (chunk_id, chunk) in enumerate(zip(ids, chunks)):
            triples = self._extraction_agent.extract_triples(
                chunk, api_key, gen_model, tuning.max_triples_per_chunk
            )
            if triples:
                self._graph_store.merge_triples(collection, chunk_id, triples)
                total_triples += len(triples)
            if (idx + 1) % 10 == 0 or (idx + 1) == len(chunks):
                logger.info(
                    "[ingest] triples %d/%d triples_so_far=%d (%.1fs)",
                    idx + 1, len(chunks), total_triples, time.perf_counter() - t2,
                )

        logger.info(
            "[ingest] done collection=%s chunks=%d triples=%d total=%.1fs",
            collection, len(chunks), total_triples, time.perf_counter() - t0,
        )

        return IngestResult(
            collection=collection,
            documents=1,
            num_chunks=len(chunks),
            num_triples=total_triples,
            embedding_model=embedding_model,
        )
