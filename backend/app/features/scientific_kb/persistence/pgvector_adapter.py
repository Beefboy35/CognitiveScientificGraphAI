"""pgvector-адаптер поверх единой таблицы ``scikb_embeddings``.

Источник истины графа — Neo4j. Векторы (384-dim) живут в одной PG-таблице с
HNSW-индексом по cosine. Каждая запись:

    (target_kind, target_id, embedding vector(384), model, created_at)

``target_id`` ссылается на id узла в Neo4j (DocumentChunk или ScientificClaim).
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)


def _vec_literal(values: list[float] | tuple[float, ...]) -> str:
    return "[" + ",".join(f"{float(v):.6f}" for v in values) + "]"


def _row_id(target_kind: str, target_id: str) -> str:
    digest = hashlib.sha256(f"{target_kind}:{target_id}".encode("utf-8")).hexdigest()[:24]
    return f"emb_{digest}"


class PgVectorAdapter:
    """Векторный поиск + хранение embeddings через одну PG-таблицу."""

    def __init__(self, postgres_adapter: Any, vector_dim: int = 384) -> None:
        self._pg = postgres_adapter
        self.vector_dim = vector_dim
        self._extension_ready: bool | None = None

    def is_active(self) -> bool:
        if not getattr(self._pg, "is_active", lambda: False)():
            return False
        if self._extension_ready is None:
            self._extension_ready = self._probe_extension()
        return bool(self._extension_ready)

    def _probe_extension(self) -> bool:
        session = self._pg._session()
        if session is None:
            return False
        try:
            from sqlalchemy import text

            ext = session.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).first()
            tab = session.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name='scikb_embeddings'")
            ).first()
            return ext is not None and tab is not None
        except Exception as exc:
            logger.debug("pgvector_probe_failed", extra={"error": str(exc)})
            return False
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    def _upsert_pairs(self, target_kind: str, pairs: Iterable[tuple[str, list[float]]], *, model: str = "deterministic") -> int:
        if not self.is_active():
            return 0
        from sqlalchemy import text

        session = self._pg._session()
        if session is None:
            return 0
        updated = 0
        try:
            for target_id, vec in pairs:
                vec = list(vec or [])
                if not vec:
                    continue
                if len(vec) < self.vector_dim:
                    vec = vec + [0.0] * (self.vector_dim - len(vec))
                elif len(vec) > self.vector_dim:
                    vec = vec[: self.vector_dim]
                session.execute(
                    text(
                        """
                        INSERT INTO scikb_embeddings (id, target_kind, target_id, model, embedding)
                        VALUES (:id, :kind, :tid, :model, CAST(:vec AS vector))
                        ON CONFLICT (target_kind, target_id) DO UPDATE
                          SET embedding = EXCLUDED.embedding,
                              model = EXCLUDED.model
                        """
                    ),
                    {
                        "id": _row_id(target_kind, target_id),
                        "kind": target_kind,
                        "tid": target_id,
                        "model": model,
                        "vec": _vec_literal(vec),
                    },
                )
                updated += 1
            session.commit()
        except Exception as exc:
            logger.debug("pgvector_upsert_failed", extra={"error": str(exc), "kind": target_kind})
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()
        return updated

    def upsert_chunk_embeddings(self, chunks: Iterable[Any], *, model: str = "deterministic") -> int:
        pairs = []
        for chunk in chunks:
            vec = list(chunk.embedding or [])
            if vec:
                pairs.append((chunk.id, vec))
        return self._upsert_pairs("chunk", pairs, model=model)

    def upsert_claim_embeddings(self, claim_pairs: Iterable[tuple[str, list[float]]], *, model: str = "deterministic") -> int:
        return self._upsert_pairs("claim", claim_pairs, model=model)

    # ------------------------------------------------------------------
    # Similarity search
    # ------------------------------------------------------------------

    def _search(self, target_kind: str, query_vector: list[float], top_k: int) -> list[dict[str, Any]]:
        if not self.is_active():
            return []
        from sqlalchemy import text

        session = self._pg._session()
        if session is None:
            return []
        try:
            rows = session.execute(
                text(
                    """
                    SELECT target_id,
                           1 - (embedding <=> CAST(:vec AS vector)) AS similarity
                    FROM scikb_embeddings
                    WHERE target_kind = :kind
                    ORDER BY embedding <=> CAST(:vec AS vector)
                    LIMIT :k
                    """
                ),
                {"vec": _vec_literal(query_vector), "kind": target_kind, "k": top_k},
            ).all()
            return [
                {"target_id": row.target_id, "similarity": float(row.similarity or 0.0)}
                for row in rows
            ]
        except Exception as exc:
            logger.debug("pgvector_search_failed", extra={"error": str(exc), "kind": target_kind})
            return []
        finally:
            session.close()

    def search_similar_chunks(self, query_vector: list[float], top_k: int = 10) -> list[dict[str, Any]]:
        return [{"id": r["target_id"], **r} for r in self._search("chunk", query_vector, top_k)]

    def search_similar_claims(self, query_vector: list[float], top_k: int = 10) -> list[dict[str, Any]]:
        return [{"id": r["target_id"], **r} for r in self._search("claim", query_vector, top_k)]

    def find_near_duplicate_claim(
        self,
        query_vector: list[float],
        *,
        threshold: float = 0.92,
        exclude_target_id: str | None = None,
        exclude_publication_id: str | None = None,  # noqa: ARG002 — резервно, не используется здесь
    ) -> dict[str, Any] | None:
        """Ищет похожий claim среди embeddings.

        `exclude_target_id` — критически важен: без него лукап нашёл бы
        тот же самый claim, который мы ищем (similarity=1.0), и pipeline
        создал бы self-loop SUPPORTS-связь claim → claim. Этот баг
        реально воспроизводился (68 self-loops на 68 claims в bootstrap).
        """
        # Берём top-5 чтобы было что отсеять при exclude.
        results = self.search_similar_claims(query_vector, top_k=5)
        for row in results:
            if exclude_target_id is not None and row.get("target_id") == exclude_target_id:
                continue
            if row["similarity"] >= threshold:
                return row
        return None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def delete_by_target(self, target_kind: str, target_ids: Iterable[str]) -> int:
        if not self.is_active():
            return 0
        from sqlalchemy import text

        session = self._pg._session()
        if session is None:
            return 0
        removed = 0
        try:
            for tid in target_ids:
                session.execute(
                    text(
                        "DELETE FROM scikb_embeddings WHERE target_kind = :kind AND target_id = :tid"
                    ),
                    {"kind": target_kind, "tid": tid},
                )
                removed += 1
            session.commit()
        except Exception as exc:
            logger.debug("pgvector_delete_failed", extra={"error": str(exc)})
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()
        return removed
