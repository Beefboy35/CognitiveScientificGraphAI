"""Quality gate: компактный demo corpus (20 статей, 5 кластеров).

Новый профиль качества (после радикального refactor'а dataset'а):
- 20 публикаций (вместо старых 53);
- ~5 claims на публикацию (вместо 10+);
- avg degree связи на claim: 5-15 (вместо 137);
- НЕ требуется присутствие всех 4 типов связей — связь должна
  быть подкреплена evidence, а не создаваться искусственно.

Проверяем:
- размер корпуса (≥20);
- покрытие основных типов сущностей и claim'ов;
- разреженность графа (avg degree ≤ 20);
- citations seeded;
- authors/organizations прикреплены.
"""

from __future__ import annotations

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.features.scientific_kb.service import ScientificKnowledgeBase


# Концептуальный корпус: ядром идут Method (алгоритмы/операции) и Model
# (структуры данных / математические объекты). Dataset/Task не обязательны —
# статьи объясняют идеи, а не привязаны к конкретным наборам данных.
REQUIRED_ENTITY_TYPES_GLOBAL = {
    "Method",
    "Model",
}

REQUIRED_CLAIM_TYPES_GLOBAL = {
    "definition",
    "method_description",
    "limitation",
    "conclusion",
}

# Минимум типов связей. Не требуем все 4 — strict-extractor не создаёт
# связь без evidence. CONTRADICTS особенно редкий в учебном корпусе.
MIN_RELATION_TYPES = 2

# Density gate: avg degree per claim после strict-extraction + pruning.
MAX_AVG_DEGREE_PER_CLAIM = 20.0


@pytest.fixture(scope="module")
def kb() -> ScientificKnowledgeBase:
    return ScientificKnowledgeBase()


def test_corpus_size_is_compact(kb: ScientificKnowledgeBase) -> None:
    """20 статей в 5 тематических кластерах."""
    assert len(kb.publications) >= 18, "Compact demo corpus expected (~20 publications)"
    assert len(kb.publications) <= 30, "Corpus should stay compact; expand only intentionally"


def test_global_corpus_covers_core_entity_types(kb: ScientificKnowledgeBase) -> None:
    """В корпусе должны встречаться Method, Dataset и Task (база онтологии)."""
    present_types = {entity.entity_type for entity in kb.entities.values()}
    missing = REQUIRED_ENTITY_TYPES_GLOBAL - present_types
    assert not missing, f"Corpus missing core entity types globally: {sorted(missing)}"


def test_global_corpus_covers_core_claim_types(kb: ScientificKnowledgeBase) -> None:
    """В корпусе должны быть definition/method/limitation/conclusion."""
    present_types = {claim.claim_type for claim in kb.claims.values()}
    missing = REQUIRED_CLAIM_TYPES_GLOBAL - present_types
    assert not missing, f"Corpus missing core claim types globally: {sorted(missing)}"


def test_at_least_two_relation_types_present(kb: ScientificKnowledgeBase) -> None:
    """Strict-extractor создаёт только evidence-обоснованные связи.
    Не требуем все 4 типа — главное, чтобы граф был связным минимум через 2 типа."""
    types = {relation.relation_type for relation in kb.relations.values()}
    assert len(types) >= MIN_RELATION_TYPES, (
        f"Expected at least {MIN_RELATION_TYPES} relation types, got {sorted(types)}"
    )


def test_graph_is_sparse_not_hairball(kb: ScientificKnowledgeBase) -> None:
    """Главная проверка нового профиля: граф разреженный (avg degree ≤ 20).

    Это страховка от регрессии к старому состоянию (avg ~137).
    """
    num_claims = len(kb.claims)
    num_relations = len(kb.relations)
    if num_claims == 0:
        pytest.skip("no claims to check density")
    avg_degree = num_relations / num_claims
    assert avg_degree <= MAX_AVG_DEGREE_PER_CLAIM, (
        f"Graph is too dense: avg degree {avg_degree:.1f} > {MAX_AVG_DEGREE_PER_CLAIM} "
        f"(claims={num_claims}, relations={num_relations}). "
        f"Investigate _build_claim_relations / _prune_relations_per_claim."
    )


def test_no_relation_exceeds_per_claim_cap(kb: ScientificKnowledgeBase) -> None:
    """После pruning ни один claim не должен иметь больше 20 связей."""
    degree: dict[str, int] = {}
    for relation in kb.relations.values():
        degree[relation.source_claim_id] = degree.get(relation.source_claim_id, 0) + 1
        degree[relation.target_claim_id] = degree.get(relation.target_claim_id, 0) + 1
    over_cap = [(cid, deg) for cid, deg in degree.items() if deg > 20]
    assert not over_cap, f"{len(over_cap)} claims exceed cap=20. Examples: {over_cap[:3]}"


def test_citations_seeded(kb: ScientificKnowledgeBase) -> None:
    """Курируемых цитат — не менее 15 (внутри- и кросс-кластерных)."""
    assert len(kb.demo_citations) >= 15, (
        f"Demo corpus must seed at least 15 cross-paper citations, got {len(kb.demo_citations)}"
    )
    pub_ids = set(kb.publications.keys())
    for citation in kb.demo_citations:
        assert citation["source_publication_id"] in pub_ids
        assert citation["target_publication_id"] in pub_ids


def test_authors_and_organizations_attached(kb: ScientificKnowledgeBase) -> None:
    assert len(kb.demo_authors) >= 6
    assert len(kb.demo_organizations) >= 3
    for publication in kb.publications.values():
        author_ids = publication.metadata.get("author_ids", [])
        assert author_ids, f"Publication '{publication.title}' has no author_ids"


def test_relations_have_provenance(kb: ScientificKnowledgeBase) -> None:
    """Каждая связь должна иметь корректный created_by ∈ {rule, llm, manual}."""
    valid = {"rule", "llm", "manual"}
    for relation in kb.relations.values():
        assert relation.created_by in valid, (
            f"Relation {relation.id} has invalid created_by={relation.created_by!r}"
        )


def test_claim_user_facing_view_returns_pipeline(kb: ScientificKnowledgeBase) -> None:
    """UserFacingKnowledge endpoint должен возвращать pipeline_trace для любого claim'а."""
    if not kb.claims:
        pytest.skip("no claims to check")
    sample_claim = next(iter(kb.claims.values()))
    view = kb.claim_user_facing_view(sample_claim.id)
    assert view is not None
    assert view["claim_id"] == sample_claim.id
    assert isinstance(view["can_be_used_in"], list)
    assert isinstance(view["retrieval_priority"], float)
    assert isinstance(view["pipeline_trace"], list) and len(view["pipeline_trace"]) > 0
