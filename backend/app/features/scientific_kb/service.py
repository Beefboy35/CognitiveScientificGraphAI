from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from .demo import DEMO_CORPUS
from .extraction import ScientificExtractionMixin
from .graph import ScientificGraphMixin
from .models import (
    ClaimRelation,
    DocumentChunk,
    EvaluationRecord,
    FeedbackEvent,
    ProcessingJob,
    Publication,
    RagAnswer,
    ScientificClaim,
    ScientificEntity,
)
from .pipeline import ScientificPipelineMixin
from .rag import ScientificRagMixin
from .search import ScientificSearchMixin
from .seed import attach_demo_metadata
from .utils import _sentences, _stable_id


class ScientificKnowledgeBase(
    ScientificPipelineMixin,
    ScientificExtractionMixin,
    ScientificSearchMixin,
    ScientificRagMixin,
    ScientificGraphMixin,
):
    def __init__(self) -> None:
        # Preserve hooks that may have been set BEFORE __init__ runs (singleton
        # configures embedder + persistence + LLM extractor on a freshly-allocated instance).
        existing_persistence = getattr(self, "persistence", None)
        existing_embedder = getattr(self, "_embedder", None)
        existing_embed_text = getattr(self, "_embed_text", None)
        existing_query_embedding = getattr(self, "_query_embedding", None)
        existing_provider = getattr(self, "_embedding_provider", None)
        existing_llm = getattr(self, "_llm_extractor", None)
        existing_mode = getattr(self, "_extraction_mode", "hybrid")
        existing_llm_on_demo = getattr(self, "_extraction_llm_on_demo", False)

        self.publications: dict[str, Publication] = {}
        self.chunks: dict[str, DocumentChunk] = {}
        self.entities: dict[str, ScientificEntity] = {}
        self.claims: dict[str, ScientificClaim] = {}
        self.relations: dict[str, ClaimRelation] = {}
        self.jobs: dict[str, ProcessingJob] = {}
        self.rag_answers: dict[str, RagAnswer] = {}
        self.evaluations: dict[str, EvaluationRecord] = {}
        self.feedback_events: dict[str, FeedbackEvent] = {}
        self.review_queue: dict[str, dict[str, Any]] = {}
        self.user_queries: dict[str, dict[str, Any]] = {}
        self.retrieval_experiments: dict[str, dict[str, Any]] = {}
        self.activation_index: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: {"entities": set(), "claims": set(), "chunks": set()}
        )
        self._entity_by_canonical: dict[str, str] = {}
        self.demo_authors: dict[str, Any] = {}
        self.demo_organizations: dict[str, Any] = {}
        self.demo_citations: list[dict[str, str]] = []
        self.persistence = existing_persistence
        if existing_embedder is not None:
            self._embedder = existing_embedder
        if existing_embed_text is not None:
            self._embed_text = existing_embed_text
        if existing_query_embedding is not None:
            self._query_embedding = existing_query_embedding
        if existing_provider is not None:
            self._embedding_provider = existing_provider
        self._llm_extractor = existing_llm
        self._extraction_mode = existing_mode
        self._extraction_llm_on_demo = existing_llm_on_demo
        # Cache of {chunk_id -> LLMExtractionResult} populated in pipeline.py
        self._llm_chunk_cache: dict[str, Any] = {}
        # Per-pipeline override: when False, the run won't call OpenRouter.
        self._use_llm_for_current_run: bool = True
        self._load_demo_corpus()

    def reset_demo(self) -> dict[str, Any]:
        persistence = getattr(self, "persistence", None)
        self.__init__()
        self.persistence = persistence
        if persistence is not None:
            try:
                persistence.reset_demo_storage(self)
            except Exception:
                pass
        return self.summary()

    def summary(self) -> dict[str, Any]:
        llm = getattr(self, "_llm_extractor", None)
        llm_active = bool(llm and llm.is_active())
        return {
            "project": "Evidence-based Scientific Reasoning Engine",
            "status": "ready",
            "publications": len(self.publications),
            "authors": len(self.demo_authors),
            "organizations": len(self.demo_organizations),
            "citations": len(self.demo_citations),
            "chunks": len(self.chunks),
            "entities": len(self.entities),
            "claims": len(self.claims),
            "relations": len(self.relations),
            "feedback_events": len(self.feedback_events),
            "human_review_queue": len(self.review_queue),
            "activation_keys": len(self.activation_index),
            "graph_mode": "real" if self._adapter_active("neo4j") else "in-memory fallback",
            "graph_query_engine": "neo4j" if self._adapter_active("neo4j") else "in-memory",
            "postgres_mode": "real" if self._adapter_active("postgres") else "in-memory fallback",
            "vector_search_mode": "pgvector" if self._adapter_active("pgvector") else "in-process",
            "extraction_mode": getattr(self, "_extraction_mode", "hybrid"),
            "llm_provider": llm.provider() if llm_active else "disabled",
            "llm_active": llm_active,
        }

    def _adapter_active(self, name: str) -> bool:
        persistence = getattr(self, "persistence", None)
        if persistence is None:
            return False
        adapter = getattr(persistence, name, None)
        return bool(adapter and getattr(adapter, "is_active", lambda: False)())

    # ------------------------------------------------------------------
    # Neo4j-first read helpers — используются API endpoints'ом.
    # Если Neo4j активен — читаем оттуда; иначе fallback на in-memory.
    # ------------------------------------------------------------------

    def _neo4j_or_none(self) -> Any:
        persistence = getattr(self, "persistence", None)
        if persistence is None:
            return None
        adapter = getattr(persistence, "neo4j", None)
        if adapter is None or not getattr(adapter, "is_active", lambda: False)():
            return None
        return adapter

    def list_publications_read(self, **filters: Any) -> list[dict[str, Any]]:
        adapter = self._neo4j_or_none()
        if adapter is not None:
            data = adapter.list_publications(**filters)
            if data is not None:
                return data
        # Fallback на in-memory
        from .serialization import dump

        items = list(self.publications.values())
        if filters.get("research_field"):
            items = [p for p in items if (p.metadata or {}).get("research_field") == filters["research_field"]]
        if filters.get("status"):
            items = [p for p in items if p.status == filters["status"]]
        if filters.get("year"):
            items = [p for p in items if p.year == filters["year"]]
        if filters.get("search"):
            needle = filters["search"].lower()
            items = [p for p in items if needle in p.title.lower() or needle in (p.abstract or "").lower()]
        return [dump(p) for p in items]

    def get_publication_detail_read(self, publication_id: str) -> dict[str, Any] | None:
        adapter = self._neo4j_or_none()
        if adapter is not None:
            data = adapter.get_publication_detail(publication_id)
            if data is not None:
                return data
        # Fallback
        from .serialization import dump

        publication = self.publications.get(publication_id)
        if publication is None:
            return None
        chunks = sorted(
            (c for c in self.chunks.values() if c.publication_id == publication_id),
            key=lambda c: c.chunk_index,
        )
        claims = [c for c in self.claims.values() if c.publication_id == publication_id]
        entity_ids: set[str] = set()
        for entity in self.entities.values():
            if any(m.get("publication_id") == publication_id for m in entity.mentions):
                entity_ids.add(entity.id)
        entities = [self.entities[i] for i in entity_ids if i in self.entities]
        jobs = [j for j in self.jobs.values() if j.publication_id == publication_id]
        citations = [c for c in self.demo_citations if c["source_publication_id"] == publication_id]
        return {
            "publication": dump(publication),
            "chunks": dump(chunks),
            "claims": dump(claims),
            "entities": dump(entities),
            "jobs": dump(jobs),
            "citations": citations,
        }

    def list_chunks_read(self, publication_id: str) -> list[dict[str, Any]] | None:
        adapter = self._neo4j_or_none()
        if adapter is not None:
            data = adapter.list_chunks_by_publication(publication_id)
            if data is not None:
                return data
        from .serialization import dump

        if publication_id not in self.publications:
            return None
        chunks = [c for c in self.chunks.values() if c.publication_id == publication_id]
        return dump(sorted(chunks, key=lambda c: c.chunk_index))

    def list_entities_read(self, **filters: Any) -> list[dict[str, Any]]:
        adapter = self._neo4j_or_none()
        if adapter is not None:
            data = adapter.list_entities(**filters)
            if data is not None:
                return data
        from .serialization import dump

        items = list(self.entities.values())
        if filters.get("entity_type"):
            items = [e for e in items if e.entity_type == filters["entity_type"]]
        if filters.get("search"):
            needle = filters["search"].lower()
            items = [
                e
                for e in items
                if needle in e.canonical_name.lower() or any(needle in a.lower() for a in e.aliases)
            ]
        items.sort(key=lambda e: (e.entity_type, e.canonical_name.lower()))
        return [dump(e) for e in items[: filters.get("limit", 200)]]

    def get_entity_detail_read(self, entity_id: str) -> dict[str, Any] | None:
        adapter = self._neo4j_or_none()
        if adapter is not None:
            data = adapter.get_entity_detail(entity_id)
            if data is not None:
                return data
        from .serialization import dump

        entity = self.entities.get(entity_id)
        if entity is None:
            return None
        claims = [
            c
            for c in self.claims.values()
            if c.subject_entity == entity.canonical_name or c.object_entity == entity.canonical_name
        ]
        publications: dict[str, Any] = {}
        for claim in claims:
            publications.setdefault(claim.publication_id, self.publications[claim.publication_id])
        return {
            "entity": dump(entity),
            "claims": dump(claims),
            "publications": dump(list(publications.values())),
        }

    def list_claims_read(self, **filters: Any) -> list[dict[str, Any]]:
        adapter = self._neo4j_or_none()
        if adapter is not None:
            data = adapter.list_claims(**filters)
            if data is not None:
                return data
        from .serialization import dump

        claims = list(self.claims.values())
        if filters.get("publication_id"):
            claims = [c for c in claims if c.publication_id == filters["publication_id"]]
        if filters.get("claim_type"):
            claims = [c for c in claims if c.claim_type == filters["claim_type"]]
        if filters.get("min_confidence"):
            claims = [c for c in claims if c.confidence_score >= filters["min_confidence"]]
        if filters.get("min_evidence_strength"):
            claims = [c for c in claims if c.evidence_strength >= filters["min_evidence_strength"]]
        claims.sort(key=lambda c: c.evidence_strength, reverse=True)
        return [dump(c) for c in claims[: filters.get("limit", 200)]]

    def get_claim_detail_read(self, claim_id: str) -> dict[str, Any] | None:
        adapter = self._neo4j_or_none()
        if adapter is not None:
            data = adapter.get_claim_detail(claim_id)
            if data is not None:
                return data
        from .serialization import dump

        claim = self.claims.get(claim_id)
        if claim is None:
            return None
        relations = [
            r
            for r in self.relations.values()
            if r.source_claim_id == claim_id or r.target_claim_id == claim_id
        ]
        related = {claim.id: claim}
        for relation in relations:
            for cid in (relation.source_claim_id, relation.target_claim_id):
                if cid in self.claims:
                    related[cid] = self.claims[cid]
        return {
            "claim": dump(claim),
            "relations": dump(relations),
            "related_claims": dump(list(related.values())),
        }

    def get_claim_evidence_read(self, claim_id: str) -> dict[str, Any] | None:
        adapter = self._neo4j_or_none()
        if adapter is not None:
            data = adapter.get_claim_evidence(claim_id)
            if data is not None:
                return data
        from .serialization import dump

        claim = self.claims.get(claim_id)
        if claim is None:
            return None
        chunk = self.chunks.get(claim.chunk_id)
        publication = self.publications.get(claim.publication_id)
        return {
            "claim": dump(claim),
            "chunk": dump(chunk) if chunk else None,
            "publication": dump(publication) if publication else None,
            "evidence_text": claim.evidence_text,
            "pages": [claim.page_start, claim.page_end],
            "evidence_strength": claim.evidence_strength,
            "source_reliability": claim.source_reliability,
        }

    def claim_user_facing_view(self, claim_id: str) -> dict[str, Any] | None:
        """Полная цепочка использования claim в продуктовых сценариях.

        Возвращает «прикладное» описание:
        - can_be_used_in: список сценариев (rag_answer / recommendation /
          roadmap / contradiction_warning), для которых claim пригоден;
        - retrieval_priority: 0..1, скорость попадания в выдачу RAG;
        - explanation_for_user: человеко-читаемое объяснение, **почему**
          этот claim ценен и где он применим;
        - pipeline_trace: восстановленная цепочка извлечения от публикации
          до конкретного claim'а (для аудита и прозрачности).
        """
        claim = self.claims.get(claim_id)
        if claim is None:
            return None

        publication = self.publications.get(claim.publication_id)
        chunk = self.chunks.get(claim.chunk_id)

        # ── Сценарии использования ────────────────────────────────────────
        # Правила выводятся из claim_type, метрик качества и наличия связей.
        can_be_used_in: list[str] = []
        reasons: list[str] = []

        # 1) RAG ответы — если claim достаточно подтверждён.
        if claim.confidence_score >= 0.6 and claim.evidence_strength >= 0.5:
            can_be_used_in.append("rag_answer")
            reasons.append(
                f"подходит для прямого ответа RAG (confidence={claim.confidence_score:.2f}, "
                f"evidence_strength={claim.evidence_strength:.2f})"
            )

        # 2) Рекомендации/учебный маршрут — для определений и методов.
        if claim.claim_type in {"definition", "method_description", "conclusion"}:
            can_be_used_in.append("recommendation")
            reasons.append(
                f"тип claim'а '{claim.claim_type}' пригоден для рекомендаций ученику"
            )

        # 3) Roadmap — если у claim есть SUPPORTS/EXTENDS-цепочки.
        related_relations = [
            r for r in self.relations.values()
            if r.source_claim_id == claim_id or r.target_claim_id == claim_id
        ]
        has_supports = any(r.relation_type == "supports" for r in related_relations)
        has_extends = any(r.relation_type == "extends" for r in related_relations)
        if has_supports or has_extends:
            can_be_used_in.append("roadmap")
            reasons.append(
                f"claim входит в учебную цепочку (SUPPORTS/EXTENDS-связей: "
                f"{sum(1 for r in related_relations if r.relation_type in {'supports', 'extends'})})"
            )

        # 4) Contradiction warning — если у claim есть входящие/исходящие CONTRADICTS.
        contradicting = [r for r in related_relations if r.relation_type == "contradicts"]
        if contradicting:
            can_be_used_in.append("contradiction_warning")
            reasons.append(
                f"найдено {len(contradicting)} противоречащих утверждений — "
                f"RAG должен показывать предупреждение"
            )

        # ── Приоритет в выдаче ────────────────────────────────────────────
        # Композитная метрика: качество claim'а × сила доказательств × надёжность источника.
        retrieval_priority = round(
            float(claim.confidence_score) * 0.4
            + float(claim.evidence_strength) * 0.4
            + float(claim.source_reliability) * 0.2,
            3,
        )

        explanation = (
            "Этот claim "
            + ("полезен для: " + ", ".join(can_be_used_in) if can_be_used_in else "не имеет явных продуктовых сценариев")
            + ". Причины: "
            + "; ".join(reasons) if reasons else ""
        )

        # ── Pipeline trace: восстанавливаемая цепочка извлечения ──────────
        from .serialization import dump

        pipeline_trace: list[dict[str, Any]] = []
        if publication:
            pipeline_trace.append({
                "step": "publication",
                "ref": publication.id,
                "label": publication.title,
                "meta": {
                    "year": publication.year,
                    "authors": publication.authors,
                    "research_field": (publication.metadata or {}).get("research_field"),
                },
            })
        if chunk:
            pipeline_trace.append({
                "step": "chunk",
                "ref": chunk.id,
                "label": f"{chunk.section} (стр. {chunk.page_start}–{chunk.page_end})",
                "excerpt": chunk.text[:240] + ("…" if len(chunk.text) > 240 else ""),
            })
        pipeline_trace.append({
            "step": "extraction",
            "ref": claim.extraction_run_id,
            "label": "Извлечение утверждения",
            "method": claim.extraction_run_id.split("_")[0] if claim.extraction_run_id else "rule",
        })
        pipeline_trace.append({
            "step": "claim",
            "ref": claim.id,
            "label": claim.claim_text,
            "claim_type": claim.claim_type,
        })
        pipeline_trace.append({
            "step": "evidence_strength",
            "value": claim.evidence_strength,
            "confidence_score": claim.confidence_score,
            "source_reliability": claim.source_reliability,
        })
        if related_relations:
            relation_summary: dict[str, int] = {}
            for r in related_relations:
                relation_summary[r.relation_type] = relation_summary.get(r.relation_type, 0) + 1
            pipeline_trace.append({
                "step": "relations",
                "summary": relation_summary,
                "total": len(related_relations),
            })

        return {
            "claim_id": claim.id,
            "publication_id": claim.publication_id,
            "can_be_used_in": can_be_used_in,
            "retrieval_priority": retrieval_priority,
            "explanation_for_user": explanation,
            "pipeline_trace": pipeline_trace,
            "claim": dump(claim),
            "publication": dump(publication) if publication else None,
        }

    def list_relations_read(self, **filters: Any) -> list[dict[str, Any]]:
        adapter = self._neo4j_or_none()
        if adapter is not None:
            data = adapter.list_relations(**filters)
            if data is not None:
                return data
        from .serialization import dump

        relations = list(self.relations.values())
        if filters.get("relation_type"):
            relations = [r for r in relations if r.relation_type == filters["relation_type"]]
        relations.sort(key=lambda r: r.weight, reverse=True)
        return [dump(r) for r in relations[: filters.get("limit", 500)]]

    def graph_query_engine_name(self) -> str:
        return "neo4j" if self._neo4j_or_none() is not None else "in-memory"

    def create_publication(
        self,
        title: str,
        text: str,
        *,
        authors: list[str] | None = None,
        year: int = 2026,
        source_type: str = "text",
        metadata: dict[str, Any] | None = None,
    ) -> Publication:
        clean_title = title.strip() or "Untitled scientific publication"
        # Stable id из (title, year, источника), чтобы повторный bootstrap не
        # создавал дублей в Neo4j.
        publication = Publication(
            id=_stable_id("pub", clean_title, year, source_type),
            title=clean_title,
            abstract=_sentences(text)[0][:500] if _sentences(text) else text[:500],
            source_type=source_type,
            authors=authors or ["Demo Research Group"],
            year=year,
            pages=max(1, math.ceil(len(text) / 2800)),
            metadata=metadata or {},
        )
        self.publications[publication.id] = publication
        return publication

    def _load_demo_corpus(self) -> None:
        for title, text in DEMO_CORPUS:
            publication = self.create_publication(
                title=title,
                text=text,
                source_type="demo",
                authors=["Demo Team"],
                year=2026,
                metadata={"raw_text": text, "demo": True},
            )
            # Demo bootstrap stays deterministic (rule-based) for reproducible
            # tests. LLM extraction kicks in for user-uploaded publications via
            # the API, unless EXTRACTION_LLM_ON_DEMO=true is explicitly set.
            self.run_pipeline(publication.id, text, use_llm=bool(self._extraction_llm_on_demo))
        attach_demo_metadata(self)
        # ВАЖНО: больше не вызываем _guarantee_relation_diversity и не
        # добавляем синтетические связи. Если в корпусе нет естественной
        # CONTRADICTS — пусть её нет. Тип связи должен иметь evidence.
        self._prune_relations_per_claim(max_per_claim=20)
        # Убираем orphan-entities — те, что не упомянуты ни в одном чанке/claim.
        # Они только засоряют выдачу /v1/knowledge/entities и Neo4j-граф.
        self._prune_orphan_entities()

    def _prune_orphan_entities(self) -> None:
        """Удаляет ScientificEntity без mentions.

        Такие entities появлялись из-за того, что parser распознаёт термин
        в онтологии, но subject_entity claim'а в итоге берётся из другой
        части предложения, и сущность остаётся без обратных ссылок. Это
        не баг (термин действительно упомянут), но в графе такая сущность
        видна как изолированная точка → визуальный мусор.
        """
        orphan_ids = [
            eid for eid, entity in self.entities.items()
            if not getattr(entity, "mentions", None)
        ]
        for eid in orphan_ids:
            canonical = self.entities[eid].canonical_name
            self.entities.pop(eid, None)
            self._entity_by_canonical.pop(canonical, None)
        if orphan_ids:
            from logging import getLogger
            getLogger(__name__).info(
                "in_memory_pruned_orphan_entities",
                extra={"count": len(orphan_ids)},
            )

    def _prune_relations_per_claim(self, *, max_per_claim: int = 20) -> None:
        """Ограничивает число связей на узел сверху.

        Для каждого claim считаем degree (входящие + исходящие). Если он
        больше cap'а — оставляем только top-N связей по приоритету
        `weight * confidence_score * evidence_strength`. Остальные удаляем.

        Это страховка от случаев, когда несколько источников (LLM,
        rule-based, near-duplicate) дают много кандидатов на один узел.
        После strict-extraction обычно срабатывает редко.
        """
        # Группируем связи по claim_id (по обоим концам).
        per_claim: dict[str, list[tuple[str, float]]] = {}
        for rel_id, rel in self.relations.items():
            score = float(rel.weight) * float(rel.confidence_score) * float(rel.evidence_strength)
            per_claim.setdefault(rel.source_claim_id, []).append((rel_id, score))
            per_claim.setdefault(rel.target_claim_id, []).append((rel_id, score))

        to_remove: set[str] = set()
        for _claim_id, items in per_claim.items():
            if len(items) <= max_per_claim:
                continue
            # Сортируем по score убыванию; всё что после max_per_claim — на удаление.
            items.sort(key=lambda pair: pair[1], reverse=True)
            for rel_id, _score in items[max_per_claim:]:
                to_remove.add(rel_id)
        for rel_id in to_remove:
            self.relations.pop(rel_id, None)
        if to_remove:
            from logging import getLogger

            getLogger(__name__).info(
                "relations_pruned", extra={"removed": len(to_remove), "cap": max_per_claim}
            )
