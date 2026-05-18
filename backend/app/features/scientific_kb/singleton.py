from __future__ import annotations

import logging
from typing import Any

from .embedding_service import EmbeddingService
from .llm_extractor import LLMExtractor
from .persistence import PersistenceManager
from .service import ScientificKnowledgeBase

logger = logging.getLogger(__name__)


def _build_persistence(settings: Any) -> PersistenceManager | None:
    if settings is None or not getattr(settings, "persistence_enabled", True):
        return None
    try:
        password_field = getattr(settings, "neo4j_password", None)
        password = (
            password_field.get_secret_value()
            if hasattr(password_field, "get_secret_value")
            else str(password_field or "")
        )
        return PersistenceManager(
            pg_dsn=str(getattr(settings, "pg_dsn", "") or ""),
            neo4j_uri=str(getattr(settings, "neo4j_uri", "") or ""),
            neo4j_user=str(getattr(settings, "neo4j_user", "") or ""),
            neo4j_password=password,
            enable_postgres=bool(getattr(settings, "persistence_postgres", True)),
            enable_neo4j=bool(getattr(settings, "persistence_neo4j", True)),
        )
    except Exception as exc:
        logger.warning("persistence_init_failed", extra={"error": str(exc)})
        return None


def _build_embedding_service(settings: Any) -> EmbeddingService:
    try:
        return EmbeddingService(
            model_name=str(getattr(settings, "embedding_model_name", "sentence-transformers/all-MiniLM-L6-v2")),
            target_dim=int(getattr(settings, "embedding_dim", 384)),
            mode=str(getattr(settings, "embedding_mode", "auto")),
        )
    except Exception:
        return EmbeddingService(mode="deterministic")


def _build_llm_extractor(settings: Any) -> LLMExtractor | None:
    if settings is None:
        return None
    try:
        api_key = getattr(settings, "openrouter_api_key", None)
        if hasattr(api_key, "get_secret_value"):
            api_key = api_key.get_secret_value()
        api_key = str(api_key or "")
        model = str(getattr(settings, "openrouter_model", "") or "")
        if not api_key or not model:
            logger.info("llm_extractor_disabled", extra={"reason": "missing api_key or model"})
            return None
        return LLMExtractor(
            api_key=api_key,
            base_url=str(getattr(settings, "openrouter_base_url", "https://openrouter.ai/api/v1")),
            model=model,
            app_title=str(getattr(settings, "openrouter_app_title", "CognitiveBaseAI")),
            http_referer=str(getattr(settings, "openrouter_http_referer", "")),
            timeout=float(getattr(settings, "extraction_llm_timeout", 60.0)),
            max_retries=int(getattr(settings, "extraction_llm_max_retries", 2)),
        )
    except Exception as exc:
        logger.warning("llm_extractor_init_failed", extra={"error": str(exc)})
        return None


def build_scientific_kb() -> ScientificKnowledgeBase:
    try:
        from app.config.settings import settings
    except Exception:
        settings = None

    embedder = _build_embedding_service(settings)
    persistence = _build_persistence(settings)
    llm_extractor = _build_llm_extractor(settings)
    extraction_mode = str(getattr(settings, "extraction_mode", "hybrid") or "hybrid").lower()
    extraction_on_demo = bool(getattr(settings, "extraction_llm_on_demo", False))

    kb = ScientificKnowledgeBase.__new__(ScientificKnowledgeBase)
    # Provide hooks BEFORE __init__ so demo bootstrap sees the proper providers.
    kb._embedder = embedder  # type: ignore[attr-defined]
    kb._embed_text = embedder.embed  # type: ignore[attr-defined]
    kb._query_embedding = embedder.embed  # type: ignore[attr-defined]
    kb._embedding_provider = embedder.provider  # type: ignore[attr-defined]
    kb.persistence = persistence
    kb._llm_extractor = llm_extractor  # type: ignore[attr-defined]
    kb._extraction_mode = extraction_mode  # type: ignore[attr-defined]
    kb._extraction_llm_on_demo = extraction_on_demo  # type: ignore[attr-defined]
    kb.__init__()  # runs demo bootstrap with persistence + extraction policy active
    return kb


