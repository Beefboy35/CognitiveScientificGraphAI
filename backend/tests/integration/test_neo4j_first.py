"""Integration tests: требуют живые Neo4j + PostgreSQL.

Запускаются ТОЛЬКО командой ``pytest -m integration``. По умолчанию
исключены через ``addopts = -m "not integration"`` в [pytest.ini].

Эти тесты проверяют, что:
1. Neo4j-first архитектура работает: после bootstrap граф наполнен и
   повторный bootstrap не создаёт дубликатов (благодаря stable IDs).
2. Cypher batch-fetch методы корректно возвращают payload'ы для
   id'шников, которых нет в in-memory кэше.
3. Pgvector embeddings (target_kind='chunk'|'claim') живут в единой
   таблице scikb_embeddings и доступны через cosine-similarity search.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def kb():
    """Реальный KB-инстанс с поднятыми адаптерами.

    Требует переменные окружения:
    - DATABASE_URL=postgresql+psycopg2://...
    - NEO4J_URI=bolt://...
    - NEO4J_USER, NEO4J_PASSWORD
    """
    if not os.getenv("NEO4J_URI") or not os.getenv("DATABASE_URL"):
        pytest.skip("integration tests need NEO4J_URI + DATABASE_URL")
    from app.features.scientific_kb.singleton import scientific_kb, bootstrap_persistence

    bootstrap_persistence()
    return scientific_kb


def test_neo4j_contains_publications_after_bootstrap(kb) -> None:
    adapter = kb.persistence.neo4j
    assert adapter.is_active()
    summary = adapter.count_summary()
    assert summary is not None
    assert summary["publications"] >= 1
    assert summary["claims"] >= 1


def test_stable_ids_keep_bootstrap_idempotent(kb) -> None:
    """Повторный bootstrap не должен раздувать граф (stable content-hash IDs)."""
    from app.features.scientific_kb.singleton import bootstrap_persistence

    adapter = kb.persistence.neo4j
    before = adapter.count_summary()
    bootstrap_persistence()
    after = adapter.count_summary()
    assert before is not None and after is not None
    assert before["publications"] == after["publications"]
    assert before["claims"] == after["claims"]
    assert before["relations"] == after["relations"]


def test_cypher_batch_fetch_chunks(kb) -> None:
    adapter = kb.persistence.neo4j
    sample_ids = [c.id for c in list(kb.chunks.values())[:5]]
    payloads = adapter.fetch_chunks_by_ids(sample_ids)
    assert set(payloads.keys()) == set(sample_ids)
    for cid in sample_ids:
        assert payloads[cid]["id"] == cid
        assert payloads[cid]["publication_id"]


def test_cypher_batch_fetch_claims(kb) -> None:
    adapter = kb.persistence.neo4j
    sample_ids = [c.id for c in list(kb.claims.values())[:5]]
    payloads = adapter.fetch_claims_by_ids(sample_ids)
    assert set(payloads.keys()) == set(sample_ids)


def test_pgvector_embeddings_searchable(kb) -> None:
    pgvector = kb.persistence.pgvector
    if pgvector is None or not pgvector.is_active():
        pytest.skip("pgvector adapter inactive")
    vector = kb._embed_query("сортировка массива")  # type: ignore[attr-defined]
    rows = pgvector.search_similar_chunks(vector, top_k=3)
    assert isinstance(rows, list)
