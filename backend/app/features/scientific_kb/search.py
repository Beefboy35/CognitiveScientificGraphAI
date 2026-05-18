from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any

from .models import DocumentChunk, Publication, ScientificClaim, ScientificEntity, SearchHit
from .ontology import ALIASES
from .utils import _cosine, _expanded_query_tokens, _tokenize, deterministic_embedding


def _safe_get_settings() -> Any:
    try:
        from app.config.settings import settings

        return settings
    except Exception:
        return None


def _chunk_from_payload(payload: dict[str, Any]) -> DocumentChunk:
    """Превращает Neo4j-payload в DocumentChunk (только нужные для скоринга поля)."""
    return DocumentChunk(
        id=payload.get("id") or "",
        publication_id=payload.get("publication_id") or "",
        chunk_index=int(payload.get("chunk_index") or 0),
        text=payload.get("text") or "",
        page_start=int(payload.get("page_start") or 1),
        page_end=int(payload.get("page_end") or 1),
        section=payload.get("section") or "Body",
        embedding=[],
        metadata=payload.get("metadata") or {},
    )


def _claim_from_payload(payload: dict[str, Any]) -> ScientificClaim:
    return ScientificClaim(
        id=payload.get("id") or "",
        claim_text=payload.get("claim_text") or "",
        claim_type=payload.get("claim_type") or "method_description",
        subject_entity=payload.get("subject_entity") or "",
        predicate=payload.get("predicate") or "",
        object_entity=payload.get("object_entity") or "",
        comparison_target=payload.get("comparison_target"),
        condition=payload.get("condition"),
        metric=payload.get("metric"),
        value=payload.get("value"),
        evidence_text=payload.get("evidence_text") or payload.get("claim_text") or "",
        publication_id=payload.get("publication_id") or "",
        chunk_id=payload.get("chunk_id") or "",
        page_start=int(payload.get("page_start") or 1),
        page_end=int(payload.get("page_end") or 1),
        confidence_score=float(payload.get("confidence_score") or 0.7),
        evidence_strength=float(payload.get("evidence_strength") or 0.7),
        source_reliability=float(payload.get("source_reliability") or 0.7),
        extraction_run_id=payload.get("extraction_run_id") or "",
    )


def _publication_from_payload(payload: dict[str, Any]) -> Publication:
    return Publication(
        id=payload.get("id") or "",
        title=payload.get("title") or "",
        abstract=payload.get("abstract") or "",
        source_type=payload.get("source_type") or "text",
        authors=list(payload.get("authors") or []),
        year=int(payload.get("year") or 2026),
        status=payload.get("status") or "ready",
        pages=int(payload.get("pages") or 1),
        metadata=payload.get("metadata") or {},
    )


