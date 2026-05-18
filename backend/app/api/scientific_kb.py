from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.features.scientific_kb import dump, scientific_kb
from app.features.scientific_kb.ontology import CLAIM_TYPES, PIPELINE_STEPS, RELATION_TYPES


router = APIRouter(tags=["Scientific KB"])


class PublicationPatch(BaseModel):
    title: str | None = None
    abstract: str | None = None
    metadata: dict[str, Any] | None = None


class ClaimPatch(BaseModel):
    claim_text: str | None = None
    claim_type: str | None = None
    subject_entity: str | None = None
    predicate: str | None = None
    object_entity: str | None = None
    metric: str | None = None
    value: str | None = None
    condition: str | None = None
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_strength: float | None = Field(default=None, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class PublicationCreate(BaseModel):
    title: str = Field(default="Untitled scientific publication")
    text: str = Field(min_length=40)
    authors: list[str] = Field(default_factory=list)
    year: int = 2026
    metadata: dict[str, Any] = Field(default_factory=dict)
    run_pipeline: bool = True


class QuestionRequest(BaseModel):
    question: str = Field(min_length=3)
    top_k: int = Field(default=6, ge=1, le=20)
    language: Literal["ru", "en"] = "ru"


class SearchRequest(BaseModel):
    query: str = Field(min_length=2)
    top_k: int = Field(default=8, ge=1, le=30)


class ActivationRequest(BaseModel):
    question: str = Field(min_length=2)


class FeedbackRequest(BaseModel):
    event_type: str = Field(default="user_signal")
    target_id: str
    signal: Literal["positive", "review_required", "neutral"]
    weight_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    payload: dict[str, Any] = Field(default_factory=dict)
    apply_now: bool = True


class ReviewResolveRequest(BaseModel):
    action: Literal["approve", "reject", "edit"]
    note: str | None = None


# ---------------------------------------------------------------------------
# Health & demo control
# ---------------------------------------------------------------------------


@router.get("/v1/scientific/health")
async def scientific_health() -> dict[str, Any]:
    return scientific_kb.summary()


@router.post("/v1/scientific/demo/reset")
async def reset_demo() -> dict[str, Any]:
    return scientific_kb.reset_demo()


@router.get("/v1/scientific/ontology")
async def ontology() -> dict[str, Any]:
    from app.features.scientific_kb.ontology import ALIASES, ONTOLOGY

    return {
        "entity_types": list(ONTOLOGY.keys()),
        "ontology": ONTOLOGY,
        "aliases": ALIASES,
        "claim_types": CLAIM_TYPES,
        "relation_types": RELATION_TYPES,
        "pipeline_steps": PIPELINE_STEPS,
    }


@router.get("/v1/scientific/hybrid-weights")
async def hybrid_weights() -> dict[str, float]:
    return scientific_kb._hybrid_weights()


# ---------------------------------------------------------------------------
# Publications
# ---------------------------------------------------------------------------


@router.post("/v1/publications")
async def create_publication(payload: PublicationCreate) -> dict[str, Any]:
    publication = scientific_kb.create_publication(
        title=payload.title,
        text=payload.text,
        authors=payload.authors or ["Uploaded by user"],
        year=payload.year,
        source_type="text",
        metadata={**payload.metadata, "raw_text": payload.text},
    )
    response: dict[str, Any] = {"publication": dump(publication)}
    if payload.run_pipeline:
        response["processing_job"] = dump(scientific_kb.run_pipeline(publication.id, payload.text))
    return response


@router.post("/v1/publications/upload")
async def upload_publication(file: UploadFile = File(...)) -> dict[str, Any]:
    raw = await file.read()
    text = _extract_upload_text(raw, file.filename or "publication")
    publication = scientific_kb.create_publication(
        title=(file.filename or "Uploaded publication").rsplit(".", 1)[0],
        text=text,
        authors=["Uploaded by user"],
        year=2026,
        source_type="pdf" if (file.filename or "").lower().endswith(".pdf") else "text",
        metadata={"raw_text": text, "filename": file.filename, "content_type": file.content_type},
    )
    job = scientific_kb.run_pipeline(publication.id, text)
    return {"publication": dump(publication), "processing_job": dump(job)}


@router.get("/v1/publications")
async def list_publications(
    research_field: str | None = Query(default=None),
    status: str | None = Query(default=None),
    year: int | None = Query(default=None),
    search: str | None = Query(default=None),
) -> dict[str, Any]:
    items = scientific_kb.list_publications_read(
        research_field=research_field, status=status, year=year, search=search
    )
    return {"items": items, "total": len(items), "engine": scientific_kb.graph_query_engine_name()}


@router.get("/v1/publications/{publication_id}")
async def publication_detail(publication_id: str) -> dict[str, Any]:
    data = scientific_kb.get_publication_detail_read(publication_id)
    if data is None:
        raise HTTPException(status_code=404, detail="publication not found")
    return data


@router.get("/v1/publications/{publication_id}/chunks")
async def list_chunks(publication_id: str) -> dict[str, Any]:
    items = scientific_kb.list_chunks_read(publication_id)
    if items is None:
        raise HTTPException(status_code=404, detail="publication not found")
    return {"items": items}


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


@router.post("/v1/pipeline/publications/{publication_id}/run")
async def pipeline_run(publication_id: str) -> dict[str, Any]:
    if publication_id not in scientific_kb.publications:
        raise HTTPException(status_code=404, detail="publication not found")
    job = scientific_kb.run_pipeline(publication_id)
    return dump(job)


@router.post("/v1/pipeline/publications/{publication_id}/steps/{step}/retry")
async def pipeline_retry_step(publication_id: str, step: str) -> dict[str, Any]:
    if publication_id not in scientific_kb.publications:
        raise HTTPException(status_code=404, detail="publication not found")
    if step not in PIPELINE_STEPS:
        raise HTTPException(status_code=400, detail=f"unknown step: {step}")
    job = scientific_kb.retry_step(publication_id, step)
    return dump(job)


@router.get("/v1/pipeline/jobs")
async def list_pipeline_jobs(publication_id: str | None = Query(default=None)) -> dict[str, Any]:
    jobs = list(scientific_kb.jobs.values())
    if publication_id:
        jobs = [j for j in jobs if j.publication_id == publication_id]
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return {"items": dump(jobs)}


@router.get("/v1/pipeline/jobs/{job_id}")
async def pipeline_job_detail(job_id: str) -> dict[str, Any]:
    job = scientific_kb.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    publication = scientific_kb.publications.get(job.publication_id)
    return {"job": dump(job), "publication": dump(publication) if publication else None}


# ---------------------------------------------------------------------------
# Knowledge entities & claims
# ---------------------------------------------------------------------------


@router.post("/v1/knowledge/extract/{publication_id}")
async def knowledge_extract(publication_id: str) -> dict[str, Any]:
    return await pipeline_run(publication_id)  # type: ignore[arg-type]


@router.get("/v1/knowledge/entities")
async def list_entities(
    entity_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    items = scientific_kb.list_entities_read(entity_type=entity_type, search=search, limit=limit)
    return {"items": items, "total": len(items), "engine": scientific_kb.graph_query_engine_name()}


@router.get("/v1/knowledge/entities/{entity_id}")
async def entity_detail(entity_id: str) -> dict[str, Any]:
    data = scientific_kb.get_entity_detail_read(entity_id)
    if data is None:
        raise HTTPException(status_code=404, detail="entity not found")
    return data


@router.get("/v1/knowledge/claims")
async def list_claims(
    publication_id: str | None = Query(default=None),
    claim_type: str | None = Query(default=None),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    min_evidence_strength: float = Query(default=0.0, ge=0.0, le=1.0),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    items = scientific_kb.list_claims_read(
        publication_id=publication_id,
        claim_type=claim_type,
        min_confidence=min_confidence,
        min_evidence_strength=min_evidence_strength,
        limit=limit,
    )
    return {"items": items, "total": len(items), "engine": scientific_kb.graph_query_engine_name()}


@router.get("/v1/knowledge/claims/{claim_id}")
async def claim_detail(claim_id: str) -> dict[str, Any]:
    data = scientific_kb.get_claim_detail_read(claim_id)
    if data is None:
        raise HTTPException(status_code=404, detail="claim not found")
    return data


@router.get("/v1/knowledge/claims/{claim_id}/evidence")
async def claim_evidence(claim_id: str) -> dict[str, Any]:
    data = scientific_kb.get_claim_evidence_read(claim_id)
    if data is None:
        raise HTTPException(status_code=404, detail="claim not found")
    return data


@router.get("/v1/knowledge/claims/{claim_id}/usage")
async def claim_user_facing_usage(claim_id: str) -> dict[str, Any]:
    """UserFacingKnowledge: продуктовое описание claim'а.

    Возвращает, в каких сценариях он может использоваться (rag_answer,
    recommendation, roadmap, contradiction_warning), какой у него
    retrieval_priority в RAG, человеко-читаемое объяснение полезности
    и pipeline_trace (восстановимая цепочка от публикации до claim'а).
    """
    data = scientific_kb.claim_user_facing_view(claim_id)
    if data is None:
        raise HTTPException(status_code=404, detail="claim not found")
    return data


@router.get("/v1/knowledge/relations")
async def list_relations(
    relation_type: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict[str, Any]:
    items = scientific_kb.list_relations_read(relation_type=relation_type, limit=limit)
    return {"items": items, "total": len(items), "engine": scientific_kb.graph_query_engine_name()}


# ---------------------------------------------------------------------------
# Authors & citations (helper endpoints for frontend Library page)
# ---------------------------------------------------------------------------


@router.get("/v1/authors")
async def list_authors() -> dict[str, Any]:
    return {
        "authors": [dump(a) for a in scientific_kb.demo_authors.values()],
        "organizations": [dump(o) for o in scientific_kb.demo_organizations.values()],
    }


@router.get("/v1/citations")
async def list_citations() -> dict[str, Any]:
    return {"items": scientific_kb.demo_citations}


# ---------------------------------------------------------------------------
# Activation index
# ---------------------------------------------------------------------------


@router.post("/v1/activation/keys")
async def activation_keys(payload: ActivationRequest) -> dict[str, Any]:
    return scientific_kb.activation_keys(payload.question)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@router.post("/v1/search/keyword")
async def keyword_search(payload: SearchRequest) -> dict[str, Any]:
    return {"items": dump(scientific_kb.search_keyword(payload.query, payload.top_k))}


@router.post("/v1/search/semantic")
async def semantic_search(payload: SearchRequest) -> dict[str, Any]:
    return {"items": dump(scientific_kb.search_semantic(payload.query, payload.top_k))}


@router.post("/v1/search/graph")
async def graph_search(payload: SearchRequest) -> dict[str, Any]:
    return {"items": dump(scientific_kb.search_graph(payload.query, payload.top_k))}


@router.post("/v1/search/hybrid")
async def hybrid_search(payload: SearchRequest) -> dict[str, Any]:
    items = scientific_kb.search_hybrid(payload.query, payload.top_k)
    return {
        "items": dump(items),
        "weights": scientific_kb._hybrid_weights(),
        "activation": scientific_kb.activation_keys(payload.query),
    }


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------


@router.post("/v1/rag/ask-with-evidence")
async def ask_with_evidence(payload: QuestionRequest) -> dict[str, Any]:
    return dump(scientific_kb.ask_with_evidence(payload.question, payload.top_k, payload.language))


@router.get("/v1/rag/answers")
async def list_rag_answers(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
    items = sorted(scientific_kb.rag_answers.values(), key=lambda r: r.created_at, reverse=True)
    return {"items": dump(items[:limit])}


@router.get("/v1/rag/answers/{rag_answer_id}")
async def rag_answer_detail(rag_answer_id: str) -> dict[str, Any]:
    rag = scientific_kb.rag_answers.get(rag_answer_id)
    if not rag:
        raise HTTPException(status_code=404, detail="rag answer not found")
    return dump(rag)


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


@router.get("/v1/graph/scientific")
async def graph_all() -> dict[str, Any]:
    return scientific_kb.graph_all()


@router.get("/v1/graph/publication/{publication_id}")
async def graph_publication(publication_id: str) -> dict[str, Any]:
    try:
        return scientific_kb.graph_for_publication(publication_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="publication not found")


@router.get("/v1/graph/entity/{entity_id}")
async def graph_entity(entity_id: str, depth: int = Query(default=2, ge=1, le=4)) -> dict[str, Any]:
    return scientific_kb.graph_for_entity(entity_id, depth=depth)


@router.get("/v1/graph/claim/{claim_id}")
async def graph_claim(claim_id: str, depth: int = Query(default=2, ge=1, le=4)) -> dict[str, Any]:
    return scientific_kb.graph_for_claim(claim_id, depth=depth)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


@router.post("/v1/evaluation/rag-answer/{rag_answer_id}")
async def evaluate_rag_answer(rag_answer_id: str) -> dict[str, Any]:
    try:
        return dump(scientific_kb.evaluate_rag_answer(rag_answer_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="rag answer not found")


@router.get("/v1/evaluation/records")
async def list_evaluations(limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
    items = sorted(scientific_kb.evaluations.values(), key=lambda e: e.created_at, reverse=True)
    return {"items": dump(items[:limit])}


@router.get("/v1/evaluation/aggregate")
async def evaluation_aggregate() -> dict[str, Any]:
    records = list(scientific_kb.evaluations.values())
    if not records:
        return {
            "total": 0,
            "averages": {
                "faithfulness": 0.0,
                "source_coverage": 0.0,
                "hallucination_rate": 0.0,
                "answer_completeness": 0.0,
                "citation_correctness": 0.0,
                "limitation_honesty": 0.0,
                "reasoning_trace_quality": 0.0,
                "contradiction_awareness": 0.0,
            },
        }
    keys = list(records[0].metrics.keys())
    averages = {
        key: round(sum(r.metrics.get(key, 0.0) for r in records) / len(records), 3)
        for key in keys
    }
    return {"total": len(records), "averages": averages}


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------


@router.post("/v1/feedback/events")
async def submit_feedback_event(payload: FeedbackRequest) -> dict[str, Any]:
    event = scientific_kb.submit_feedback(
        event_type=payload.event_type,
        target_id=payload.target_id,
        signal=payload.signal,
        weight_delta=payload.weight_delta,
        payload=payload.payload,
        apply_now=payload.apply_now,
    )
    return dump(event)


@router.get("/v1/feedback/events")
async def list_feedback_events(limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
    items = sorted(scientific_kb.feedback_events.values(), key=lambda e: e.created_at, reverse=True)
    return {"items": dump(items[:limit])}


@router.post("/v1/feedback/apply-pending")
async def feedback_apply_pending() -> dict[str, Any]:
    return scientific_kb.apply_pending_feedback()


# ---------------------------------------------------------------------------
# Human review queue
# ---------------------------------------------------------------------------


@router.get("/v1/review/queue")
async def review_queue_list() -> dict[str, Any]:
    return {"items": scientific_kb.list_review_queue()}


@router.post("/v1/review/queue/{review_id}/resolve")
async def review_queue_resolve(review_id: str, payload: ReviewResolveRequest) -> dict[str, Any]:
    try:
        return scientific_kb.resolve_review_item(review_id, action=payload.action, note=payload.note)
    except KeyError:
        raise HTTPException(status_code=404, detail="review item not found")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Mutations: edit / delete publications and claims (admin actions)
# ---------------------------------------------------------------------------


@router.patch("/v1/publications/{publication_id}")
async def update_publication(publication_id: str, payload: PublicationPatch) -> dict[str, Any]:
    publication = scientific_kb.publications.get(publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="publication not found")
    changes = payload.model_dump(exclude_none=True)
    if "title" in changes:
        publication.title = str(changes["title"]).strip() or publication.title
    if "abstract" in changes:
        publication.abstract = str(changes["abstract"])
    if "metadata" in changes and isinstance(changes["metadata"], dict):
        publication.metadata.update(changes["metadata"])
    # Apply mutation to Neo4j (source of truth).
    persistence = getattr(scientific_kb, "persistence", None)
    if persistence is not None:
        neo4j_adapter = getattr(persistence, "neo4j", None)
        if neo4j_adapter is not None and getattr(neo4j_adapter, "is_active", lambda: False)():
            neo4j_adapter.update_publication_properties(
                publication_id,
                {
                    k: v
                    for k, v in {"title": publication.title, "abstract": publication.abstract}.items()
                    if v is not None
                },
            )
    return dump(publication)


@router.delete("/v1/publications/{publication_id}")
async def delete_publication(publication_id: str) -> dict[str, Any]:
    publication = scientific_kb.publications.pop(publication_id, None)
    if publication is None:
        raise HTTPException(status_code=404, detail="publication not found")
    chunk_ids = {c.id for c in list(scientific_kb.chunks.values()) if c.publication_id == publication_id}
    claim_ids = {c.id for c in list(scientific_kb.claims.values()) if c.publication_id == publication_id}
    for cid in chunk_ids:
        scientific_kb.chunks.pop(cid, None)
    for cid in claim_ids:
        scientific_kb.claims.pop(cid, None)
    scientific_kb.relations = {
        rid: r
        for rid, r in scientific_kb.relations.items()
        if r.source_claim_id not in claim_ids and r.target_claim_id not in claim_ids
    }
    scientific_kb.demo_citations = [
        c for c in scientific_kb.demo_citations
        if c.get("source_publication_id") != publication_id
        and c.get("target_publication_id") != publication_id
    ]
    # Cascade delete from Neo4j (source of truth for graph).
    persistence = getattr(scientific_kb, "persistence", None)
    deleted_pg = {"chunks": 0, "claims": 0}
    if persistence is not None:
        neo4j_adapter = getattr(persistence, "neo4j", None)
        if neo4j_adapter is not None and getattr(neo4j_adapter, "is_active", lambda: False)():
            res = neo4j_adapter.delete_publication(publication_id)
            if res:
                deleted_pg = res
        # Удаляем эмбеддинги из pgvector.
        pgvector = getattr(persistence, "pgvector", None)
        if pgvector is not None and getattr(pgvector, "is_active", lambda: False)():
            pgvector.delete_by_target("chunk", chunk_ids)
            pgvector.delete_by_target("claim", claim_ids)
    return {
        "deleted_publication": publication_id,
        "deleted_chunks": len(chunk_ids) or deleted_pg.get("chunks", 0),
        "deleted_claims": len(claim_ids) or deleted_pg.get("claims", 0),
    }


@router.patch("/v1/knowledge/claims/{claim_id}")
async def update_claim(claim_id: str, payload: ClaimPatch) -> dict[str, Any]:
    claim = scientific_kb.claims.get(claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="claim not found")
    changes = payload.model_dump(exclude_none=True)
    for field, value in changes.items():
        if hasattr(claim, field):
            setattr(claim, field, value)
    persistence = getattr(scientific_kb, "persistence", None)
    if persistence is not None:
        neo4j_adapter = getattr(persistence, "neo4j", None)
        if neo4j_adapter is not None and getattr(neo4j_adapter, "is_active", lambda: False)():
            neo4j_adapter.update_claim_properties(claim_id, {k: getattr(claim, k) for k in changes if hasattr(claim, k)})
    return dump(claim)


@router.delete("/v1/knowledge/claims/{claim_id}")
async def delete_claim(claim_id: str) -> dict[str, str]:
    claim = scientific_kb.claims.pop(claim_id, None)
    if claim is None:
        raise HTTPException(status_code=404, detail="claim not found")
    scientific_kb.relations = {
        rid: r
        for rid, r in scientific_kb.relations.items()
        if r.source_claim_id != claim_id and r.target_claim_id != claim_id
    }
    persistence = getattr(scientific_kb, "persistence", None)
    if persistence is not None:
        neo4j_adapter = getattr(persistence, "neo4j", None)
        if neo4j_adapter is not None and getattr(neo4j_adapter, "is_active", lambda: False)():
            neo4j_adapter.delete_claim(claim_id)
        pgvector = getattr(persistence, "pgvector", None)
        if pgvector is not None and getattr(pgvector, "is_active", lambda: False)():
            pgvector.delete_by_target("claim", [claim_id])
    return {"deleted_claim": claim_id}


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


@router.get("/v1/export/graph.json")
async def export_graph_json() -> dict[str, Any]:
    return scientific_kb.graph_all()


@router.post("/v1/export/search.csv")
async def export_search_csv(payload: SearchRequest):
    import csv
    import io

    from fastapi.responses import StreamingResponse

    hits = scientific_kb.search_hybrid(payload.query, payload.top_k)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["kind", "id", "score", "title", "page_start", "page_end", "text"])
    for hit in hits:
        meta = hit.metadata or {}
        writer.writerow(
            [
                hit.kind,
                hit.id,
                f"{hit.score:.4f}",
                hit.title,
                meta.get("page_start", ""),
                meta.get("page_end", ""),
                (hit.text or "").replace("\n", " ").replace(";", ","),
            ]
        )
    csv_bytes = ("﻿" + buf.getvalue()).encode("utf-8")
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="search_results.csv"'},
    )


def _extract_upload_text(raw: bytes, filename: str) -> str:
    if filename.lower().endswith(".pdf"):
        try:
            from io import BytesIO

            from pypdf import PdfReader

            reader = PdfReader(BytesIO(raw))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages).strip()
            if text:
                return text
        except Exception:
            pass
    for encoding in ("utf-8", "cp1251", "latin-1"):
        try:
            text = raw.decode(encoding).strip()
            if text:
                return text
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail="could not extract text from uploaded file")
