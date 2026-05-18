"""SQLAlchemy 2.0 ORM — операционные таблицы PostgreSQL и единый эмбеддинг-индекс.

В Neo4j-first архитектуре PostgreSQL хранит:

* **operational tables**: jobs / steps / runs / rag answers / user queries /
  evaluations / feedback events / review queue / retrieval experiments;
* **scikb_embeddings** — единая таблица векторов (HNSW по cosine) для
  поиска. ``target_id`` ссылается на id узла в Neo4j.

Графовые данные (Publication, ScientificClaim, ScientificEntity, рёбра)
живут в Neo4j и сюда не дублируются.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Pipeline & runs
# ---------------------------------------------------------------------------


class ProcessingJob(Base):
    __tablename__ = "scikb_processing_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    publication_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    extraction_run_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class ProcessingStep(Base):
    __tablename__ = "scikb_processing_steps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (UniqueConstraint("job_id", "name", name="uq_scikb_step_per_job"),)


class ExtractionRun(Base):
    __tablename__ = "scikb_extraction_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    publication_id: Mapped[str] = mapped_column(String(64), index=True)
    job_id: Mapped[str | None] = mapped_column(String(64))
    pipeline_version: Mapped[str] = mapped_column(String(32), default="v2")
    extractor_model: Mapped[str | None] = mapped_column(String(128))
    embedder_model: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)


# ---------------------------------------------------------------------------
# Retrieval / RAG records
# ---------------------------------------------------------------------------


class UserQuery(Base):
    __tablename__ = "scikb_user_queries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    question: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), default="ru")
    top_k: Mapped[int] = mapped_column(Integer, default=6)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class RagAnswer(Base):
    __tablename__ = "scikb_rag_answers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    user_query_id: Mapped[str | None] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="answered")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    reasoning_trace: Mapped[list] = mapped_column(JSON, default=list)
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class RagAnswerSource(Base):
    __tablename__ = "scikb_rag_answer_sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    rag_answer_id: Mapped[str] = mapped_column(String(64), index=True)
    publication_id: Mapped[str | None] = mapped_column(String(64))
    chunk_id: Mapped[str | None] = mapped_column(String(64))
    claim_id: Mapped[str | None] = mapped_column(String(64))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)


class RetrievalExperiment(Base):
    __tablename__ = "scikb_retrieval_experiments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128))
    mode: Mapped[str] = mapped_column(String(32))
    query: Mapped[str] = mapped_column(Text)
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Evaluation & feedback
# ---------------------------------------------------------------------------


class AnswerEvaluation(Base):
    __tablename__ = "scikb_answer_evaluations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    rag_answer_id: Mapped[str] = mapped_column(String(64), index=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    feedback_events_created: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class FeedbackEvent(Base):
    __tablename__ = "scikb_feedback_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    target_kind: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64), index=True)
    signal: Mapped[str] = mapped_column(String(32))
    weight_delta: Mapped[float] = mapped_column(Float, default=0.0)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class HumanReviewItem(Base):
    __tablename__ = "scikb_human_review_queue"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    item_type: Mapped[str] = mapped_column(String(32), index=True)
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    resolution: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Vector embeddings (единая таблица; target_id ссылается на Neo4j id)
# ---------------------------------------------------------------------------


class Embedding(Base):
    __tablename__ = "scikb_embeddings"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), default="deterministic")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (UniqueConstraint("target_kind", "target_id", name="uq_scikb_embedding_target"),)


ALL_TABLES: list[type[Base]] = [
    ProcessingJob,
    ProcessingStep,
    ExtractionRun,
    UserQuery,
    RagAnswer,
    RagAnswerSource,
    RetrievalExperiment,
    AnswerEvaluation,
    FeedbackEvent,
    HumanReviewItem,
    Embedding,
]