scientific_kb = build_scientific_kb()


def bootstrap_persistence() -> dict[str, Any]:
    """Mirror the current in-memory state into PostgreSQL + Neo4j (+ pgvector).

    Called from FastAPI startup so that real stores reflect the demo corpus
    even if it was loaded before adapters were available.
    """
    if scientific_kb.persistence is None:
        return {"persistence": "disabled"}
    try:
        # IDs стабильные (content-hash через _stable_id), поэтому повторные
        # bootstrap'ы идемпотентны — Cypher MERGE по id не создаёт дубликатов.
        # Не нужно ничего удалять заранее.
        for publication in scientific_kb.publications.values():
            scientific_kb.persistence.upsert_publication(publication)
        scientific_kb.persistence.upsert_chunks(list(scientific_kb.chunks.values()))
        scientific_kb.persistence.upsert_entities(list(scientific_kb.entities.values()))
        scientific_kb.persistence.upsert_claims(list(scientific_kb.claims.values()))
        scientific_kb.persistence.upsert_relations(list(scientific_kb.relations.values()))
        for job in scientific_kb.jobs.values():
            scientific_kb.persistence.upsert_job(job)
            for step in job.steps:
                scientific_kb.persistence.upsert_step(job, step)
        # Цитирования между публикациями — отдельные рёбра CITES в Neo4j.
        neo4j_adapter = getattr(scientific_kb.persistence, "neo4j", None)
        if neo4j_adapter is not None and getattr(neo4j_adapter, "is_active", lambda: False)():
            for citation in scientific_kb.demo_citations:
                try:
                    neo4j_adapter.upsert_citation(
                        source_pub_id=citation["source_publication_id"],
                        target_pub_id=citation["target_publication_id"],
                        context=citation.get("context"),
                    )
                except Exception:
                    pass
            # Финальный pass: удаляем все узлы-сироты (любого label), которые
            # не имеют ни одного ребра. Это даёт чистый граф без visual debris.
            try:
                removed = neo4j_adapter.prune_orphan_nodes()
                if removed:
                    logger.info("bootstrap_pruned_orphan_nodes", extra={"count": removed})
            except Exception as exc:
                logger.debug("prune_orphans_skip", extra={"error": str(exc)})

        # ── In-memory prune ─────────────────────────────────────────────
        # Симметрично чистим in-memory state, чтобы списки в API и graph
        # responses не возвращали неподключённые ScientificEntity, claims и т.д.
        _prune_in_memory_orphans(scientific_kb)
    except Exception as exc:
        logger.warning("bootstrap_persistence_failed", extra={"error": str(exc)})
    return scientific_kb.persistence.status()


def _prune_in_memory_orphans(kb: Any) -> None:
    """Удаляет из in-memory state все entities/claims без связей.

    Граф знаний должен показывать только сущности, реально подкреплённые
    утверждениями (для entities) или участвующие в каких-то связях (для
    claims) — orphan'ы только засоряют выдачу.
    """
    # 1) Entities без mentions → удаляем
    orphan_entities = [
        eid for eid, e in kb.entities.items()
        if not getattr(e, "mentions", None)
    ]
    # 2) Claims без relations и не упоминающие в чанках — допустимы (orphan-claim
    #    по спеке), но всё равно полезно сохранить только осмысленные.
    #    Не трогаем claims — orphan'ы по claim допустимы по требованиям.
    for eid in orphan_entities:
        canonical = kb.entities[eid].canonical_name
        kb.entities.pop(eid, None)
        kb._entity_by_canonical.pop(canonical, None)
    if orphan_entities:
        logger.info(
            "in_memory_pruned_orphan_entities",
            extra={"count": len(orphan_entities)},
        )
