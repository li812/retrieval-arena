import logging
import time
from concurrent.futures import ThreadPoolExecutor

from app.schemas import IngestResult

logger = logging.getLogger(__name__)


class IngestionAgent:
    def __init__(self, chunking, embedding_agent, vector_store, graph_store, extraction_agent, key_store=None):
        self._chunking = chunking
        self._embedding_agent = embedding_agent
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._extraction_agent = extraction_agent
        self._key_store = key_store

    def ingest(
        self,
        text: str,
        collection: str,
        tuning,
        api_key: str,
        embedding_model: str,
        gen_model: str,
        chunk_id_prefix: str = "",
        provider: str = "gemini",
        source: str = "pasted text",
    ) -> IngestResult:
        if not chunk_id_prefix:
            chunk_id_prefix = f"{collection}_chunk"

        logger.info(
            "[ingest] start collection=%s prefix=%s text_len=%d provider=%s",
            collection, chunk_id_prefix, len(text), provider,
        )

        t0 = time.perf_counter()
        chunks = self._chunking.chunk(
            text,
            strategy=tuning.chunking_strategy,
            chunk_size=tuning.chunk_size,
            chunk_overlap=tuning.chunk_overlap,
        )
        logger.info("[ingest] chunking done chunks=%d (%.1fs)", len(chunks), time.perf_counter() - t0)

        if getattr(tuning, "contextual_headers", False):
            tc = time.perf_counter()
            chunks = self._add_contextual_headers(text, chunks, api_key, gen_model, provider)
            logger.info("[ingest] contextual headers done (%.1fs)", time.perf_counter() - tc)

        t1 = time.perf_counter()
        embeddings = self._embedding_agent.embed_documents(chunks, api_key, embedding_model, provider=provider)
        logger.info(
            "[ingest] embedding done embeddings=%d (%.1fs)",
            len(embeddings), time.perf_counter() - t1,
        )

        if self._key_store and embeddings:
            embed_dim = len(embeddings[0])
            try:
                self._key_store.register_collection(collection, provider, embedding_model, embed_dim)
            except ValueError as exc:
                raise ValueError(str(exc))

        ids = [f"{chunk_id_prefix}_{i:04d}" for i in range(len(chunks))]
        metadatas = [{"source": source, "doc": chunk_id_prefix, "seq": i} for i in range(len(chunks))]
        self._vector_store.add_chunks(collection, chunks, embeddings, ids, metadatas)
        logger.info("[ingest] vector store upsert done chunks=%d", len(chunks))

        total_triples = 0
        t2 = time.perf_counter()
        for idx, (chunk_id, chunk) in enumerate(zip(ids, chunks)):
            triples = self._extraction_agent.extract_triples(
                chunk, api_key, gen_model, tuning.max_triples_per_chunk, provider=provider
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

    def _add_contextual_headers(
        self, document: str, chunks: list[str], api_key: str, gen_model: str, provider: str
    ) -> list[str]:
        """Contextual retrieval: prefix each chunk with an LLM-written line placing it in the document."""
        doc_excerpt = document[:8000]

        def header(chunk: str) -> str:
            prompt = (
                f"<document>\n{doc_excerpt}\n</document>\n"
                f"Here is a chunk from that document:\n<chunk>\n{chunk}\n</chunk>\n"
                "Write one short sentence that situates this chunk within the overall document, "
                "to improve search retrieval of the chunk. Answer only with that sentence."
            )
            try:
                line = self._extraction_agent.complete(prompt, api_key, gen_model, provider, max_tokens=256)
            except Exception as exc:
                logger.warning("[ingest] contextual header failed: %s", exc)
                return chunk
            return f"[Context: {line.strip()}]\n{chunk}" if line.strip() else chunk

        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(header, chunks))
