"""Scientific KB schema (TZ §8 — 22+ tables)

Revision ID: 2026051502
Revises: 7e9424fcd3ae
Create Date: 2026-05-15 02:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "2026051502"
down_revision: Union[str, Sequence[str], None] = "7e9424fcd3ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scikb_publications",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("abstract", sa.Text),
        sa.Column("doi", sa.String(255)),
        sa.Column("url", sa.Text),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="text"),
        sa.Column("publication_year", sa.Integer, server_default="2026"),
        sa.Column("publication_type", sa.String(64)),
        sa.Column("language", sa.String(8), server_default="en"),
        sa.Column("status", sa.String(32), nullable=False, server_default="uploaded"),
        sa.Column("pages", sa.Integer, server_default="1"),
        sa.Column("file_hash", sa.String(128)),
        sa.Column("research_field", sa.String(128)),
        sa.Column("extra", sa.JSON, nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status in ('uploaded','text_extracted','chunked','embedded',"
            "'entities_extracted','entities_normalized','claims_extracted',"
            "'claim_relations_built','graph_built','activation_indexed','ready','error')",
            name="ck_scikb_publication_status",
        ),
    )
    op.create_index("ix_scikb_publication_status_year", "scikb_publications", ["status", "publication_year"])
    op.create_index("ix_scikb_publication_doi", "scikb_publications", ["doi"])
    op.create_index("ix_scikb_publication_research_field", "scikb_publications", ["research_field"])
    op.create_index("ix_scikb_publication_file_hash", "scikb_publications", ["file_hash"])

    op.create_table(
        "scikb_authors",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("orcid", sa.String(64)),
        sa.Column("organization", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scikb_authors_name", "scikb_authors", ["name"])

    op.create_table(
        "scikb_publication_authors",
        sa.Column("publication_id", sa.String(64), sa.ForeignKey("scikb_publications.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("author_id", sa.String(64), sa.ForeignKey("scikb_authors.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.Integer, server_default="0"),
    )

    op.create_table(
        "scikb_organizations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("country", sa.String(64)),
        sa.Column("kind", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "scikb_document_chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("publication_id", sa.String(64), sa.ForeignKey("scikb_publications.id", ondelete="CASCADE")),
        sa.Column("section", sa.String(64), server_default="Body"),
        sa.Column("chunk_index", sa.Integer, server_default="0"),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, server_default="0"),
        sa.Column("page_start", sa.Integer, server_default="1"),
        sa.Column("page_end", sa.Integer, server_default="1"),
        sa.Column("qdrant_point_id", sa.String(64)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding_provider", sa.String(64), server_default="deterministic"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("publication_id", "chunk_index", name="uq_scikb_chunk_pub_idx"),
    )
    op.create_index("ix_scikb_chunk_pub", "scikb_document_chunks", ["publication_id"])
    op.create_index("ix_scikb_chunk_content_hash", "scikb_document_chunks", ["content_hash"])

    op.create_table(
        "scikb_scientific_entities",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("canonical_name", sa.String(255), nullable=False, unique=True),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("confidence_score", sa.Float, server_default="0.72"),
        sa.Column("extra", sa.JSON, nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scikb_entity_type", "scikb_scientific_entities", ["entity_type"])

    op.create_table(
        "scikb_entity_aliases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("entity_id", sa.String(64), sa.ForeignKey("scikb_scientific_entities.id", ondelete="CASCADE")),
        sa.Column("alias", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("entity_id", "alias", name="uq_scikb_entity_alias"),
    )
    op.create_index("ix_scikb_entity_alias_eid", "scikb_entity_aliases", ["entity_id"])

    op.create_table(
        "scikb_entity_mentions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("entity_id", sa.String(64), sa.ForeignKey("scikb_scientific_entities.id", ondelete="CASCADE")),
        sa.Column("publication_id", sa.String(64), sa.ForeignKey("scikb_publications.id", ondelete="CASCADE")),
        sa.Column("chunk_id", sa.String(64), sa.ForeignKey("scikb_document_chunks.id", ondelete="SET NULL")),
        sa.Column("raw_text", sa.String(255)),
        sa.Column("normalized_text", sa.String(255)),
        sa.Column("section", sa.String(64)),
        sa.Column("page_start", sa.Integer, server_default="1"),
        sa.Column("page_end", sa.Integer, server_default="1"),
        sa.Column("confidence_score", sa.Float, server_default="0.75"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scikb_mention_eid", "scikb_entity_mentions", ["entity_id"])
    op.create_index("ix_scikb_mention_pub", "scikb_entity_mentions", ["publication_id"])

    op.create_table(
        "scikb_scientific_claims",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("publication_id", sa.String(64), sa.ForeignKey("scikb_publications.id", ondelete="CASCADE")),
        sa.Column("chunk_id", sa.String(64), sa.ForeignKey("scikb_document_chunks.id", ondelete="SET NULL")),
        sa.Column("extraction_run_id", sa.String(64), nullable=False),
        sa.Column("claim_text", sa.Text, nullable=False),
        sa.Column("claim_type", sa.String(64), nullable=False),
        sa.Column("subject_entity", sa.String(255)),
        sa.Column("predicate", sa.String(64)),
        sa.Column("object_entity", sa.String(255)),
        sa.Column("comparison_target", sa.String(255)),
        sa.Column("condition_text", sa.Text),
        sa.Column("metric", sa.String(128)),
        sa.Column("value_text", sa.String(64)),
        sa.Column("evidence_text", sa.Text),
        sa.Column("page_start", sa.Integer, server_default="1"),
        sa.Column("page_end", sa.Integer, server_default="1"),
        sa.Column("confidence_score", sa.Float, server_default="0.65"),
        sa.Column("evidence_strength", sa.Float, server_default="0.55"),
        sa.Column("source_reliability", sa.Float, server_default="0.70"),
        sa.Column("contradiction_risk", sa.Float, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "claim_type in ('definition','method_description','experimental_result',"
            "'comparison','limitation','hypothesis','conclusion',"
            "'contradiction_candidate','replication_note')",
            name="ck_scikb_claim_type",
        ),
    )
    op.create_index("ix_scikb_claim_pub", "scikb_scientific_claims", ["publication_id"])
    op.create_index("ix_scikb_claim_type", "scikb_scientific_claims", ["claim_type"])
    op.create_index("ix_scikb_claim_run", "scikb_scientific_claims", ["extraction_run_id"])

    op.create_table(
        "scikb_claim_entities",
        sa.Column("claim_id", sa.String(64), sa.ForeignKey("scikb_scientific_claims.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("entity_id", sa.String(64), sa.ForeignKey("scikb_scientific_entities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(32), server_default="mention"),
    )

    op.create_table(
        "scikb_claim_relations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_claim_id", sa.String(64), sa.ForeignKey("scikb_scientific_claims.id", ondelete="CASCADE")),
        sa.Column("target_claim_id", sa.String(64), sa.ForeignKey("scikb_scientific_claims.id", ondelete="CASCADE")),
        sa.Column("relation_type", sa.String(32), nullable=False),
        sa.Column("weight", sa.Float, server_default="0.5"),
        sa.Column("confidence_score", sa.Float, server_default="0.5"),
        sa.Column("evidence_strength", sa.Float, server_default="0.5"),
        sa.Column("source_reliability", sa.Float, server_default="0.7"),
        sa.Column("rationale", sa.Text),
        sa.Column("extraction_run_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "relation_type in ('supports','contradicts','limits','extends')",
            name="ck_scikb_relation_type",
        ),
        sa.UniqueConstraint("source_claim_id", "target_claim_id", "relation_type", name="uq_scikb_relation_triple"),
    )
    op.create_index("ix_scikb_relation_source", "scikb_claim_relations", ["source_claim_id"])
    op.create_index("ix_scikb_relation_target", "scikb_claim_relations", ["target_claim_id"])
    op.create_index("ix_scikb_relation_type", "scikb_claim_relations", ["relation_type"])

    op.create_table(
        "scikb_evidence_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("publication_id", sa.String(64), sa.ForeignKey("scikb_publications.id", ondelete="CASCADE")),
        sa.Column("chunk_id", sa.String(64), sa.ForeignKey("scikb_document_chunks.id", ondelete="SET NULL")),
        sa.Column("claim_id", sa.String(64), sa.ForeignKey("scikb_scientific_claims.id", ondelete="SET NULL")),
        sa.Column("evidence_type", sa.String(64), server_default="extracted_claim"),
        sa.Column("text", sa.Text),
        sa.Column("section", sa.String(64)),
        sa.Column("page_start", sa.Integer, server_default="1"),
        sa.Column("page_end", sa.Integer, server_default="1"),
        sa.Column("evidence_strength", sa.Float, server_default="0.55"),
        sa.Column("source_reliability", sa.Float, server_default="0.70"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "scikb_processing_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("publication_id", sa.String(64), sa.ForeignKey("scikb_publications.id", ondelete="CASCADE")),
        sa.Column("extraction_run_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="queued"),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scikb_job_pub", "scikb_processing_jobs", ["publication_id"])
    op.create_index("ix_scikb_job_status", "scikb_processing_jobs", ["status"])

    op.create_table(
        "scikb_processing_steps",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("scikb_processing_jobs.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("details", sa.JSON, server_default=sa.text("'{}'::json")),
        sa.Column("error", sa.Text),
        sa.UniqueConstraint("job_id", "name", name="uq_scikb_step_per_job"),
    )
    op.create_index("ix_scikb_step_job", "scikb_processing_steps", ["job_id"])

    op.create_table(
        "scikb_extraction_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("publication_id", sa.String(64), sa.ForeignKey("scikb_publications.id", ondelete="CASCADE")),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("scikb_processing_jobs.id", ondelete="SET NULL")),
        sa.Column("pipeline_version", sa.String(32), server_default="v2"),
        sa.Column("extractor_model", sa.String(128)),
        sa.Column("embedder_model", sa.String(128)),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("parameters", sa.JSON, server_default=sa.text("'{}'::json")),
    )

    op.create_table(
        "scikb_activation_keys",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("target_kind", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("weight", sa.Float, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("key", "target_kind", "target_id", name="uq_scikb_activation_key"),
    )
    op.create_index("ix_scikb_activation_key", "scikb_activation_keys", ["key"])
    op.create_index("ix_scikb_activation_target", "scikb_activation_keys", ["target_id"])

    op.create_table(
        "scikb_user_queries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("question", sa.Text),
        sa.Column("language", sa.String(8), server_default="ru"),
        sa.Column("top_k", sa.Integer, server_default="6"),
        sa.Column("extra", sa.JSON, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scikb_user_queries_created", "scikb_user_queries", ["created_at"])

    op.create_table(
        "scikb_rag_answers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_query_id", sa.String(64), sa.ForeignKey("scikb_user_queries.id", ondelete="SET NULL")),
        sa.Column("question", sa.Text),
        sa.Column("answer", sa.Text),
        sa.Column("status", sa.String(32), server_default="answered"),
        sa.Column("confidence_score", sa.Float, server_default="0.5"),
        sa.Column("reasoning_trace", sa.JSON, server_default=sa.text("'[]'::json")),
        sa.Column("limitations", sa.JSON, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scikb_rag_created", "scikb_rag_answers", ["created_at"])

    op.create_table(
        "scikb_rag_answer_sources",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("rag_answer_id", sa.String(64), sa.ForeignKey("scikb_rag_answers.id", ondelete="CASCADE")),
        sa.Column("publication_id", sa.String(64), sa.ForeignKey("scikb_publications.id", ondelete="SET NULL")),
        sa.Column("chunk_id", sa.String(64), sa.ForeignKey("scikb_document_chunks.id", ondelete="SET NULL")),
        sa.Column("claim_id", sa.String(64), sa.ForeignKey("scikb_scientific_claims.id", ondelete="SET NULL")),
        sa.Column("score", sa.Float, server_default="0.0"),
        sa.Column("score_breakdown", sa.JSON, server_default=sa.text("'{}'::json")),
    )
    op.create_index("ix_scikb_rag_src_answer", "scikb_rag_answer_sources", ["rag_answer_id"])

    op.create_table(
        "scikb_retrieval_experiments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128)),
        sa.Column("mode", sa.String(32)),
        sa.Column("query", sa.Text),
        sa.Column("results", sa.JSON, server_default=sa.text("'{}'::json")),
        sa.Column("metrics", sa.JSON, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "scikb_answer_evaluations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("rag_answer_id", sa.String(64), sa.ForeignKey("scikb_rag_answers.id", ondelete="CASCADE")),
        sa.Column("metrics", sa.JSON, server_default=sa.text("'{}'::json")),
        sa.Column("feedback_events_created", sa.JSON, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scikb_eval_answer", "scikb_answer_evaluations", ["rag_answer_id"])

    op.create_table(
        "scikb_feedback_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("target_kind", sa.String(32)),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("signal", sa.String(32), nullable=False),
        sa.Column("weight_delta", sa.Float, server_default="0.0"),
        sa.Column("applied", sa.Boolean, server_default=sa.false()),
        sa.Column("payload", sa.JSON, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scikb_feedback_type", "scikb_feedback_events", ["event_type"])
    op.create_index("ix_scikb_feedback_target", "scikb_feedback_events", ["target_id"])
    op.create_index("ix_scikb_feedback_created", "scikb_feedback_events", ["created_at"])

    op.create_table(
        "scikb_human_review_queue",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("item_type", sa.String(32), nullable=False),
        sa.Column("item_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("status", sa.String(32), server_default="open"),
        sa.Column("metadata_json", sa.JSON, server_default=sa.text("'{}'::json")),
        sa.Column("resolution", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scikb_review_status", "scikb_human_review_queue", ["status"])
    op.create_index("ix_scikb_review_item_type", "scikb_human_review_queue", ["item_type"])

    op.create_table(
        "scikb_publication_citations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_publication_id", sa.String(64), sa.ForeignKey("scikb_publications.id", ondelete="CASCADE")),
        sa.Column("target_publication_id", sa.String(64), sa.ForeignKey("scikb_publications.id", ondelete="CASCADE")),
        sa.Column("context", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_publication_id", "target_publication_id", name="uq_scikb_citation"),
    )
    op.create_index("ix_scikb_citation_src", "scikb_publication_citations", ["source_publication_id"])
    op.create_index("ix_scikb_citation_tgt", "scikb_publication_citations", ["target_publication_id"])


def downgrade() -> None:
    for table in [
        "scikb_publication_citations",
        "scikb_human_review_queue",
        "scikb_feedback_events",
        "scikb_answer_evaluations",
        "scikb_retrieval_experiments",
        "scikb_rag_answer_sources",
        "scikb_rag_answers",
        "scikb_user_queries",
        "scikb_activation_keys",
        "scikb_extraction_runs",
        "scikb_processing_steps",
        "scikb_processing_jobs",
        "scikb_evidence_items",
        "scikb_claim_relations",
        "scikb_claim_entities",
        "scikb_scientific_claims",
        "scikb_entity_mentions",
        "scikb_entity_aliases",
        "scikb_scientific_entities",
        "scikb_document_chunks",
        "scikb_organizations",
        "scikb_publication_authors",
        "scikb_authors",
        "scikb_publications",
    ]:
        op.drop_table(table)
