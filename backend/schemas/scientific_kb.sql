-- Evidence-based Scientific Reasoning Engine schema sketch.
-- The current MVP uses an in-memory repository for a zero-setup demo, while these
-- tables define the PostgreSQL target model required by TT.md.

CREATE TABLE IF NOT EXISTS scientific_publications (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    abstract TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL,
    authors JSONB NOT NULL DEFAULT '[]'::jsonb,
    year INTEGER NOT NULL,
    status TEXT NOT NULL,
    pages INTEGER NOT NULL DEFAULT 1,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS processing_jobs (
    id TEXT PRIMARY KEY,
    publication_id TEXT NOT NULL REFERENCES scientific_publications(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    extraction_run_id TEXT NOT NULL,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    publication_id TEXT NOT NULL REFERENCES scientific_publications(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    section TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS scientific_entities (
    id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    mentions JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence_score NUMERIC(5, 4) NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_scientific_entities_canonical
    ON scientific_entities (lower(canonical_name));

CREATE TABLE IF NOT EXISTS scientific_claims (
    id TEXT PRIMARY KEY,
    claim_text TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    subject_entity TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_entity TEXT NOT NULL,
    comparison_target TEXT,
    condition TEXT,
    metric TEXT,
    value TEXT,
    evidence_text TEXT NOT NULL,
    publication_id TEXT NOT NULL REFERENCES scientific_publications(id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    confidence_score NUMERIC(5, 4) NOT NULL,
    evidence_strength NUMERIC(5, 4) NOT NULL,
    source_reliability NUMERIC(5, 4) NOT NULL,
    extraction_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claim_relations (
    id TEXT PRIMARY KEY,
    source_claim_id TEXT NOT NULL REFERENCES scientific_claims(id) ON DELETE CASCADE,
    target_claim_id TEXT NOT NULL REFERENCES scientific_claims(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    weight NUMERIC(5, 4) NOT NULL,
    confidence_score NUMERIC(5, 4) NOT NULL,
    evidence_strength NUMERIC(5, 4) NOT NULL,
    source_reliability NUMERIC(5, 4) NOT NULL,
    rationale TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activation_index_entries (
    activation_key TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    weight NUMERIC(5, 4) NOT NULL DEFAULT 1.0,
    PRIMARY KEY (activation_key, target_kind, target_id)
);

CREATE TABLE IF NOT EXISTS rag_answers (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence_score NUMERIC(5, 4) NOT NULL,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    used_entities JSONB NOT NULL DEFAULT '[]'::jsonb,
    used_claims JSONB NOT NULL DEFAULT '[]'::jsonb,
    reasoning_trace JSONB NOT NULL DEFAULT '[]'::jsonb,
    limitations JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS evaluation_records (
    id TEXT PRIMARY KEY,
    rag_answer_id TEXT NOT NULL REFERENCES rag_answers(id) ON DELETE CASCADE,
    metrics JSONB NOT NULL,
    feedback_events_created JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feedback_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    signal TEXT NOT NULL,
    weight_delta NUMERIC(7, 4) NOT NULL DEFAULT 0,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
