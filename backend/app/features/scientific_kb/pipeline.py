from __future__ import annotations

import hashlib
import logging
import re
import time
from collections import defaultdict
from typing import Any, Callable

from .models import DocumentChunk, PipelineStep, ProcessingJob, Publication
from .ontology import PIPELINE_STEPS
from .utils import _id, _sentences, _stable_id, deterministic_embedding, utc_now


logger = logging.getLogger(__name__)


class ScientificPipelineMixin:
    def run_pipeline(
        self,
        publication_id: str,
        text: str | None = None,
        *,
        max_retries: int = 1,
        use_llm: bool | None = None,
    ) -> ProcessingJob:
        if publication_id not in self.publications:
            raise KeyError("publication not found")
        publication = self.publications[publication_id]
        self._clear_publication_knowledge(publication_id)
        extraction_run_id = _id("run")
        # decide LLM policy for this run
        if use_llm is None:
            mode = getattr(self, "_extraction_mode", "hybrid") or "hybrid"
            use_llm = mode in ("hybrid", "llm")
        self._use_llm_for_current_run = bool(use_llm)
        self._llm_chunk_cache = {}
        job = ProcessingJob(
            id=_id("job"),
            publication_id=publication_id,
            status="running",
            extraction_run_id=extraction_run_id,
            steps=[PipelineStep(name=s, status="pending") for s in PIPELINE_STEPS],
        )
        self.jobs[job.id] = job
        publication.status = "uploaded"

        source_text = text or publication.metadata.get("raw_text") or publication.abstract
        content_hash = hashlib.sha256(source_text.encode("utf-8", errors="ignore")).hexdigest()[:24]
        publication.metadata["content_hash"] = content_hash
        publication.metadata["extraction_run_id"] = extraction_run_id

        sections_ref: dict[str, dict[str, str]] = {}
        chunks_ref: dict[str, list[DocumentChunk]] = {}
        entities_count = {"value": 0}
        claims_count = {"value": 0}
        relations_count = {"value": 0}

        def step_upload() -> dict[str, Any]:
            return {"publication_id": publication_id, "content_hash": content_hash}

        def step_text_extraction() -> dict[str, Any]:
            return {"characters": len(source_text), "pages": publication.pages}

        def step_section_detection() -> dict[str, Any]:
            sections_ref["sections"] = self._detect_sections(source_text)
            return {"sections": list(sections_ref["sections"].keys())}

        def step_semantic_chunking() -> dict[str, Any]:
            chunks_ref["chunks"] = self._chunk_publication(publication, sections_ref["sections"])
            return {"chunks": len(chunks_ref["chunks"])}

        def step_embeddings() -> dict[str, Any]:
            for chunk in chunks_ref["chunks"]:
                chunk.embedding = self._chunk_embedding(chunk.text)
                chunk.metadata["embedding_provider"] = self._embedding_provider_name()
            self._persist("upsert_chunks", chunks_ref["chunks"], publication=publication)
            return {"vectors": len(chunks_ref["chunks"]), "dimension": len(chunks_ref["chunks"][0].embedding) if chunks_ref["chunks"] else 0}

        def step_entity_extraction() -> dict[str, Any]:
            llm_summary = self._llm_enrich_chunks(chunks_ref["chunks"])
            entities = self._extract_entities(chunks_ref["chunks"])
            entities_count["value"] = len(entities)
            return {
                "entities": len(entities),
                "canonical_total": len(self.entities),
                "llm": llm_summary,
            }

        def step_entity_normalization() -> dict[str, Any]:
            self._normalize_entities()
            self._persist("upsert_entities", list(self.entities.values()))
            return {"canonical_entities": len(self.entities)}

        def step_claim_extraction() -> dict[str, Any]:
            claims = self._extract_claims(chunks_ref["chunks"], extraction_run_id)
            claims_count["value"] = len(claims)
            self._persist("upsert_claims", claims, publication=publication)
            # Embed каждый новый claim и положи вектор в pgvector. Заодно посчитай,
            # сколько near-duplicate'ов нашлось в уже существующих claims.
            duplicates = self._embed_and_dedup_claims(claims, publication_id=publication.id)
            return {
                "claims": len(claims),
                "claim_total": len(self.claims),
                "duplicates_linked": duplicates,
            }

        def step_claim_relations() -> dict[str, Any]:
            relations = self._build_claim_relations(list(self.claims.values()))
            relations_count["value"] = len(relations)
            self._persist("upsert_relations", relations)
            return {"relations": len(relations), "relation_total": len(self.relations)}

        def step_weighted_graph() -> dict[str, Any]:
            self._persist("sync_graph", publication)
            return {
                "nodes": len(self.entities) + len(self.claims) + len(self.publications),
                "edges": len(self.relations),
            }

        def step_activation_index() -> dict[str, Any]:
            self._rebuild_activation_index()
            self._persist("cache_activation", publication.id, list(self.activation_index.keys())[:256])
            return {"keys": len(self.activation_index)}

        def step_ready() -> dict[str, Any]:
            publication.status = "ready"
            return {"status": "ready"}

        steps: list[tuple[str, Callable[[], dict[str, Any]]]] = [
            ("upload", step_upload),
            ("text_extraction", step_text_extraction),
            ("section_detection", step_section_detection),
            ("semantic_chunking", step_semantic_chunking),
            ("embeddings", step_embeddings),
            ("entity_extraction", step_entity_extraction),
            ("entity_normalization", step_entity_normalization),
            ("claim_extraction_v2", step_claim_extraction),
            ("claim_relations", step_claim_relations),
            ("weighted_graph", step_weighted_graph),
            ("activation_index", step_activation_index),
            ("ready", step_ready),
        ]

        try:
            for name, fn in steps:
                self._run_step(job, name, fn, max_retries=max_retries)
                publication.status = self._status_for_step(name)
            job.status = "completed"
            publication.status = "ready"
            self._persist("upsert_job", job, publication=publication)
        except Exception as exc:
            publication.status = "error"
            job.status = "error"
            job.error = str(exc)
            self._persist("upsert_job", job, publication=publication)
            logger.exception("pipeline_failed", extra={"publication_id": publication_id, "job_id": job.id})
        finally:
            job.updated_at = utc_now()
        return job

    def retry_step(
        self,
        publication_id: str,
        step_name: str,
        text: str | None = None,
    ) -> ProcessingJob:
        if step_name not in PIPELINE_STEPS:
            raise ValueError(f"unknown pipeline step: {step_name}")
        return self.run_pipeline(publication_id, text)

    def _run_step(
        self,
        job: ProcessingJob,
        name: str,
        fn: Callable[[], dict[str, Any]],
        *,
        max_retries: int = 1,
    ) -> None:
        step = next(s for s in job.steps if s.name == name)
        step.status = "running"
        step.started_at = utc_now()
        job.updated_at = utc_now()
        attempts = 0
        last_error: Exception | None = None
        backoff = [0.0, 0.5, 1.5]
        while attempts <= max_retries:
            try:
                details = fn() or {}
                step.status = "completed"
                step.finished_at = utc_now()
                step.details = {"attempts": attempts + 1, **details}
                job.updated_at = utc_now()
                self._persist("upsert_step", job, step)
                return
            except Exception as exc:
                last_error = exc
                attempts += 1
                if attempts > max_retries:
                    break
                wait = backoff[min(attempts, len(backoff) - 1)]
                logger.warning("step_retry", extra={"step": name, "attempt": attempts, "error": str(exc)})
                time.sleep(wait)
        step.status = "error"
        step.finished_at = utc_now()
        step.details = {"attempts": attempts, "error": str(last_error) if last_error else "unknown"}
        job.updated_at = utc_now()
        self._persist("upsert_step", job, step)
        if last_error is not None:
            raise last_error

    def _status_for_step(self, step_name: str) -> str:
        mapping = {
            "upload": "uploaded",
            "text_extraction": "text_extracted",
            "section_detection": "text_extracted",
            "semantic_chunking": "chunked",
            "embeddings": "embedded",
            "entity_extraction": "entities_extracted",
            "entity_normalization": "entities_normalized",
            "claim_extraction_v2": "claims_extracted",
            "claim_relations": "claim_relations_built",
            "weighted_graph": "graph_built",
            "activation_index": "activation_indexed",
            "ready": "ready",
        }
        return mapping.get(step_name, "uploaded")

    def _persist(self, operation: str, *args: Any, **kwargs: Any) -> None:
        persistence = getattr(self, "persistence", None)
        if persistence is None:
            return
        fn = getattr(persistence, operation, None)
        if fn is None:
            return
        try:
            fn(*args, **kwargs)
        except Exception as exc:  # graceful degradation, never block pipeline
            logger.debug("persistence_skip", extra={"operation": operation, "error": str(exc)})

    def _chunk_embedding(self, text: str) -> list[float]:
        embedding_fn = getattr(self, "_embed_text", None)
        if callable(embedding_fn):
            try:
                return embedding_fn(text)
            except Exception:
                pass
        return deterministic_embedding(text)

    def _embed_and_dedup_claims(self, claims: list[Any], *, publication_id: str) -> int:
        """Подсчитывает embedding каждого claim, мирорит в pgvector и для каждого
        ищет уже существующий очень похожий claim в других публикациях.
        Если находит — добавляет SUPPORTS-связь, увеличивая граф знаний.
        Возвращает число найденных дубликатов.
        """
        if not claims:
            return 0
        persistence = getattr(self, "persistence", None)
        pgvector = getattr(persistence, "pgvector", None) if persistence else None
        embedder = getattr(self, "_embed_text", None) or deterministic_embedding
        try:
            pairs: list[tuple[str, list[float]]] = []
            duplicates_found = 0
            for claim in claims:
                vec = embedder(claim.claim_text)
                pairs.append((claim.id, vec))
                if pgvector is None or not getattr(pgvector, "is_active", lambda: False)():
                    continue
                # Строгая дедупликация: ищем ПОЧТИ ИДЕНТИЧНЫЙ claim в других
                # публикациях. Порог поднят с 0.93 → 0.96, чтобы исключить
                # ложноположительные совпадения по шаблонным фразам
                # ("Мы предлагаем...", "По результатам..." и т.п.).
                near = pgvector.find_near_duplicate_claim(
                    vec,
                    threshold=0.96,
                    exclude_publication_id=publication_id,
                )
                if not near:
                    continue
                existing_id = near.get("id")
                if existing_id is None or existing_id not in self.claims:
                    continue
                # Дополнительное условие: оба claims должны быть одного
                # claim_type. Иначе это не "дубль", а связанные утверждения
                # разной природы — для них есть более подходящие relation-типы.
                existing_claim = self.claims[existing_id]
                if existing_claim.claim_type != claim.claim_type:
                    continue
                from .models import ClaimRelation

                existing_keys = {
                    (r.source_claim_id, r.target_claim_id, r.relation_type)
                    for r in self.relations.values()
                }
                key = (claim.id, existing_id, "supports")
                if key in existing_keys:
                    continue
                relation = ClaimRelation(
                    id=_stable_id("rel", claim.id, existing_id, "supports"),
                    source_claim_id=claim.id,
                    target_claim_id=existing_id,
                    relation_type="supports",
                    weight=round(min(0.97, 0.6 + 0.3 * float(near.get("similarity") or 0.0)), 3),
                    confidence_score=0.85,
                    evidence_strength=round(float(near.get("evidence_strength") or 0.7), 3),
                    source_reliability=round(float(near.get("source_reliability") or 0.7), 3),
                    rationale=f"Близкий дубликат claim_text (cosine={near.get('similarity', 0.0):.3f}) в другой публикации",
                    created_by="rule",
                )
                self.relations[relation.id] = relation
                self._persist("upsert_relation", relation)
                duplicates_found += 1
            if pgvector is not None and getattr(pgvector, "is_active", lambda: False)():
                try:
                    pgvector.upsert_claim_embeddings(pairs)
                except Exception as exc:
                    logger.debug("pgvector_upsert_claims_skip", extra={"error": str(exc)})
            return duplicates_found
        except Exception as exc:
            logger.debug("embed_and_dedup_claims_failed", extra={"error": str(exc)})
            return 0

    def _embedding_provider_name(self) -> str:
        provider = getattr(self, "_embedding_provider", None)
        if callable(provider):
            try:
                return provider()
            except Exception:
                return "deterministic"
        return "deterministic"

    def _clear_publication_knowledge(self, publication_id: str) -> None:
        claim_ids = {claim.id for claim in self.claims.values() if claim.publication_id == publication_id}
        chunk_ids = {chunk.id for chunk in self.chunks.values() if chunk.publication_id == publication_id}
        for claim_id in claim_ids:
            self.claims.pop(claim_id, None)
        for chunk_id in chunk_ids:
            self.chunks.pop(chunk_id, None)
        for rel_id, relation in list(self.relations.items()):
            if relation.source_claim_id in claim_ids or relation.target_claim_id in claim_ids:
                self.relations.pop(rel_id, None)
        for entity in self.entities.values():
            entity.mentions = [m for m in entity.mentions if m.get("publication_id") != publication_id]

    def _detect_sections(self, text: str) -> dict[str, str]:
        section_headers = {
            # English (compatibility with English uploads)
            "abstract": "Abstract",
            "introduction": "Introduction",
            "background": "Background",
            "related work": "Background",
            "method": "Methods",
            "methods": "Methods",
            "methodology": "Methods",
            "approach": "Approach",
            "models": "Models",
            "models and datasets": "Models",
            "datasets": "Datasets",
            "setup": "Setup",
            "experiments": "Experiments",
            "evaluation": "Evaluation",
            "results": "Results",
            "discussion": "Discussion",
            "comparison": "Comparison",
            "comparisons": "Comparison",
            "ablation": "Experiments",
            "limitation": "Limitations",
            "limitations": "Limitations",
            "hypothesis": "Hypothesis",
            "hypotheses": "Hypothesis",
            "conclusion": "Conclusion",
            "conclusions": "Conclusion",
            "contradiction": "Contradiction",
            "reproducibility": "Reproducibility",
            "replication": "Reproducibility",
            # Русские заголовки — основная локаль предметной области
            "аннотация": "Abstract",
            "реферат": "Abstract",
            "введение": "Introduction",
            "предыстория": "Background",
            "обзор литературы": "Background",
            "связанные работы": "Background",
            "метод": "Methods",
            "методы": "Methods",
            "методология": "Methods",
            "подход": "Approach",
            "модели": "Models",
            "модели и данные": "Models",
            "модели и датасеты": "Models",
            "наборы данных": "Datasets",
            "датасеты": "Datasets",
            "данные": "Datasets",
            "постановка": "Setup",
            "постановка эксперимента": "Setup",
            "эксперименты": "Experiments",
            "оценка": "Evaluation",
            "результаты": "Results",
            "обсуждение": "Discussion",
            "сравнение": "Comparison",
            "сравнения": "Comparison",
            "анализ": "Discussion",
            "ограничение": "Limitations",
            "ограничения": "Limitations",
            "гипотеза": "Hypothesis",
            "гипотезы": "Hypothesis",
            "заключение": "Conclusion",
            "выводы": "Conclusion",
            "вывод": "Conclusion",
            "противоречие": "Contradiction",
            "воспроизводимость": "Reproducibility",
            "репродуцируемость": "Reproducibility",
        }
        header_keys = sorted(section_headers.keys(), key=len, reverse=True)
        sections: dict[str, list[str]] = defaultdict(list)
        current = "Abstract"
        for line in text.splitlines():
            clean = line.strip()
            if not clean:
                continue
            lowered = clean.lower().rstrip(":")
            matched: str | None = None
            for header in header_keys:
                if lowered == header or lowered.startswith(header + " "):
                    matched = section_headers[header]
                    break
            if matched and len(clean) <= 40:
                current = matched
                continue
            sections[current].append(clean)
        if not sections:
            sections["Body"].append(text)
        return {k: "\n".join(v) for k, v in sections.items() if v}

    def _chunk_publication(self, publication: Publication, sections: dict[str, str]) -> list[DocumentChunk]:
        for chunk_id in [c.id for c in self.chunks.values() if c.publication_id == publication.id]:
            self.chunks.pop(chunk_id, None)
        chunks: list[DocumentChunk] = []
        index = 0
        for section, text in sections.items():
            buffer = ""
            for sentence in _sentences(text):
                if len(buffer) + len(sentence) > 850 and buffer:
                    chunks.append(self._make_chunk(publication, index, buffer, section))
                    index += 1
                    buffer = ""
                buffer = f"{buffer} {sentence}".strip()
            if buffer:
                chunks.append(self._make_chunk(publication, index, buffer, section))
                index += 1
        for chunk in chunks:
            self.chunks[chunk.id] = chunk
        return chunks

    def _make_chunk(self, publication: Publication, index: int, text: str, section: str) -> DocumentChunk:
        page = max(1, min(publication.pages, int(index / 3) + 1))
        content_hash = hashlib.sha256(f"{publication.id}:{section}:{index}:{text}".encode("utf-8", errors="ignore")).hexdigest()[:24]
        return DocumentChunk(
            id=_stable_id("chunk", publication.id, section, index, content_hash),
            publication_id=publication.id,
            chunk_index=index,
            text=text,
            page_start=page,
            page_end=page,
            section=section,
            embedding=self._chunk_embedding(text),
            metadata={
                "qdrant_collection": "scientific_chunks",
                "vector_dim": 384,
                "content_hash": content_hash,
            },
        )
