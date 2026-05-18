"""PostgreSQL adapter — только операционные данные.

В Neo4j-first архитектуре графовые сущности (Publication, ScientificClaim,
ScientificEntity, рёбра) в PG не хранятся. PG отвечает за:

* `users` (auth, отдельный модуль `app.features.auth`)
* `scikb_processing_jobs` / `_steps` / `scikb_extraction_runs`
* `scikb_user_queries`
* `scikb_rag_answers` / `_sources`
* `scikb_answer_evaluations`
* `scikb_feedback_events`
* `scikb_human_review_queue`
* `scikb_retrieval_experiments`
* `scikb_embeddings` (через PgVectorAdapter)
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)


class PostgresAdapter:
    def __init__(self, dsn: str | None) -> None:
        self.dsn = dsn or ""
        self._engine: Any = None
        self._session_factory: Any = None
        self._connected = False
        self._connect_safely()

    def _connect_safely(self) -> None:
        if not self.dsn:
            return
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            self._engine = create_engine(str(self.dsn), pool_pre_ping=True, future=True)
            self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False, autoflush=False)
            with self._engine.connect() as conn:
                conn.execute(_select_one())
            self._connected = True
            logger.info("postgres_adapter_connected")
        except Exception as exc:
            logger.warning("postgres_adapter_disabled", extra={"error": str(exc)})
            self._engine = None
            self._session_factory = None
            self._connected = False

    def is_active(self) -> bool:
        return self._connected

    def _session(self):
        if not self._connected or self._session_factory is None:
            return None
        return self._session_factory()

    # ------------------------------------------------------------------
    # Operational write operations
    # ------------------------------------------------------------------

    def upsert_job(self, job: Any, *, publication: Any | None = None) -> None:
        if not self._connected:
            return
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from ..orm import ProcessingJob

        session = self._session()
        try:
            stmt = pg_insert(ProcessingJob).values(
                id=job.id,
                publication_id=job.publication_id,
                extraction_run_id=job.extraction_run_id,
                status=job.status,
                error=job.error,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[ProcessingJob.id],
                set_={"status": stmt.excluded.status, "error": stmt.excluded.error},
            )
            session.execute(stmt)
            session.commit()
        except Exception as exc:
            logger.debug("pg_upsert_job_failed", extra={"error": str(exc)})
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    def upsert_step(self, job: Any, step: Any) -> None:
        if not self._connected:
            return
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from ..orm import ProcessingStep

        session = self._session()
        try:
            stmt = pg_insert(ProcessingStep).values(
                id=f"{job.id}_{step.name}",
                job_id=job.id,
                name=step.name,
                status=step.status,
                started_at=_to_datetime(step.started_at),
                finished_at=_to_datetime(step.finished_at),
                details=step.details or {},
                error=(step.details or {}).get("error") if step.status == "error" else None,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["job_id", "name"],
                set_={
                    "status": stmt.excluded.status,
                    "started_at": stmt.excluded.started_at,
                    "finished_at": stmt.excluded.finished_at,
                    "details": stmt.excluded.details,
                    "error": stmt.excluded.error,
                },
            )
            session.execute(stmt)
            session.commit()
        except Exception as exc:
            logger.debug("pg_upsert_step_failed", extra={"error": str(exc)})
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    def upsert_rag_answer(self, rag: Any) -> None:
        if not self._connected:
            return
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from ..orm import RagAnswer, RagAnswerSource

        session = self._session()
        try:
            stmt = pg_insert(RagAnswer).values(
                id=rag.id,
                question=rag.question,
                answer=rag.answer,
                status=rag.status,
                confidence_score=rag.confidence_score,
                reasoning_trace=list(rag.reasoning_trace),
                limitations=list(rag.limitations),
            )
            stmt = stmt.on_conflict_do_nothing(index_elements=[RagAnswer.id])
            session.execute(stmt)
            for source in rag.sources:
                src_stmt = pg_insert(RagAnswerSource).values(
                    id=f"{rag.id}_{abs(hash(str(source))) % (10**10):x}",
                    rag_answer_id=rag.id,
                    publication_id=source.get("publication_id"),
                    chunk_id=source.get("chunk_id"),
                    claim_id=source.get("claim_id"),
                    score=source.get("score", 0.0),
                    score_breakdown=source.get("score_breakdown", {}),
                )
                src_stmt = src_stmt.on_conflict_do_nothing(index_elements=[RagAnswerSource.id])
                session.execute(src_stmt)
            session.commit()
        except Exception as exc:
            logger.debug("pg_upsert_rag_failed", extra={"error": str(exc)})
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    def upsert_evaluation(self, record: Any) -> None:
        if not self._connected:
            return
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from ..orm import AnswerEvaluation

        session = self._session()
        try:
            stmt = pg_insert(AnswerEvaluation).values(
                id=record.id,
                rag_answer_id=record.rag_answer_id,
                metrics=record.metrics,
                feedback_events_created=list(record.feedback_events_created),
            )
            stmt = stmt.on_conflict_do_nothing(index_elements=[AnswerEvaluation.id])
            session.execute(stmt)
            session.commit()
        except Exception as exc:
            logger.debug("pg_upsert_eval_failed", extra={"error": str(exc)})
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    def upsert_feedback_event(self, event: Any) -> None:
        if not self._connected:
            return
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from ..orm import FeedbackEvent

        session = self._session()
        try:
            stmt = pg_insert(FeedbackEvent).values(
                id=event.id,
                event_type=event.event_type,
                target_kind=(event.payload or {}).get("target_kind", "claim"),
                target_id=event.target_id,
                signal=event.signal,
                weight_delta=event.weight_delta,
                applied=bool(event.payload.get("_applied")) if event.payload else False,
                payload=event.payload or {},
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[FeedbackEvent.id],
                set_={"applied": stmt.excluded.applied, "payload": stmt.excluded.payload},
            )
            session.execute(stmt)
            session.commit()
        except Exception as exc:
            logger.debug("pg_upsert_feedback_failed", extra={"error": str(exc)})
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    def upsert_review_item(self, item: dict[str, Any]) -> None:
        if not self._connected:
            return
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from ..orm import HumanReviewItem

        session = self._session()
        try:
            stmt = pg_insert(HumanReviewItem).values(
                id=item["id"],
                item_type=item["item_type"],
                item_id=item["item_id"],
                reason=item.get("reason"),
                status=item.get("status", "open"),
                metadata_json=item.get("metadata", {}),
                resolution=item.get("resolution"),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[HumanReviewItem.id],
                set_={"status": stmt.excluded.status, "resolution": stmt.excluded.resolution},
            )
            session.execute(stmt)
            session.commit()
        except Exception as exc:
            logger.debug("pg_upsert_review_failed", extra={"error": str(exc)})
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    def reset_demo_storage(self, scientific_kb: Any) -> None:
        if not self._connected:
            return
        from sqlalchemy import text

        session = self._session()
        try:
            for table in [
                "scikb_human_review_queue",
                "scikb_feedback_events",
                "scikb_answer_evaluations",
                "scikb_retrieval_experiments",
                "scikb_rag_answer_sources",
                "scikb_rag_answers",
                "scikb_user_queries",
                "scikb_extraction_runs",
                "scikb_processing_steps",
                "scikb_processing_jobs",
                "scikb_embeddings",
            ]:
                session.execute(text(f"DELETE FROM {table}"))
            session.commit()
        except Exception as exc:
            logger.debug("pg_reset_failed", extra={"error": str(exc)})
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

    # ------------------------------------------------------------------
    # No-op для совместимости с manager dispatch (графовые данные теперь в Neo4j).
    # ------------------------------------------------------------------

    def upsert_publication(self, publication: Any) -> None:
        return

    def upsert_chunks(self, chunks: Iterable[Any], *, publication: Any | None = None) -> None:
        return

    def upsert_entities(self, entities: Iterable[Any]) -> None:
        return

    def upsert_claims(self, claims: Iterable[Any], *, publication: Any | None = None) -> None:
        return

    def upsert_claim(self, claim: Any) -> None:
        return

    def upsert_relations(self, relations: Iterable[Any]) -> None:
        return

    def upsert_relation(self, relation: Any) -> None:
        return

    def sync_graph(self, publication: Any) -> None:
        return

    def cache_activation(self, publication_id: str, keys: list[str]) -> None:
        return


def _select_one():
    from sqlalchemy import text

    return text("SELECT 1")


def _to_datetime(value: str | None):
    if not value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
