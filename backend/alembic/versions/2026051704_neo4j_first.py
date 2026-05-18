"""Neo4j-first refactor: graph data lives in Neo4j, PG keeps operational tables only

Revision ID: 2026051704
Revises: 2026051603
Create Date: 2026-05-17 04:00:00

Changes:
* Drop scientific tables whose content now lives in Neo4j (publications,
  chunks, entities, claims, claim-relations, citations, mentions, aliases).
* Replace `embedding` columns in chunks/claims with a single dedicated
  table ``scikb_embeddings`` keyed by (target_kind, target_id) — references
  Neo4j node IDs.
* Keep operational tables: jobs, steps, runs, rag_answers, evaluations,
  feedback events, review queue, user_queries, retrieval_experiments.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "2026051704"
down_revision: Union[str, Sequence[str], None] = "2026051603"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VECTOR_DIM = 384

# Графовые таблицы — переезжают в Neo4j (узлы и рёбра).
GRAPH_TABLES = [
    "scikb_publication_citations",
    "scikb_publication_authors",
    "scikb_authors",
    "scikb_organizations",
    "scikb_claim_entities",
    "scikb_claim_relations",
    "scikb_entity_mentions",
    "scikb_entity_aliases",
    "scikb_scientific_entities",
    "scikb_evidence_items",
    "scikb_activation_keys",
]


def upgrade() -> None:
    # 1) Drop graph tables (с FK cascade — ON DELETE CASCADE уже в схеме).
    for table in GRAPH_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    # 2) scientific_claims и document_chunks — DROP полностью.
    op.execute("DROP TABLE IF EXISTS scikb_scientific_claims CASCADE")
    op.execute("DROP TABLE IF EXISTS scikb_document_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS scikb_publications CASCADE")

    # 3) Единая таблица для всех embeddings.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "scikb_embeddings",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("target_kind", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("model", sa.String(64), nullable=False, server_default="deterministic"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("target_kind", "target_id", name="uq_scikb_embedding_target"),
    )
    op.execute(
        f"ALTER TABLE scikb_embeddings ADD COLUMN embedding vector({VECTOR_DIM}) NOT NULL"
    )
    op.create_index(
        "ix_scikb_embeddings_target_kind",
        "scikb_embeddings",
        ["target_kind"],
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scikb_embeddings_vector_hnsw "
        "ON scikb_embeddings USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_scikb_embeddings_vector_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_scikb_embeddings_target_kind")
    op.execute("DROP TABLE IF EXISTS scikb_embeddings")
    # Восстановление снесённых графовых таблиц не предусмотрено — их источник
    # истины теперь Neo4j. Downgrade оставлен пустым по содержательным
    # причинам; в случае отката используйте Neo4j-снимок.
