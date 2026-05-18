"""Graph read API.

Read path для всех `/v1/graph/*` endpoints:

1. Если Neo4jAdapter активен — выполняется Cypher-запрос в Neo4j;
2. Иначе используется in-memory fallback (нужен для unit-тестов и graceful
   degradation при недоступном Neo4j).

Источник истины графовых данных — Neo4j. In-memory `self.claims`/`self.relations`/…
остаются как горячий кэш и используются pipeline'ом во время записи.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


def _neo4j(self: Any) -> Any:
    persistence = getattr(self, "persistence", None)
    if persistence is None:
        return None
    adapter = getattr(persistence, "neo4j", None)
    if adapter is None or not getattr(adapter, "is_active", lambda: False)():
        return None
    return adapter


class ScientificGraphMixin:
    # ------------------------------------------------------------------
    # Public API (Neo4j-first, in-memory fallback)
    # ------------------------------------------------------------------

    def graph_all(self) -> dict[str, Any]:
        adapter = _neo4j(self)
        if adapter is not None:
            data = adapter.query_full_graph()
            if data is not None:
                data["engine"] = "neo4j"
                return data
        return self._graph_all_in_memory()

    def graph_for_publication(self, publication_id: str) -> dict[str, Any]:
        if publication_id not in self.publications:
            raise KeyError("publication not found")
        adapter = _neo4j(self)
        if adapter is not None:
            data = adapter.query_publication_subgraph(publication_id)
            if data is not None and data.get("nodes"):
                data["engine"] = "neo4j"
                return data
        return self._graph_for_publication_in_memory(publication_id)

    def graph_for_entity(self, entity_id: str, *, depth: int = 2) -> dict[str, Any]:
        if entity_id not in self.entities:
            raise KeyError("entity not found")
        adapter = _neo4j(self)
        if adapter is not None:
            data = adapter.query_entity_subgraph(entity_id, depth=depth)
            if data is not None and data.get("nodes"):
                data["engine"] = "neo4j"
                return data
        return self._graph_for_entity_in_memory(entity_id, depth=depth)

    def graph_for_claim(self, claim_id: str, *, depth: int = 2) -> dict[str, Any]:
        if claim_id not in self.claims:
            raise KeyError("claim not found")
        adapter = _neo4j(self)
        if adapter is not None:
            data = adapter.query_claim_subgraph(claim_id, depth=depth)
            if data is not None and data.get("nodes"):
                data["engine"] = "neo4j"
                return data
        return self._graph_for_claim_in_memory(claim_id, depth=depth)

    # ------------------------------------------------------------------
    # In-memory fallback implementations (used in tests + when Neo4j down)
    # ------------------------------------------------------------------

    def _graph_all_in_memory(self) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        connected_entity_ids: set[str] = set()

        for claim in self.claims.values():
            for name in (claim.subject_entity, claim.object_entity, claim.metric):
                if not name:
                    continue
                entity_id = self._entity_by_canonical.get(name)
                if entity_id:
                    connected_entity_ids.add(entity_id)

        for publication in self.publications.values():
            nodes.append(
                {
                    "id": publication.id,
                    "label": publication.title,
                    "kind": "Publication",
                    "status": publication.status,
                    "pages": publication.pages,
                    "research_field": publication.metadata.get("research_field"),
                }
            )

        for entity in self.entities.values():
            if entity.id not in connected_entity_ids:
                continue
            nodes.append(
                {
                    "id": entity.id,
                    "label": entity.canonical_name,
                    "kind": entity.entity_type,
                    "confidence_score": entity.confidence_score,
                }
            )

        for claim in self.claims.values():
            nodes.append(
                {
                    "id": claim.id,
                    "label": claim.claim_text,
                    "kind": "ScientificClaim",
                    "claim_type": claim.claim_type,
                    "confidence_score": claim.confidence_score,
                    "evidence_strength": claim.evidence_strength,
                }
            )
            edges.append(
                {
                    "source": claim.publication_id,
                    "target": claim.id,
                    "type": "CONTAINS_CLAIM",
                    "weight": round(claim.evidence_strength, 3),
                }
            )
            for name, rel_type in [(claim.subject_entity, "SUBJECT"), (claim.object_entity, "OBJECT")]:
                entity_id = self._entity_by_canonical.get(name)
                if entity_id:
                    edges.append(
                        {
                            "source": claim.id,
                            "target": entity_id,
                            "type": rel_type,
                            "weight": round(claim.confidence_score, 3),
                        }
                    )
            if claim.metric and claim.metric in self._entity_by_canonical:
                edges.append(
                    {
                        "source": claim.id,
                        "target": self._entity_by_canonical[claim.metric],
                        "type": "EVALUATED_BY",
                        "weight": round(claim.confidence_score, 3),
                    }
                )

        for relation in self.relations.values():
            edges.append(
                {
                    "source": relation.source_claim_id,
                    "target": relation.target_claim_id,
                    "type": relation.relation_type,
                    "weight": round(relation.weight, 3),
                    "confidence_score": relation.confidence_score,
                    "evidence_strength": relation.evidence_strength,
                }
            )

        for citation in self.demo_citations:
            edges.append(
                {
                    "source": citation["source_publication_id"],
                    "target": citation["target_publication_id"],
                    "type": "CITES",
                    "weight": 0.75,
                    "context": citation["context"],
                }
            )

        return {
            "nodes": nodes,
            "edges": edges,
            "summary": {
                "publications": len(self.publications),
                "entities": len(connected_entity_ids),
                "claims": len(self.claims),
                "relations": len(self.relations),
                "citations": len(self.demo_citations),
                "total_edges": len(edges),
            },
            "engine": "in-memory",
        }

    def _graph_for_publication_in_memory(self, publication_id: str) -> dict[str, Any]:
        publication = self.publications[publication_id]
        claim_ids = {c.id for c in self.claims.values() if c.publication_id == publication_id}
        entity_names: set[str] = set()
        for claim_id in claim_ids:
            claim = self.claims[claim_id]
            entity_names.update([claim.subject_entity, claim.object_entity])
        nodes: list[dict[str, Any]] = [
            {
                "id": publication_id,
                "label": publication.title,
                "kind": "Publication",
                "status": publication.status,
                "research_field": publication.metadata.get("research_field"),
            }
        ]
        for claim_id in sorted(claim_ids):
            claim = self.claims[claim_id]
            nodes.append(
                {
                    "id": claim_id,
                    "label": claim.claim_text,
                    "kind": "ScientificClaim",
                    "claim_type": claim.claim_type,
                    "confidence_score": claim.confidence_score,
                    "evidence_strength": claim.evidence_strength,
                }
            )
        for name in sorted(entity_names):
            entity_id = self._entity_by_canonical.get(name)
            if entity_id:
                entity = self.entities[entity_id]
                nodes.append(
                    {
                        "id": entity.id,
                        "label": name,
                        "kind": entity.entity_type,
                        "confidence_score": entity.confidence_score,
                    }
                )
        edges: list[dict[str, Any]] = []
        for claim_id in claim_ids:
            claim = self.claims[claim_id]
            edges.append(
                {"source": publication_id, "target": claim_id, "type": "CONTAINS_CLAIM",
                 "weight": round(claim.evidence_strength, 3)}
            )
            for name, rel_type in [(claim.subject_entity, "SUBJECT"), (claim.object_entity, "OBJECT")]:
                entity_id = self._entity_by_canonical.get(name)
                if entity_id:
                    edges.append({"source": claim_id, "target": entity_id, "type": rel_type,
                                  "weight": round(claim.confidence_score, 3)})
            metric_name = claim.metric
            if metric_name and metric_name in self._entity_by_canonical:
                edges.append(
                    {"source": claim_id, "target": self._entity_by_canonical[metric_name],
                     "type": "EVALUATED_BY", "weight": round(claim.confidence_score, 3)}
                )
        for relation in self.relations.values():
            if relation.source_claim_id in claim_ids and relation.target_claim_id in claim_ids:
                edges.append(
                    {"source": relation.source_claim_id, "target": relation.target_claim_id,
                     "type": relation.relation_type, "weight": relation.weight,
                     "confidence_score": relation.confidence_score,
                     "evidence_strength": relation.evidence_strength}
                )
        for citation in self.demo_citations:
            if citation["source_publication_id"] == publication_id:
                target_id = citation["target_publication_id"]
                if target_id in self.publications:
                    nodes.append(
                        {"id": target_id, "label": self.publications[target_id].title, "kind": "Publication"}
                    )
                edges.append(
                    {"source": publication_id, "target": target_id, "type": "CITES",
                     "weight": 0.75, "context": citation["context"]}
                )
        return {"nodes": _dedup_nodes(nodes), "edges": edges, "engine": "in-memory"}

    def _graph_for_entity_in_memory(self, entity_id: str, *, depth: int = 2) -> dict[str, Any]:
        entity = self.entities[entity_id]
        nodes: dict[str, dict[str, Any]] = {
            entity.id: {
                "id": entity.id, "label": entity.canonical_name, "kind": entity.entity_type,
                "confidence_score": entity.confidence_score, "aliases": entity.aliases,
            }
        }
        edges: list[dict[str, Any]] = []
        related_claim_ids: set[str] = set()
        for claim in self.claims.values():
            if entity.canonical_name in (claim.subject_entity, claim.object_entity, claim.metric):
                related_claim_ids.add(claim.id)
                nodes[claim.id] = {
                    "id": claim.id, "label": claim.claim_text, "kind": "ScientificClaim",
                    "claim_type": claim.claim_type, "confidence_score": claim.confidence_score,
                    "evidence_strength": claim.evidence_strength,
                }
                edges.append(
                    {"source": entity.id, "target": claim.id,
                     "type": "EVALUATED_BY" if claim.metric == entity.canonical_name else "MENTIONS_ENTITY",
                     "weight": round(claim.confidence_score, 3)}
                )
                publication = self.publications.get(claim.publication_id)
                if publication:
                    nodes[publication.id] = {"id": publication.id, "label": publication.title,
                                              "kind": "Publication", "status": publication.status}
                    edges.append({"source": publication.id, "target": claim.id, "type": "CONTAINS_CLAIM",
                                  "weight": round(claim.evidence_strength, 3)})
        if depth >= 2:
            for relation in self.relations.values():
                if relation.source_claim_id in related_claim_ids or relation.target_claim_id in related_claim_ids:
                    for cid in (relation.source_claim_id, relation.target_claim_id):
                        if cid in self.claims and cid not in nodes:
                            claim = self.claims[cid]
                            nodes[cid] = {"id": cid, "label": claim.claim_text,
                                          "kind": "ScientificClaim", "claim_type": claim.claim_type}
                    edges.append(
                        {"source": relation.source_claim_id, "target": relation.target_claim_id,
                         "type": relation.relation_type, "weight": relation.weight}
                    )
        return {"nodes": list(nodes.values()), "edges": edges, "root": entity.id, "engine": "in-memory"}

    def _graph_for_claim_in_memory(self, claim_id: str, *, depth: int = 2) -> dict[str, Any]:
        root = self.claims[claim_id]
        nodes: dict[str, dict[str, Any]] = {
            claim_id: {"id": claim_id, "label": root.claim_text, "kind": "ScientificClaim",
                       "claim_type": root.claim_type, "confidence_score": root.confidence_score,
                       "evidence_strength": root.evidence_strength}
        }
        edges: list[dict[str, Any]] = []
        queue: deque[tuple[str, int]] = deque([(claim_id, 0)])
        visited = {claim_id}
        while queue:
            current_id, level = queue.popleft()
            if level >= depth:
                continue
            for relation in self.relations.values():
                if relation.source_claim_id == current_id or relation.target_claim_id == current_id:
                    other_id = (relation.target_claim_id if relation.source_claim_id == current_id
                                else relation.source_claim_id)
                    if other_id in self.claims and other_id not in nodes:
                        other = self.claims[other_id]
                        nodes[other_id] = {"id": other_id, "label": other.claim_text,
                                           "kind": "ScientificClaim", "claim_type": other.claim_type,
                                           "confidence_score": other.confidence_score,
                                           "evidence_strength": other.evidence_strength}
                    edge_key = (relation.source_claim_id, relation.target_claim_id, relation.relation_type)
                    if not any(e["source"] == edge_key[0] and e["target"] == edge_key[1] and e["type"] == edge_key[2]
                               for e in edges):
                        edges.append({"source": relation.source_claim_id, "target": relation.target_claim_id,
                                      "type": relation.relation_type, "weight": relation.weight,
                                      "confidence_score": relation.confidence_score})
                    if other_id not in visited:
                        visited.add(other_id)
                        queue.append((other_id, level + 1))
        for name in (root.subject_entity, root.object_entity, root.metric):
            entity_id = self._entity_by_canonical.get(name) if name else None
            if entity_id and entity_id not in nodes:
                entity = self.entities[entity_id]
                nodes[entity_id] = {"id": entity_id, "label": entity.canonical_name,
                                    "kind": entity.entity_type, "confidence_score": entity.confidence_score}
                edges.append({"source": claim_id, "target": entity_id, "type": "MENTIONS_ENTITY",
                              "weight": round(root.confidence_score, 3)})
        publication = self.publications.get(root.publication_id)
        if publication:
            nodes[publication.id] = {"id": publication.id, "label": publication.title,
                                      "kind": "Publication", "status": publication.status}
            edges.append({"source": publication.id, "target": claim_id, "type": "CONTAINS_CLAIM",
                          "weight": round(root.evidence_strength, 3)})
        return {"nodes": list(nodes.values()), "edges": edges, "root": claim_id, "engine": "in-memory"}


def _dedup_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for node in nodes:
        node_id = node["id"]
        if node_id in seen:
            continue
        seen.add(node_id)
        unique.append(node)
    return unique