class ScientificSearchMixin:
    def activation_keys(self, question: str) -> dict[str, Any]:
        tokens = _tokenize(question)
        expanded = set(tokens)
        for token in tokens:
            canonical = ALIASES.get(token)
            if canonical:
                expanded.update(_tokenize(canonical))
        for entity in self.entities.values():
            name_tokens = set(_tokenize(entity.canonical_name))
            if name_tokens & expanded:
                expanded.update(name_tokens)
                for alias in entity.aliases:
                    expanded.update(_tokenize(alias))
        keys = sorted(k for k in expanded if len(k) > 2)
        activated = {"entities": set(), "claims": set(), "chunks": set()}
        for key in keys:
            bucket = self.activation_index.get(key)
            if not bucket:
                continue
            activated["entities"].update(bucket["entities"])
            activated["claims"].update(bucket["claims"])
            activated["chunks"].update(bucket["chunks"])
        return {
            "question": question,
            "activation_keys": keys,
            "activated_entities": [asdict(self.entities[i]) for i in sorted(activated["entities"]) if i in self.entities],
            "activated_claims": [asdict(self.claims[i]) for i in sorted(activated["claims"]) if i in self.claims],
            "activated_chunks": [asdict(self.chunks[i]) for i in sorted(activated["chunks"]) if i in self.chunks],
        }

    def search_keyword(self, query: str, top_k: int = 8) -> list[SearchHit]:
        query_tokens = Counter(_expanded_query_tokens(query))
        hits: list[SearchHit] = []
        for chunk in self.chunks.values():
            tokens = Counter(_tokenize(chunk.text))
            overlap = sum(min(tokens[t], query_tokens[t]) for t in query_tokens)
            score = overlap / max(1, len(query_tokens))
            if score:
                hits.append(self._chunk_hit(chunk, score, {"keyword": score}))
        for claim in self.claims.values():
            tokens = Counter(_tokenize(claim.claim_text))
            overlap = sum(min(tokens[t], query_tokens[t]) for t in query_tokens)
            score = min(1.0, overlap / max(1, len(query_tokens)) + 0.08)
            if score > 0.08:
                hits.append(self._claim_hit(claim, score, {"keyword": score}))
        return sorted(hits, key=lambda h: h.score, reverse=True)[:top_k]

    def search_semantic(self, query: str, top_k: int = 8) -> list[SearchHit]:
        vector = self._embed_query(query)
        # 1) Сначала пробуем pgvector — он отдаёт top_k за O(log n) через HNSW.
        pgvector = self._pgvector_adapter()
        if pgvector is not None:
            hits = self._semantic_via_pgvector(vector, top_k, pgvector)
            if hits:
                return hits
        # 2) Fallback: in-process bruteforce cosine. Корректно для маленького демо.
        hits: list[SearchHit] = []
        for chunk in self.chunks.values():
            score = max(0.0, _cosine(vector, chunk.embedding))
            hits.append(self._chunk_hit(chunk, score, {"semantic": score}))
        for claim in self.claims.values():
            score = max(0.0, _cosine(vector, self._embed_query(claim.claim_text)))
            hits.append(self._claim_hit(claim, score, {"semantic": score}))
        return sorted(hits, key=lambda h: h.score, reverse=True)[:top_k]

    def _pgvector_adapter(self) -> Any:
        persistence = getattr(self, "persistence", None)
        if persistence is None:
            return None
        adapter = getattr(persistence, "pgvector", None)
        if adapter is None or not getattr(adapter, "is_active", lambda: False)():
            return None
        return adapter

    def _neo4j_adapter(self) -> Any:
        persistence = getattr(self, "persistence", None)
        if persistence is None:
            return None
        adapter = getattr(persistence, "neo4j", None)
        if adapter is None or not getattr(adapter, "is_active", lambda: False)():
            return None
        return adapter

    def _fetch_chunks_by_ids(self, ids: list[str]) -> dict[str, DocumentChunk]:
        """Достаёт DocumentChunk по id: сначала in-memory, затем Cypher fallback."""
        result: dict[str, DocumentChunk] = {}
        missing: list[str] = []
        for cid in ids:
            chunk = self.chunks.get(cid)
            if chunk is not None:
                result[cid] = chunk
            else:
                missing.append(cid)
        if missing:
            adapter = self._neo4j_adapter()
            if adapter is not None and hasattr(adapter, "fetch_chunks_by_ids"):
                payloads = adapter.fetch_chunks_by_ids(missing)
                for cid, payload in (payloads or {}).items():
                    result[cid] = _chunk_from_payload(payload)
        return result

    def _fetch_claims_by_ids(self, ids: list[str]) -> dict[str, ScientificClaim]:
        result: dict[str, ScientificClaim] = {}
        missing: list[str] = []
        for cid in ids:
            claim = self.claims.get(cid)
            if claim is not None:
                result[cid] = claim
            else:
                missing.append(cid)
        if missing:
            adapter = self._neo4j_adapter()
            if adapter is not None and hasattr(adapter, "fetch_claims_by_ids"):
                payloads = adapter.fetch_claims_by_ids(missing)
                for cid, payload in (payloads or {}).items():
                    result[cid] = _claim_from_payload(payload)
        return result

    def _fetch_publication(self, publication_id: str) -> Publication | None:
        pub = self.publications.get(publication_id)
        if pub is not None:
            return pub
        adapter = self._neo4j_adapter()
        if adapter is not None and hasattr(adapter, "fetch_publications_by_ids"):
            payloads = adapter.fetch_publications_by_ids([publication_id])
            payload = (payloads or {}).get(publication_id)
            if payload:
                return _publication_from_payload(payload)
        return None

    def _semantic_via_pgvector(
        self, vector: list[float], top_k: int, pgvector: Any
    ) -> list[SearchHit]:
        hits: list[SearchHit] = []
        chunk_rows = pgvector.search_similar_chunks(vector, top_k=top_k)
        claim_rows = pgvector.search_similar_claims(vector, top_k=top_k)
        chunks_map = self._fetch_chunks_by_ids([row["id"] for row in chunk_rows])
        claims_map = self._fetch_claims_by_ids([row["id"] for row in claim_rows])
        for row in chunk_rows:
            chunk = chunks_map.get(row["id"])
            if chunk is None:
                continue
            hits.append(self._chunk_hit(chunk, row["similarity"], {"semantic": row["similarity"]}))
        for row in claim_rows:
            claim = claims_map.get(row["id"])
            if claim is None:
                continue
            hits.append(self._claim_hit(claim, row["similarity"], {"semantic": row["similarity"]}))
        return sorted(hits, key=lambda h: h.score, reverse=True)[:top_k]

    def search_graph(self, query: str, top_k: int = 8) -> list[SearchHit]:
        activation = self.activation_keys(query)
        active_claims = {c["id"] for c in activation["activated_claims"]}
        related = set(active_claims)
        for relation in self.relations.values():
            if relation.source_claim_id in active_claims or relation.target_claim_id in active_claims:
                related.add(relation.source_claim_id)
                related.add(relation.target_claim_id)
        hits = []
        for claim_id in related:
            claim = self.claims.get(claim_id)
            if not claim:
                continue
            relation_bonus = sum(
                r.weight
                for r in self.relations.values()
                if r.source_claim_id == claim_id or r.target_claim_id == claim_id
            )
            score = min(1.0, 0.45 + relation_bonus / 4.0)
            hits.append(self._claim_hit(claim, score, {"graph": score, "relation_bonus": min(1.0, relation_bonus)}))
        return sorted(hits, key=lambda h: h.score, reverse=True)[:top_k]

    def search_hybrid(self, query: str, top_k: int = 8) -> list[SearchHit]:
        weights = self._hybrid_weights()
        by_id: dict[str, SearchHit] = {}
        component_scores: dict[str, dict[str, float]] = {}

        def channel(hit: SearchHit, name: str, value: float) -> None:
            existing = by_id.get(hit.id)
            if not existing:
                existing = hit
                existing.score = 0.0
                existing.score_breakdown = {}
                by_id[hit.id] = existing
                component_scores[hit.id] = {}
            existing.score_breakdown[name] = round(
                max(existing.score_breakdown.get(name, 0.0), value), 4
            )
            component_scores[hit.id][name] = existing.score_breakdown[name]

        for hit in self.search_keyword(query, top_k=top_k * 3):
            channel(hit, "keyword", hit.score_breakdown.get("keyword", hit.score))
        for hit in self.search_semantic(query, top_k=top_k * 3):
            channel(hit, "semantic", hit.score_breakdown.get("semantic", hit.score))
        for hit in self.search_graph(query, top_k=top_k * 3):
            channel(hit, "graph", hit.score_breakdown.get("graph", hit.score))

        activation = self.activation_keys(query)
        activated_ids = {c["id"] for c in activation["activated_claims"]} | {
            c["id"] for c in activation["activated_chunks"]
        }
        for hit_id in activated_ids:
            existing = by_id.get(hit_id)
            if existing:
                existing.score_breakdown["activation"] = 1.0

        # Достаём claims одним батчем через Cypher (если cache miss) для расчёта весов.
        claim_ids = [hit.id for hit in by_id.values() if hit.kind == "claim"]
        claims_map = self._fetch_claims_by_ids(claim_ids) if claim_ids else {}

        for hit in by_id.values():
            claim = claims_map.get(hit.id) if hit.kind == "claim" else None
            confidence = float(claim.confidence_score) if claim else float(hit.metadata.get("confidence_score") or 0.55)
            evidence_strength = float(claim.evidence_strength) if claim else float(hit.metadata.get("evidence_strength") or 0.55)
            source_reliability = float(claim.source_reliability) if claim else 0.70
            contradiction_risk = self._contradiction_risk(claim) if claim else 0.0

            keyword = round(hit.score_breakdown.get("keyword", 0.0), 4)
            semantic = round(hit.score_breakdown.get("semantic", 0.0), 4)
            graph_value = round(hit.score_breakdown.get("graph", 0.0), 4)
            activation_bonus = round(hit.score_breakdown.get("activation", 0.0), 4)
            hit.score_breakdown.setdefault("keyword", keyword)
            hit.score_breakdown.setdefault("semantic", semantic)
            hit.score_breakdown.setdefault("graph", graph_value)
            hit.score_breakdown.setdefault("activation", activation_bonus)

            total = (
                weights["alpha"] * keyword
                + weights["beta"] * semantic
                + weights["gamma"] * (graph_value + 0.5 * activation_bonus)
                + weights["delta"] * confidence
                + weights["epsilon"] * evidence_strength
                + weights["zeta"] * source_reliability
                - weights["eta"] * contradiction_risk
            )
            total = max(0.0, min(1.0, total))
            hit.score_breakdown.update(
                {
                    "claim_confidence": round(confidence, 4),
                    "evidence_strength": round(evidence_strength, 4),
                    "source_reliability": round(source_reliability, 4),
                    "contradiction_risk": round(contradiction_risk, 4),
                    "weights": weights,
                }
            )
            hit.score = round(total, 4)
        return sorted(by_id.values(), key=lambda h: h.score, reverse=True)[:top_k]

    def _hybrid_weights(self) -> dict[str, float]:
        settings = _safe_get_settings()
        if settings is None:
            return {
                "alpha": 0.15,
                "beta": 0.35,
                "gamma": 0.20,
                "delta": 0.10,
                "epsilon": 0.15,
                "zeta": 0.05,
                "eta": 0.10,
            }
        return {
            "alpha": float(getattr(settings, "hybrid_alpha", 0.15)),
            "beta": float(getattr(settings, "hybrid_beta", 0.35)),
            "gamma": float(getattr(settings, "hybrid_gamma", 0.20)),
            "delta": float(getattr(settings, "hybrid_delta", 0.10)),
            "epsilon": float(getattr(settings, "hybrid_epsilon", 0.15)),
            "zeta": float(getattr(settings, "hybrid_zeta", 0.05)),
            "eta": float(getattr(settings, "hybrid_eta", 0.10)),
        }

    def _contradiction_risk(self, claim: ScientificClaim | None) -> float:
        if claim is None:
            return 0.0
        risk = 0.0
        if claim.claim_type == "contradiction_candidate":
            risk += 0.45
        contradicts = 0
        supports = 0
        for relation in self.relations.values():
            if relation.source_claim_id == claim.id or relation.target_claim_id == claim.id:
                if relation.relation_type == "contradicts":
                    contradicts += 1
                elif relation.relation_type == "supports":
                    supports += 1
        if contradicts:
            risk += min(0.55, 0.15 * contradicts)
        if contradicts and supports == 0:
            risk += 0.10
        return round(min(1.0, risk), 4)

    def _embed_query(self, text: str) -> list[float]:
        embedding_fn = getattr(self, "_query_embedding", None)
        if callable(embedding_fn):
            try:
                return embedding_fn(text)
            except Exception:
                pass
        return deterministic_embedding(text)

    def build_evidence(self, question: str, top_k: int = 6) -> dict[str, Any]:
        hits = self.search_hybrid(question, top_k)
        claim_ids = [h.id for h in hits if h.kind == "claim"]
        chunk_ids = [h.id for h in hits if h.kind == "chunk"]
        claims_map = self._fetch_claims_by_ids(claim_ids) if claim_ids else {}
        chunks_map = self._fetch_chunks_by_ids(chunk_ids) if chunk_ids else {}
        pub_ids: set[str] = set()
        for claim in claims_map.values():
            if claim.publication_id:
                pub_ids.add(claim.publication_id)
        for chunk in chunks_map.values():
            if chunk.publication_id:
                pub_ids.add(chunk.publication_id)
        publications_map: dict[str, Publication] = {}
        missing_pubs: list[str] = []
        for pid in pub_ids:
            pub = self.publications.get(pid)
            if pub is not None:
                publications_map[pid] = pub
            else:
                missing_pubs.append(pid)
        if missing_pubs:
            adapter = self._neo4j_adapter()
            if adapter is not None and hasattr(adapter, "fetch_publications_by_ids"):
                payloads = adapter.fetch_publications_by_ids(missing_pubs)
                for pid, payload in (payloads or {}).items():
                    publications_map[pid] = _publication_from_payload(payload)

        evidence_items = []
        for hit in hits:
            if hit.kind == "claim":
                claim = claims_map.get(hit.id)
                if claim is None:
                    continue
                publication = publications_map.get(claim.publication_id)
                pub_id = publication.id if publication else claim.publication_id
                pub_title = publication.title if publication else ""
                evidence_items.append(
                    {
                        "claim_id": claim.id,
                        "publication_id": pub_id,
                        "publication_title": pub_title,
                        "chunk_id": claim.chunk_id,
                        "pages": [claim.page_start, claim.page_end],
                        "evidence_text": claim.evidence_text,
                        "claim_text": claim.claim_text,
                        "claim_type": claim.claim_type,
                        "score": hit.score,
                        "score_breakdown": hit.score_breakdown,
                        "evidence_strength": claim.evidence_strength,
                        "confidence_score": claim.confidence_score,
                        "source_reliability": claim.source_reliability,
                        "contradiction_risk": hit.score_breakdown.get("contradiction_risk", 0.0),
                    }
                )
            elif hit.kind == "chunk":
                chunk = chunks_map.get(hit.id)
                if chunk is None:
                    continue
                publication = publications_map.get(chunk.publication_id)
                pub_id = publication.id if publication else chunk.publication_id
                pub_title = publication.title if publication else ""
                evidence_items.append(
                    {
                        "claim_id": None,
                        "publication_id": pub_id,
                        "publication_title": pub_title,
                        "chunk_id": chunk.id,
                        "pages": [chunk.page_start, chunk.page_end],
                        "evidence_text": chunk.text,
                        "claim_text": None,
                        "claim_type": None,
                        "score": hit.score,
                        "score_breakdown": hit.score_breakdown,
                        "evidence_strength": hit.metadata.get("evidence_strength", 0.5),
                        "confidence_score": hit.score,
                        "source_reliability": 0.70,
                        "contradiction_risk": hit.score_breakdown.get("contradiction_risk", 0.0),
                    }
                )
        return {
            "question": question,
            "activation": self.activation_keys(question),
            "evidence": evidence_items,
            "coverage": self._coverage(question, evidence_items),
        }

    def _coverage(self, question: str, evidence: list[dict[str, Any]]) -> float:
        q_tokens = {t for t in _tokenize(question) if len(t) > 2}
        if not q_tokens:
            return 0.0
        evidence_tokens = set()
        for item in evidence:
            evidence_tokens.update(_tokenize(item.get("evidence_text") or ""))
            evidence_tokens.update(_tokenize(item.get("claim_text") or ""))
        return round(len(q_tokens & evidence_tokens) / len(q_tokens), 3)

    def _entities_for_claims(self, claim_ids: list[str]) -> list[ScientificEntity]:
        claims_map = self._fetch_claims_by_ids(claim_ids) if claim_ids else {}
        names = set()
        for claim in claims_map.values():
            names.update([claim.subject_entity, claim.object_entity])
        return [self.entities[self._entity_by_canonical[name]] for name in sorted(names) if name in self._entity_by_canonical]

    def _chunk_hit(self, chunk: DocumentChunk, score: float, breakdown: dict[str, float]) -> SearchHit:
        publication = self._fetch_publication(chunk.publication_id)
        pub_title = publication.title if publication else chunk.publication_id
        pub_id = publication.id if publication else chunk.publication_id
        return SearchHit(
            id=chunk.id,
            kind="chunk",
            score=round(score, 4),
            title=f"{pub_title} / {chunk.section}",
            text=chunk.text,
            metadata={
                "publication_id": pub_id,
                "publication_title": pub_title,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "section": chunk.section,
                "evidence_strength": 0.52,
            },
            score_breakdown={k: round(v, 4) for k, v in breakdown.items()},
        )

    def _claim_hit(self, claim: ScientificClaim, score: float, breakdown: dict[str, float]) -> SearchHit:
        publication = self._fetch_publication(claim.publication_id)
        pub_title = publication.title if publication else claim.publication_id
        pub_id = publication.id if publication else claim.publication_id
        return SearchHit(
            id=claim.id,
            kind="claim",
            score=round(score, 4),
            title=f"{claim.claim_type}: {claim.subject_entity}",
            text=claim.claim_text,
            metadata={
                "publication_id": pub_id,
                "publication_title": pub_title,
                "chunk_id": claim.chunk_id,
                "page_start": claim.page_start,
                "page_end": claim.page_end,
                "claim_type": claim.claim_type,
                "predicate": claim.predicate,
                "evidence_strength": claim.evidence_strength,
                "confidence_score": claim.confidence_score,
                "source_reliability": claim.source_reliability,
            },
            score_breakdown={k: round(v, 4) for k, v in breakdown.items()},
        )
