from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .ontology import EntityType
from .utils import utc_now

@dataclass
class Publication:
    id: str
    title: str
    abstract: str
    source_type: str
    authors: list[str]
    year: int
    status: str = "uploaded"
    pages: int = 1
    created_at: str = field(default_factory=lambda: utc_now())
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentChunk:
    id: str
    publication_id: str
    chunk_index: int
    text: str
    page_start: int
    page_end: int
    section: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScientificEntity:
    id: str
    canonical_name: str
    entity_type: EntityType
    aliases: list[str]
    mentions: list[dict[str, Any]]
    confidence_score: float


@dataclass
class ScientificClaim:
    id: str
    claim_text: str
    claim_type: str
    subject_entity: str
    predicate: str
    object_entity: str
    comparison_target: str | None
    condition: str | None
    metric: str | None
    value: str | None
    evidence_text: str
    publication_id: str
    chunk_id: str
    page_start: int
    page_end: int
    confidence_score: float
    evidence_strength: float
    source_reliability: float
    extraction_run_id: str


@dataclass
class ClaimRelation:
    id: str
    source_claim_id: str
    target_claim_id: str
    relation_type: Literal["supports", "contradicts", "limits", "extends"]
    weight: float
    confidence_score: float
    evidence_strength: float
    source_reliability: float
    rationale: str
    # Provenance связи: rule (детерминированный экстрактор), llm (модель
    # предложила), manual (создано человеком). Используется для аудита
    # качества и фильтрации в UI.
    created_by: Literal["rule", "llm", "manual"] = "rule"


@dataclass
class PipelineStep:
    name: str
    status: Literal["pending", "running", "completed", "error"]
    started_at: str | None = None
    finished_at: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessingJob:
    id: str
    publication_id: str
    status: Literal["queued", "running", "completed", "error"]
    extraction_run_id: str
    created_at: str = field(default_factory=lambda: utc_now())
    updated_at: str = field(default_factory=lambda: utc_now())
    steps: list[PipelineStep] = field(default_factory=list)
    error: str | None = None


@dataclass
class SearchHit:
    id: str
    kind: Literal["chunk", "claim", "entity"]
    score: float
    title: str
    text: str
    metadata: dict[str, Any]
    score_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class RagAnswer:
    id: str
    question: str
    answer: str
    status: Literal["answered", "insufficient_evidence"]
    confidence_score: float
    sources: list[dict[str, Any]]
    used_entities: list[dict[str, Any]]
    used_claims: list[dict[str, Any]]
    reasoning_trace: list[str]
    limitations: list[str]
    created_at: str = field(default_factory=lambda: utc_now())


@dataclass
class EvaluationRecord:
    id: str
    rag_answer_id: str
    metrics: dict[str, float]
    feedback_events_created: list[str]
    created_at: str = field(default_factory=lambda: utc_now())


@dataclass
class FeedbackEvent:
    id: str
    event_type: str
    target_id: str
    signal: str
    weight_delta: float
    payload: dict[str, Any]
    created_at: str = field(default_factory=lambda: utc_now())
