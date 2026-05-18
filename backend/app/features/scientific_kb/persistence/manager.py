from __future__ import annotations

import logging
from typing import Any

from .neo4j_adapter import Neo4jAdapter
from .pgvector_adapter import PgVectorAdapter
from .postgres_adapter import PostgresAdapter

logger = logging.getLogger(__name__)


class PersistenceManager:
    """Fan-out persistence calls to PostgreSQL and Neo4j with graceful degradation.

    The project intentionally focuses on two stores:

    * **PostgreSQL** — single source of truth for operational data
      (jobs/steps/runs/evaluations/feedback/queue) and scientific tables
      (publications/chunks/entities/claims/relations).
    * **Neo4j** — weighted knowledge graph for multi-hop traversal and
      Cypher-based queries.

    Vector similarity is computed in-process over chunk and claim embeddings
    (see :mod:`embedding_service`).  Activation keys are kept in-process as
    well — for a single FastAPI replica a dedicated cache layer is overkill.
    """

    def __init__(
        self,
        *,
        pg_dsn: str | None = None,
        neo4j_uri: str | None = None,
        neo4j_user: str | None = None,
        neo4j_password: str | None = None,
        enable_postgres: bool = True,
        enable_neo4j: bool = True,
        vector_dim: int = 384,
    ) -> None:
        self.postgres = PostgresAdapter(pg_dsn) if enable_postgres else _Inactive()
        self.neo4j = Neo4jAdapter(neo4j_uri, neo4j_user, neo4j_password) if enable_neo4j else _Inactive()
        self.pgvector = PgVectorAdapter(self.postgres, vector_dim=vector_dim) if enable_postgres else _Inactive()

    def _dispatch(self, method: str, *args: Any, **kwargs: Any) -> None:
        for adapter in (self.postgres, self.neo4j):
            fn = getattr(adapter, method, None)
            if fn is None:
                continue
            try:
                fn(*args, **kwargs)
            except Exception as exc:
                logger.debug("persistence_dispatch_failed", extra={"method": method, "error": str(exc)})

    # The pipeline calls these methods (see pipeline.py) — every method fans out.
    def upsert_publication(self, publication: Any) -> None:
        self._dispatch("upsert_publication", publication)

    def upsert_chunks(self, chunks: Any, *, publication: Any | None = None) -> None:
        chunks_list = list(chunks)
        # Chunks хранятся как узлы в Neo4j (CONTAINS_CHUNK от Publication).
        self._dispatch("upsert_chunks", chunks_list, publication=publication)
        # Embeddings — в единой PG-таблице scikb_embeddings.
        try:
            self.pgvector.upsert_chunk_embeddings(chunks_list)
        except Exception as exc:
            logger.debug("pgvector_upsert_chunks_skip", extra={"error": str(exc)})

    def upsert_entities(self, entities: Any) -> None:
        self._dispatch("upsert_entities", entities)

    def upsert_claims(self, claims: Any, *, publication: Any | None = None) -> None:
        claims_list = list(claims)
        # Claims хранятся как узлы в Neo4j (CONTAINS_CLAIM от Publication).
        self._dispatch("upsert_claims", claims_list, publication=publication)
        # Embeddings — в единой PG-таблице scikb_embeddings.
        try:
            from ..utils import deterministic_embedding

            pairs = [
                (claim.id, deterministic_embedding(claim.claim_text))
                for claim in claims_list
                if getattr(claim, "claim_text", None)
            ]
            if pairs:
                self.pgvector.upsert_claim_embeddings(pairs)
        except Exception as exc:
            logger.debug("pgvector_upsert_claims_skip", extra={"error": str(exc)})

    def upsert_claim(self, claim: Any) -> None:
        self._dispatch("upsert_claim", claim)

    def upsert_relations(self, relations: Any) -> None:
        self._dispatch("upsert_relations", relations)

    def upsert_relation(self, relation: Any) -> None:
        self._dispatch("upsert_relation", relation)

    def sync_graph(self, publication: Any) -> None:
        self._dispatch("sync_graph", publication)

    def cache_activation(self, publication_id: str, keys: list[str]) -> None:
        # Activation keys live in-process; this is a no-op intentionally kept
        # so pipeline.py does not need to branch on persistence shape.
        return

    def upsert_job(self, job: Any, *, publication: Any | None = None) -> None:
        self._dispatch("upsert_job", job, publication=publication)

    def upsert_step(self, job: Any, step: Any) -> None:
        self._dispatch("upsert_step", job, step)

    def upsert_rag_answer(self, rag: Any) -> None:
        self._dispatch("upsert_rag_answer", rag)

    def upsert_evaluation(self, record: Any) -> None:
        self._dispatch("upsert_evaluation", record)

    def upsert_feedback_event(self, event: Any) -> None:
        self._dispatch("upsert_feedback_event", event)

    def upsert_review_item(self, item: dict[str, Any]) -> None:
        self._dispatch("upsert_review_item", item)

    def reset_demo_storage(self, scientific_kb: Any) -> None:
        for adapter in (self.postgres, self.neo4j):
            try:
                adapter.reset_demo_storage(scientific_kb)
            except Exception as exc:
                logger.debug("persistence_reset_failed", extra={"error": str(exc)})

    def status(self) -> dict[str, bool]:
        return {
            "postgres": getattr(self.postgres, "is_active", lambda: False)(),
            "neo4j": getattr(self.neo4j, "is_active", lambda: False)(),
            "pgvector": getattr(self.pgvector, "is_active", lambda: False)(),
        }


class _Inactive:
    """No-op adapter when a backend is explicitly disabled in settings."""

    def is_active(self) -> bool:
        return False

    def __getattr__(self, name: str):
        def _noop(*args: Any, **kwargs: Any) -> None:
            return None

        return _noop
