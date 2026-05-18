"""pgvector embeddings for chunks and claims

Revision ID: 2026051603
Revises: 2026051502
Create Date: 2026-05-16 03:00:00

Adds:
* `CREATE EXTENSION IF NOT EXISTS vector`
* `scikb_document_chunks.embedding   vector(384)` (+ HNSW index, cosine)
* `scikb_scientific_claims.embedding vector(384)` (+ HNSW index, cosine)

Both columns are nullable so existing rows survive; new pipeline runs fill them.
HNSW (Hierarchical Navigable Small World) gives O(log n) approximate kNN.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "2026051603"
down_revision: Union[str, Sequence[str], None] = "2026051502"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VECTOR_DIM = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        f"ALTER TABLE scikb_document_chunks "
        f"ADD COLUMN IF NOT EXISTS embedding vector({VECTOR_DIM})"
    )
    op.execute(
        f"ALTER TABLE scikb_scientific_claims "
        f"ADD COLUMN IF NOT EXISTS embedding vector({VECTOR_DIM})"
    )

    # HNSW индексы по cosine distance. m=16, ef_construction=64 — стандартные значения.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scikb_chunks_embedding_hnsw "
        "ON scikb_document_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scikb_claims_embedding_hnsw "
        "ON scikb_scientific_claims USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_scikb_claims_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_scikb_chunks_embedding_hnsw")
    op.execute("ALTER TABLE scikb_scientific_claims DROP COLUMN IF EXISTS embedding")
    op.execute("ALTER TABLE scikb_document_chunks DROP COLUMN IF EXISTS embedding")
