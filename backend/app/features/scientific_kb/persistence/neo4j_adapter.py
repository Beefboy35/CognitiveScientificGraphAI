from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# Имена меток для рёбер MENTIONS_ENTITY / EVALUATED_BY / CITES вынесены, чтобы
# read-запросы могли их собирать без дублирования.
CLAIM_TO_ENTITY_TYPES = ("MENTIONS_ENTITY", "EVALUATED_BY")
PUB_LINK_TYPES = ("CONTAINS_CLAIM", "CITES", "BELONGS_TO_FIELD")
CLAIM_RELATION_TYPES = ("SUPPORTS", "CONTRADICTS", "LIMITS", "EXTENDS")


def _node_payload(node: Any) -> dict[str, Any]:
    """Конвертирует neo4j.Node в frontend-friendly dict."""
    labels = list(getattr(node, "labels", []) or [])
    props = dict(node)
    kind = labels[0] if labels else "Unknown"
    if kind == "ResearchField":
        node_id = props.get("name") or ""
        label = props.get("name") or ""
    elif kind == "Publication":
        node_id = props.get("id") or ""
        label = props.get("title") or props.get("id") or ""
    elif kind == "ScientificClaim":
        node_id = props.get("id") or ""
        label = props.get("claim_text") or props.get("id") or ""
    elif kind == "ScientificEntity":
        node_id = props.get("id") or ""
        label = props.get("canonical_name") or props.get("id") or ""
        kind = props.get("entity_type") or kind
    else:
        node_id = props.get("id") or props.get("name") or ""
        label = props.get("title") or props.get("canonical_name") or props.get("name") or node_id
    payload = {"id": node_id, "label": label, "kind": kind}
    # Прокидываем релевантные числовые поля для UI.
    for key in (
        "claim_type",
        "confidence_score",
        "evidence_strength",
        "status",
        "research_field",
        "publication_id",
        "year",
    ):
        if key in props and props[key] is not None:
            payload[key] = props[key]
    return payload


def _relationship_payload(rel: Any, *, start_node: Any = None, end_node: Any = None) -> dict[str, Any]:
    """Конвертирует neo4j.Relationship в edge-dict.

    В neo4j-python driver 5.x ``rel.start_node`` / ``rel.end_node`` могут быть
    None если узлы не были явно возвращены в запросе. Поэтому Cypher должен
    возвращать ``startNode(r) AS src, endNode(r) AS tgt`` и передавать их сюда.
    """
    start = start_node if start_node is not None else getattr(rel, "start_node", None)
    end = end_node if end_node is not None else getattr(rel, "end_node", None)
    start_props = dict(start) if start else {}
    end_props = dict(end) if end else {}
    start_labels = list(getattr(start, "labels", []) or []) if start else []
    end_labels = list(getattr(end, "labels", []) or []) if end else []
    if "ResearchField" in start_labels:
        source = start_props.get("name") or ""
    else:
        source = start_props.get("id") or start_props.get("name") or ""
    if "ResearchField" in end_labels:
        target = end_props.get("name") or ""
    else:
        target = end_props.get("id") or end_props.get("name") or ""
    rel_type = rel.type
    if rel_type in CLAIM_RELATION_TYPES:
        rel_type = rel_type.lower()
    payload: dict[str, Any] = {"source": source, "target": target, "type": rel_type}
    rel_props = dict(rel)
    for key in ("weight", "confidence_score", "evidence_strength", "source_reliability", "context"):
        if key in rel_props and rel_props[key] is not None:
            payload[key] = rel_props[key]
    return payload


class Neo4jAdapter:
    def __init__(self, uri: str | None, user: str | None, password: str | None) -> None:
        self.uri = uri or ""
        self.user = user or ""
        self.password = password or ""
        self._driver: Any = None
        self._connected = False
        self._connect_safely()

    def _connect_safely(self) -> None:
        if not self.uri:
            return
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            with self._driver.session() as session:
                session.run("RETURN 1").consume()
            self._connected = True
            self._apply_constraints()
            logger.info("neo4j_adapter_connected")
        except Exception as exc:
            logger.warning("neo4j_adapter_disabled", extra={"error": str(exc)})
            self._driver = None
            self._connected = False

    def is_active(self) -> bool:
        return self._connected

    def _apply_constraints(self) -> None:
        if not self._connected:
            return
        try:
            with self._driver.session() as session:
                statements = [
                    "CREATE CONSTRAINT publication_id IF NOT EXISTS FOR (n:Publication) REQUIRE n.id IS UNIQUE",
                    "CREATE CONSTRAINT claim_id IF NOT EXISTS FOR (n:ScientificClaim) REQUIRE n.id IS UNIQUE",
                    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:ScientificEntity) REQUIRE n.id IS UNIQUE",
                    "CREATE CONSTRAINT author_id IF NOT EXISTS FOR (n:Author) REQUIRE n.id IS UNIQUE",
                    "CREATE CONSTRAINT field_name IF NOT EXISTS FOR (n:ResearchField) REQUIRE n.name IS UNIQUE",
                ]
                for stmt in statements:
                    try:
                        session.run(stmt).consume()
                    except Exception:
                        pass
        except Exception as exc:
            logger.debug("neo4j_constraints_failed", extra={"error": str(exc)})

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def upsert_publication(self, publication: Any) -> None:
        if not self._connected:
            return
        try:
            metadata = publication.metadata or {}
            with self._driver.session() as session:
                session.run(
                    """
                    MERGE (p:Publication {id: $id})
                    SET p.title = $title,
                        p.abstract = $abstract,
                        p.year = $year,
                        p.status = $status,
                        p.source_type = $source_type,
                        p.research_field = $research_field,
                        p.pages = $pages,
                        p.authors = $authors,
                        p.organizations = $organizations
                    """,
                    id=publication.id,
                    title=publication.title,
                    abstract=publication.abstract,
                    year=publication.year,
                    status=publication.status,
                    source_type=publication.source_type,
                    research_field=metadata.get("research_field"),
                    pages=publication.pages,
                    authors=list(publication.authors or []),
                    organizations=list(metadata.get("organizations") or []),
                ).consume()
                research_field = metadata.get("research_field")
                if research_field:
                    session.run(
                        """
                        MERGE (f:ResearchField {name: $name})
                        WITH f
                        MATCH (p:Publication {id: $pid})
                        MERGE (p)-[:BELONGS_TO_FIELD]->(f)
                        """,
                        name=research_field,
                        pid=publication.id,
                    ).consume()
                # Цитирования: пишем рёбра CITES из metadata.cites (заполняется seed.py).
                cites = metadata.get("cites") or []
                for target_pub in cites:
                    if not target_pub:
                        continue
                    try:
                        session.run(
                            """
                            MATCH (src:Publication {id: $src})
                            MERGE (tgt:Publication {id: $tgt})
                            MERGE (src)-[r:CITES]->(tgt)
                            """,
                            src=publication.id,
                            tgt=target_pub,
                        ).consume()
                    except Exception:
                        pass
        except Exception as exc:
            logger.debug("neo4j_upsert_publication_failed", extra={"error": str(exc)})

    def upsert_entities(self, entities: Iterable[Any]) -> None:
        if not self._connected:
            return
        try:
            with self._driver.session() as session:
                for entity in entities:
                    session.run(
                        """
                        MERGE (e:ScientificEntity {id: $id})
                        SET e.canonical_name = $name,
                            e.entity_type = $etype,
                            e.confidence_score = $cs,
                            e.aliases = $aliases
                        """,
                        id=entity.id,
                        name=entity.canonical_name,
                        etype=entity.entity_type,
                        cs=entity.confidence_score,
                        aliases=list(entity.aliases or []),
                    ).consume()
        except Exception as exc:
            logger.debug("neo4j_upsert_entities_failed", extra={"error": str(exc)})

    def upsert_claims(self, claims: Iterable[Any], *, publication: Any | None = None) -> None:
        if not self._connected:
            return
        try:
            with self._driver.session() as session:
                for claim in claims:
                    session.run(
                        """
                        MERGE (c:ScientificClaim {id: $id})
                        SET c.claim_text = $text,
                            c.claim_type = $ctype,
                            c.subject_entity = $subj,
                            c.predicate = $pred,
                            c.object_entity = $obj,
                            c.comparison_target = $cmp,
                            c.condition = $cond,
                            c.metric = $metric,
                            c.value = $value,
                            c.evidence_text = $ev_text,
                            c.confidence_score = $conf,
                            c.evidence_strength = $ev,
                            c.source_reliability = $src,
                            c.publication_id = $pub_id,
                            c.chunk_id = $chunk_id,
                            c.extraction_run_id = $run_id,
                            c.page_start = $ps,
                            c.page_end = $pe
                        """,
                        id=claim.id,
                        text=claim.claim_text,
                        ctype=claim.claim_type,
                        subj=claim.subject_entity,
                        pred=claim.predicate,
                        obj=claim.object_entity,
                        cmp=claim.comparison_target,
                        cond=claim.condition,
                        metric=claim.metric,
                        value=claim.value,
                        ev_text=claim.evidence_text,
                        conf=claim.confidence_score,
                        ev=claim.evidence_strength,
                        src=claim.source_reliability,
                        pub_id=claim.publication_id,
                        chunk_id=claim.chunk_id,
                        run_id=claim.extraction_run_id,
                        ps=claim.page_start,
                        pe=claim.page_end,
                    ).consume()
                    session.run(
                        """
                        MATCH (p:Publication {id: $pub_id})
                        MATCH (c:ScientificClaim {id: $claim_id})
                        MERGE (p)-[r:CONTAINS_CLAIM]->(c)
                        SET r.evidence_strength = $ev
                        """,
                        pub_id=claim.publication_id,
                        claim_id=claim.id,
                        ev=claim.evidence_strength,
                    ).consume()
                    # MENTIONS_ENTITY / EVALUATED_BY рёбра — связь claim'а со
                    # своими subject/object/metric entity по canonical_name.
                    for entity_name, edge_type in (
                        (claim.subject_entity, "MENTIONS_ENTITY"),
                        (claim.object_entity, "MENTIONS_ENTITY"),
                        (claim.metric, "EVALUATED_BY"),
                    ):
                        if not entity_name:
                            continue
                        try:
                            session.run(
                                f"""
                                MATCH (c:ScientificClaim {{id: $claim_id}})
                                MATCH (e:ScientificEntity {{canonical_name: $name}})
                                MERGE (c)-[r:{edge_type}]->(e)
                                SET r.confidence_score = $conf
                                """,
                                claim_id=claim.id,
                                name=entity_name,
                                conf=claim.confidence_score,
                            ).consume()
                        except Exception:
                            pass
        except Exception as exc:
            logger.debug("neo4j_upsert_claims_failed", extra={"error": str(exc)})

    def upsert_claim(self, claim: Any) -> None:
        self.upsert_claims([claim])

    def upsert_relations(self, relations: Iterable[Any]) -> None:
        if not self._connected:
            return
        try:
            with self._driver.session() as session:
                for relation in relations:
                    rel_type = relation.relation_type.upper()
                    session.run(
                        f"""
                        MATCH (a:ScientificClaim {{id: $sid}})
                        MATCH (b:ScientificClaim {{id: $tid}})
                        MERGE (a)-[r:{rel_type}]->(b)
                        SET r.weight = $w,
                            r.confidence_score = $conf,
                            r.evidence_strength = $ev,
                            r.source_reliability = $src
                        """,
                        sid=relation.source_claim_id,
                        tid=relation.target_claim_id,
                        w=relation.weight,
                        conf=relation.confidence_score,
                        ev=relation.evidence_strength,
                        src=relation.source_reliability,
                    ).consume()
        except Exception as exc:
            logger.debug("neo4j_upsert_relations_failed", extra={"error": str(exc)})

    def upsert_relation(self, relation: Any) -> None:
        self.upsert_relations([relation])

    def upsert_citation(self, *, source_pub_id: str, target_pub_id: str, context: str | None = None) -> None:
        if not self._connected:
            return
        try:
            with self._driver.session() as session:
                session.run(
                    """
                    MERGE (src:Publication {id: $src})
                    MERGE (tgt:Publication {id: $tgt})
                    MERGE (src)-[r:CITES]->(tgt)
                    SET r.context = $context
                    """,
                    src=source_pub_id,
                    tgt=target_pub_id,
                    context=context,
                ).consume()
        except Exception as exc:
            logger.debug("neo4j_upsert_citation_failed", extra={"error": str(exc)})

    def sync_graph(self, publication: Any) -> None:
        # The graph is kept in sync via upsert_publication / claims / relations.
        return

    def reset_demo_storage(self, scientific_kb: Any) -> None:
        if not self._connected:
            return
        try:
            with self._driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n").consume()
        except Exception as exc:
            logger.debug("neo4j_reset_failed", extra={"error": str(exc)})

    def prune_orphan_nodes(self) -> int:
        """Удаляет все узлы без единого ребра (isolated nodes любого типа).

        Вызывается после bootstrap'а — гарантирует что в графе нет сущностей-
        сирот, которые не имеют связей с публикациями/claims (визуально это
        были бы одинокие точки на сцене графа).

        Возвращает число удалённых узлов.
        """
        if not self._connected:
            return 0
        try:
            with self._driver.session() as session:
                result = session.run(
                    "MATCH (n) WHERE NOT (n)-[]-() DELETE n RETURN count(n) AS removed"
                ).single()
                count = int(result["removed"]) if result else 0
                if count:
                    logger.info("neo4j_pruned_orphans", extra={"count": count})
                return count
        except Exception as exc:
            logger.debug("neo4j_prune_orphans_failed", extra={"error": str(exc)})
            return 0

    # ------------------------------------------------------------------
    # Reads — Cypher-запросы, которые используются /v1/graph/* endpoints.
    # ------------------------------------------------------------------

    def query_full_graph(self, *, max_claim_relations: int = 1500) -> dict[str, Any] | None:
        """Возвращает полный граф: Publication, ScientificClaim, ScientificEntity
        и рёбра между ними. Чтобы не возвращать сотни тысяч claim-relations
        (на демо-корпусе их ~67k) — берём top-N по weight.
        Изолированные entity (orphan) не возвращаются."""
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                # 1) Все Publication.
                nodes_map: dict[str, dict[str, Any]] = {}
                for rec in session.run("MATCH (p:Publication) RETURN p AS node"):
                    payload = _node_payload(rec["node"])
                    if payload["id"]:
                        nodes_map[payload["id"]] = payload
                # 2) ScientificClaim.
                for rec in session.run("MATCH (c:ScientificClaim) RETURN c AS node"):
                    payload = _node_payload(rec["node"])
                    if payload["id"]:
                        nodes_map[payload["id"]] = payload
                # 3) Только connected ScientificEntity.
                for rec in session.run(
                    "MATCH (e:ScientificEntity)<-[]-(:ScientificClaim) "
                    "RETURN DISTINCT e AS node"
                ):
                    payload = _node_payload(rec["node"])
                    if payload["id"]:
                        nodes_map[payload["id"]] = payload
                # 4) ResearchField.
                for rec in session.run(
                    "MATCH (f:ResearchField)<-[:BELONGS_TO_FIELD]-(:Publication) "
                    "RETURN DISTINCT f AS node"
                ):
                    payload = _node_payload(rec["node"])
                    if payload["id"]:
                        nodes_map[payload["id"]] = payload

                edges: list[dict[str, Any]] = []
                # 5) Лёгкие рёбра — CONTAINS_CLAIM, BELONGS_TO_FIELD, CITES,
                #    MENTIONS_ENTITY / EVALUATED_BY (их всего несколько сотен).
                for rec in session.run(
                    "MATCH (a)-[r:CONTAINS_CLAIM|BELONGS_TO_FIELD|CITES|MENTIONS_ENTITY|EVALUATED_BY]->(b) "
                    "RETURN a AS src, r AS rel, b AS tgt"
                ):
                    payload = _relationship_payload(rec["rel"], start_node=rec["src"], end_node=rec["tgt"])
                    if payload["source"] and payload["target"]:
                        edges.append(payload)
                # 6) Claim-relations с лимитом — берём top-N по weight.
                claim_rels_count = int(
                    session.run(
                        "MATCH ()-[r:SUPPORTS|CONTRADICTS|LIMITS|EXTENDS]->() RETURN count(r) AS c"
                    ).single()["c"]
                )
                for rec in session.run(
                    "MATCH (a:ScientificClaim)-[r:SUPPORTS|CONTRADICTS|LIMITS|EXTENDS]->(b:ScientificClaim) "
                    "RETURN a AS src, r AS rel, b AS tgt ORDER BY r.weight DESC LIMIT $lim",
                    lim=max_claim_relations,
                ):
                    payload = _relationship_payload(rec["rel"], start_node=rec["src"], end_node=rec["tgt"])
                    if payload["source"] and payload["target"]:
                        edges.append(payload)

                pub_count = int(session.run("MATCH (p:Publication) RETURN count(p) AS c").single()["c"])
                claim_count = int(session.run("MATCH (c:ScientificClaim) RETURN count(c) AS c").single()["c"])
                entity_count = int(
                    session.run(
                        "MATCH (e:ScientificEntity)<-[]-(:ScientificClaim) RETURN count(DISTINCT e) AS c"
                    ).single()["c"]
                )
                summary = {
                    "publications": pub_count,
                    "claims": claim_count,
                    "entities": entity_count,
                    "relations": claim_rels_count,
                    "total_edges": len(edges),
                    "claim_relations_truncated_to": max_claim_relations if claim_rels_count > max_claim_relations else None,
                }
                return {"nodes": list(nodes_map.values()), "edges": edges, "summary": summary}
        except Exception as exc:
            logger.warning("neo4j_query_full_graph_failed", extra={"error": str(exc)})
            return None

    def query_publication_subgraph(self, publication_id: str) -> dict[str, Any] | None:
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                nodes_map: dict[str, dict[str, Any]] = {}
                edges: list[dict[str, Any]] = []
                seen_edges: set[tuple[str, str, str]] = set()

                pub_record = session.run(
                    "MATCH (p:Publication {id: $pid}) RETURN p", pid=publication_id
                ).single()
                if not pub_record:
                    return None
                pub_payload = _node_payload(pub_record["p"])
                if pub_payload["id"]:
                    nodes_map[pub_payload["id"]] = pub_payload

                # 1) Прямые рёбра от публикации (CITES, BELONGS_TO_FIELD).
                for rec in session.run(
                    "MATCH (p:Publication {id: $pid})-[r:CITES|BELONGS_TO_FIELD]->(other) "
                    "RETURN p AS src, r AS rel, other AS tgt",
                    pid=publication_id,
                ):
                    other_payload = _node_payload(rec["tgt"])
                    if other_payload["id"]:
                        nodes_map[other_payload["id"]] = other_payload
                    edge = _relationship_payload(rec["rel"], start_node=rec["src"], end_node=rec["tgt"])
                    key = (edge["source"], edge["target"], edge["type"])
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges.append(edge)

                # 2) Claims, принадлежащие публикации.
                claims_recs = list(session.run(
                    "MATCH (p:Publication {id: $pid})-[r:CONTAINS_CLAIM]->(c:ScientificClaim) "
                    "RETURN p AS src, r AS rel, c AS claim",
                    pid=publication_id,
                ))
                claim_ids: list[str] = []
                for rec in claims_recs:
                    claim_payload = _node_payload(rec["claim"])
                    if claim_payload["id"]:
                        nodes_map[claim_payload["id"]] = claim_payload
                        claim_ids.append(claim_payload["id"])
                    edge = _relationship_payload(rec["rel"], start_node=rec["src"], end_node=rec["claim"])
                    key = (edge["source"], edge["target"], edge["type"])
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges.append(edge)

                if claim_ids:
                    # 3) Entity-связи для всех этих claims.
                    for rec in session.run(
                        "MATCH (c:ScientificClaim)-[r:MENTIONS_ENTITY|EVALUATED_BY]->(e:ScientificEntity) "
                        "WHERE c.id IN $ids "
                        "RETURN c AS src, r AS rel, e AS tgt",
                        ids=claim_ids,
                    ):
                        entity_payload = _node_payload(rec["tgt"])
                        if entity_payload["id"]:
                            nodes_map[entity_payload["id"]] = entity_payload
                        edge = _relationship_payload(rec["rel"], start_node=rec["src"], end_node=rec["tgt"])
                        key = (edge["source"], edge["target"], edge["type"])
                        if key not in seen_edges:
                            seen_edges.add(key)
                            edges.append(edge)
                    # 4) Claim-relations внутри публикации.
                    for rec in session.run(
                        "MATCH (a:ScientificClaim)-[r:SUPPORTS|CONTRADICTS|LIMITS|EXTENDS]->(b:ScientificClaim) "
                        "WHERE a.id IN $ids AND b.id IN $ids "
                        "RETURN a AS src, r AS rel, b AS tgt",
                        ids=claim_ids,
                    ):
                        edge = _relationship_payload(rec["rel"], start_node=rec["src"], end_node=rec["tgt"])
                        key = (edge["source"], edge["target"], edge["type"])
                        if key not in seen_edges:
                            seen_edges.add(key)
                            edges.append(edge)

                return {"nodes": list(nodes_map.values()), "edges": edges, "root": publication_id}
        except Exception as exc:
            logger.warning("neo4j_query_pub_subgraph_failed", extra={"error": str(exc)})
            return None

    def query_entity_subgraph(self, entity_id: str, *, depth: int = 2) -> dict[str, Any] | None:
        if not self._connected:
            return None
        depth = max(1, min(int(depth), 3))
        try:
            with self._driver.session() as session:
                nodes_map: dict[str, dict[str, Any]] = {}
                edges: list[dict[str, Any]] = []
                seen_edges: set[tuple[str, str, str]] = set()

                root_rec = session.run(
                    "MATCH (e:ScientificEntity {id: $eid}) RETURN e", eid=entity_id
                ).single()
                if not root_rec:
                    return None
                root_payload = _node_payload(root_rec["e"])
                if root_payload["id"]:
                    nodes_map[root_payload["id"]] = root_payload

                # claims, упоминающие entity
                for rec in session.run(
                    "MATCH (c:ScientificClaim)-[r:MENTIONS_ENTITY|EVALUATED_BY]->(e:ScientificEntity {id: $eid}) "
                    "RETURN c AS src, r AS rel, e AS tgt",
                    eid=entity_id,
                ):
                    claim_payload = _node_payload(rec["src"])
                    if claim_payload["id"]:
                        nodes_map[claim_payload["id"]] = claim_payload
                    edge = _relationship_payload(rec["rel"], start_node=rec["src"], end_node=rec["tgt"])
                    key = (edge["source"], edge["target"], edge["type"])
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges.append(edge)

                if depth >= 2 and nodes_map:
                    related_claim_ids = [nid for nid, payload in nodes_map.items() if payload["kind"] == "ScientificClaim"]
                    if related_claim_ids:
                        for rec in session.run(
                            "MATCH (a:ScientificClaim)-[r:SUPPORTS|CONTRADICTS|LIMITS|EXTENDS]->(b:ScientificClaim) "
                            "WHERE a.id IN $ids OR b.id IN $ids "
                            "RETURN a AS src, r AS rel, b AS tgt LIMIT 300",
                            ids=related_claim_ids,
                        ):
                            for n_field in ("src", "tgt"):
                                payload = _node_payload(rec[n_field])
                                if payload["id"] and payload["id"] not in nodes_map:
                                    nodes_map[payload["id"]] = payload
                            edge = _relationship_payload(rec["rel"], start_node=rec["src"], end_node=rec["tgt"])
                            key = (edge["source"], edge["target"], edge["type"])
                            if key not in seen_edges:
                                seen_edges.add(key)
                                edges.append(edge)

                return {"nodes": list(nodes_map.values()), "edges": edges, "root": entity_id}
        except Exception as exc:
            logger.warning("neo4j_query_entity_subgraph_failed", extra={"error": str(exc)})
            return None

    def query_claim_subgraph(self, claim_id: str, *, depth: int = 2) -> dict[str, Any] | None:
        if not self._connected:
            return None
        depth = max(1, min(int(depth), 3))
        try:
            with self._driver.session() as session:
                nodes_map: dict[str, dict[str, Any]] = {}
                edges: list[dict[str, Any]] = []
                seen_edges: set[tuple[str, str, str]] = set()

                root_rec = session.run(
                    "MATCH (c:ScientificClaim {id: $cid}) RETURN c", cid=claim_id
                ).single()
                if not root_rec:
                    return None
                root_payload = _node_payload(root_rec["c"])
                if root_payload["id"]:
                    nodes_map[root_payload["id"]] = root_payload

                # 1) Publication, владеющая claim'ом
                for rec in session.run(
                    "MATCH (p:Publication)-[r:CONTAINS_CLAIM]->(c:ScientificClaim {id: $cid}) "
                    "RETURN p AS src, r AS rel, c AS tgt",
                    cid=claim_id,
                ):
                    pub_payload = _node_payload(rec["src"])
                    if pub_payload["id"]:
                        nodes_map[pub_payload["id"]] = pub_payload
                    edge = _relationship_payload(rec["rel"], start_node=rec["src"], end_node=rec["tgt"])
                    key = (edge["source"], edge["target"], edge["type"])
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges.append(edge)

                # 2) Entity-связи
                for rec in session.run(
                    "MATCH (c:ScientificClaim {id: $cid})-[r:MENTIONS_ENTITY|EVALUATED_BY]->(e:ScientificEntity) "
                    "RETURN c AS src, r AS rel, e AS tgt",
                    cid=claim_id,
                ):
                    entity_payload = _node_payload(rec["tgt"])
                    if entity_payload["id"]:
                        nodes_map[entity_payload["id"]] = entity_payload
                    edge = _relationship_payload(rec["rel"], start_node=rec["src"], end_node=rec["tgt"])
                    key = (edge["source"], edge["target"], edge["type"])
                    if key not in seen_edges:
                        seen_edges.add(key)
                        edges.append(edge)

                # 3) Claim ↔ Claim связи на N хопов
                cypher = f"""
                    MATCH path = (c:ScientificClaim {{id: $cid}})-[:SUPPORTS|CONTRADICTS|LIMITS|EXTENDS*1..{depth}]-(other:ScientificClaim)
                    RETURN relationships(path) AS rels, nodes(path) AS nds LIMIT 200
                """
                for rec in session.run(cypher, cid=claim_id):
                    for node in rec["nds"] or []:
                        payload = _node_payload(node)
                        if payload["id"] and payload["id"] not in nodes_map:
                            nodes_map[payload["id"]] = payload
                    for rel in rec["rels"] or []:
                        edge = _relationship_payload(rel)
                        # Если start/end не пришли из path, попробуем достать из имён node-ов
                        if not edge["source"] or not edge["target"]:
                            continue
                        key = (edge["source"], edge["target"], edge["type"])
                        if key not in seen_edges:
                            seen_edges.add(key)
                            edges.append(edge)

                return {"nodes": list(nodes_map.values()), "edges": edges, "root": claim_id}
        except Exception as exc:
            logger.warning("neo4j_query_claim_subgraph_failed", extra={"error": str(exc)})
            return None

    # ------------------------------------------------------------------
    # DocumentChunk as graph node (Neo4j-as-source-of-truth)
    # ------------------------------------------------------------------

    def upsert_chunks(self, chunks: Iterable[Any], *, publication: Any | None = None) -> None:
        if not self._connected:
            return
        try:
            with self._driver.session() as session:
                for chunk in chunks:
                    session.run(
                        """
                        MERGE (c:DocumentChunk {id: $id})
                        SET c.publication_id = $pub_id,
                            c.chunk_index = $idx,
                            c.section = $section,
                            c.page_start = $ps,
                            c.page_end = $pe,
                            c.text = $text,
                            c.content_hash = $hash,
                            c.embedding_provider = $emb_provider
                        """,
                        id=chunk.id,
                        pub_id=chunk.publication_id,
                        idx=chunk.chunk_index,
                        section=chunk.section,
                        ps=chunk.page_start,
                        pe=chunk.page_end,
                        text=chunk.text,
                        hash=(chunk.metadata or {}).get("content_hash", chunk.id),
                        emb_provider=(chunk.metadata or {}).get("embedding_provider", "deterministic"),
                    ).consume()
                    session.run(
                        """
                        MATCH (p:Publication {id: $pub_id})
                        MATCH (c:DocumentChunk {id: $chunk_id})
                        MERGE (p)-[:CONTAINS_CHUNK]->(c)
                        """,
                        pub_id=chunk.publication_id,
                        chunk_id=chunk.id,
                    ).consume()
        except Exception as exc:
            logger.debug("neo4j_upsert_chunks_failed", extra={"error": str(exc)})

    # ------------------------------------------------------------------
    # Mutations on existing nodes
    # ------------------------------------------------------------------

    def update_publication_properties(self, publication_id: str, props: dict[str, Any]) -> None:
        if not self._connected or not props:
            return
        try:
            with self._driver.session() as session:
                session.run(
                    "MATCH (p:Publication {id: $id}) SET p += $props",
                    id=publication_id,
                    props=props,
                ).consume()
        except Exception as exc:
            logger.debug("neo4j_update_publication_failed", extra={"error": str(exc)})

    def update_claim_properties(self, claim_id: str, props: dict[str, Any]) -> None:
        if not self._connected or not props:
            return
        try:
            with self._driver.session() as session:
                session.run(
                    "MATCH (c:ScientificClaim {id: $id}) SET c += $props",
                    id=claim_id,
                    props=props,
                ).consume()
        except Exception as exc:
            logger.debug("neo4j_update_claim_failed", extra={"error": str(exc)})

    def increment_claim_score(self, claim_id: str, *, confidence_delta: float = 0.0, evidence_delta: float = 0.0) -> dict[str, Any] | None:
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                rec = session.run(
                    """
                    MATCH (c:ScientificClaim {id: $id})
                    SET c.confidence_score = CASE
                            WHEN c.confidence_score + $cd < 0.05 THEN 0.05
                            WHEN c.confidence_score + $cd > 1.0 THEN 1.0
                            ELSE c.confidence_score + $cd
                          END,
                        c.evidence_strength = CASE
                            WHEN c.evidence_strength + $ed < 0.05 THEN 0.05
                            WHEN c.evidence_strength + $ed > 1.0 THEN 1.0
                            ELSE c.evidence_strength + $ed
                          END
                    RETURN c.confidence_score AS confidence_score, c.evidence_strength AS evidence_strength
                    """,
                    id=claim_id, cd=confidence_delta, ed=evidence_delta,
                ).single()
                if rec is None:
                    return None
                return {"confidence_score": float(rec["confidence_score"]), "evidence_strength": float(rec["evidence_strength"])}
        except Exception as exc:
            logger.debug("neo4j_increment_claim_failed", extra={"error": str(exc)})
            return None

    def increment_supports_weights(self, claim_id: str, delta: float) -> None:
        if not self._connected:
            return
        try:
            with self._driver.session() as session:
                session.run(
                    """
                    MATCH (c:ScientificClaim {id: $id})-[r:SUPPORTS]-(:ScientificClaim)
                    SET r.weight = CASE
                        WHEN r.weight + $d < 0.05 THEN 0.05
                        WHEN r.weight + $d > 1.0 THEN 1.0
                        ELSE r.weight + $d
                      END
                    """,
                    id=claim_id, d=delta,
                ).consume()
        except Exception as exc:
            logger.debug("neo4j_increment_supports_failed", extra={"error": str(exc)})

    def delete_publication(self, publication_id: str) -> dict[str, int] | None:
        """Каскадно удаляет публикацию, её chunks/claims и связанные рёбра."""
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                counts = session.run(
                    """
                    OPTIONAL MATCH (p:Publication {id: $pid})-[:CONTAINS_CHUNK]->(ch:DocumentChunk)
                    WITH p, count(DISTINCT ch) AS chunks
                    OPTIONAL MATCH (p)-[:CONTAINS_CLAIM]->(c:ScientificClaim)
                    WITH p, chunks, count(DISTINCT c) AS claims
                    OPTIONAL MATCH (p)-[:CONTAINS_CHUNK]->(ch2:DocumentChunk)
                    DETACH DELETE ch2
                    WITH p, chunks, claims
                    OPTIONAL MATCH (p)-[:CONTAINS_CLAIM]->(c2:ScientificClaim)
                    DETACH DELETE c2
                    WITH p, chunks, claims
                    DETACH DELETE p
                    RETURN chunks, claims
                    """,
                    pid=publication_id,
                ).single()
                if counts is None:
                    return {"chunks": 0, "claims": 0}
                return {"chunks": int(counts["chunks"] or 0), "claims": int(counts["claims"] or 0)}
        except Exception as exc:
            logger.debug("neo4j_delete_publication_failed", extra={"error": str(exc)})
            return None

    def delete_claim(self, claim_id: str) -> bool:
        if not self._connected:
            return False
        try:
            with self._driver.session() as session:
                rec = session.run(
                    "MATCH (c:ScientificClaim {id: $id}) DETACH DELETE c RETURN count(c) AS removed",
                    id=claim_id,
                ).single()
                return bool(rec and rec["removed"])
        except Exception as exc:
            logger.debug("neo4j_delete_claim_failed", extra={"error": str(exc)})
            return False

    # ------------------------------------------------------------------
    # Read API — list / detail запросы для всех scientific endpoints
    # ------------------------------------------------------------------

    def list_publications(
        self,
        *,
        research_field: str | None = None,
        status: str | None = None,
        year: int | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]] | None:
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                clauses: list[str] = []
                params: dict[str, Any] = {}
                if research_field:
                    clauses.append("p.research_field = $research_field")
                    params["research_field"] = research_field
                if status:
                    clauses.append("p.status = $status")
                    params["status"] = status
                if year:
                    clauses.append("p.year = $year")
                    params["year"] = year
                if search:
                    clauses.append("toLower(p.title) CONTAINS toLower($search) OR toLower(coalesce(p.abstract, '')) CONTAINS toLower($search)")
                    params["search"] = search
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
                query = f"MATCH (p:Publication) {where} RETURN p ORDER BY p.year DESC, p.title ASC"
                rows = session.run(query, **params)
                return [_publication_payload(rec["p"]) for rec in rows]
        except Exception as exc:
            logger.debug("neo4j_list_publications_failed", extra={"error": str(exc)})
            return None

    def get_publication_detail(self, publication_id: str) -> dict[str, Any] | None:
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                pub_rec = session.run(
                    "MATCH (p:Publication {id: $id}) RETURN p", id=publication_id
                ).single()
                if pub_rec is None:
                    return None
                publication = _publication_payload(pub_rec["p"])
                chunks_rows = session.run(
                    "MATCH (p:Publication {id: $id})-[:CONTAINS_CHUNK]->(c:DocumentChunk) "
                    "RETURN c ORDER BY c.chunk_index",
                    id=publication_id,
                )
                chunks = [_chunk_payload(rec["c"]) for rec in chunks_rows]
                claims_rows = session.run(
                    "MATCH (p:Publication {id: $id})-[:CONTAINS_CLAIM]->(c:ScientificClaim) "
                    "RETURN c ORDER BY c.evidence_strength DESC",
                    id=publication_id,
                )
                claims = [_claim_payload(rec["c"]) for rec in claims_rows]
                entities_rows = session.run(
                    "MATCH (p:Publication {id: $id})-[:CONTAINS_CLAIM]->(:ScientificClaim)-[:MENTIONS_ENTITY|EVALUATED_BY]->(e:ScientificEntity) "
                    "RETURN DISTINCT e",
                    id=publication_id,
                )
                entities = [_entity_payload(rec["e"]) for rec in entities_rows]
                citations_rows = session.run(
                    "MATCH (p:Publication {id: $id})-[r:CITES]->(t:Publication) "
                    "RETURN t.id AS target_id, t.title AS target_title, r.context AS context",
                    id=publication_id,
                )
                citations = [
                    {
                        "source_publication_id": publication_id,
                        "target_publication_id": rec["target_id"],
                        "target_title": rec["target_title"],
                        "context": rec["context"],
                    }
                    for rec in citations_rows
                ]
                return {
                    "publication": publication,
                    "chunks": chunks,
                    "claims": claims,
                    "entities": entities,
                    "jobs": [],  # jobs хранятся в PG, добавляются отдельно в API-слое
                    "citations": citations,
                }
        except Exception as exc:
            logger.debug("neo4j_get_publication_detail_failed", extra={"error": str(exc)})
            return None

    def list_chunks_by_publication(self, publication_id: str) -> list[dict[str, Any]] | None:
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                rows = session.run(
                    "MATCH (p:Publication {id: $id})-[:CONTAINS_CHUNK]->(c:DocumentChunk) "
                    "RETURN c ORDER BY c.chunk_index",
                    id=publication_id,
                )
                return [_chunk_payload(rec["c"]) for rec in rows]
        except Exception as exc:
            logger.debug("neo4j_list_chunks_failed", extra={"error": str(exc)})
            return None

    # ------------------------------------------------------------------
    # Batch fetch by ids (используются search.py / rag.py при cache-miss
    # in-memory копии — критично для Neo4j-first архитектуры).
    # ------------------------------------------------------------------

    def fetch_chunks_by_ids(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        if not self._connected or not ids:
            return {}
        try:
            with self._driver.session() as session:
                rows = session.run(
                    "MATCH (c:DocumentChunk) WHERE c.id IN $ids RETURN c",
                    ids=list(ids),
                )
                result: dict[str, dict[str, Any]] = {}
                for rec in rows:
                    payload = _chunk_payload(rec["c"])
                    if payload.get("id"):
                        result[payload["id"]] = payload
                return result
        except Exception as exc:
            logger.debug("neo4j_fetch_chunks_by_ids_failed", extra={"error": str(exc)})
            return {}

    def fetch_claims_by_ids(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        if not self._connected or not ids:
            return {}
        try:
            with self._driver.session() as session:
                rows = session.run(
                    "MATCH (c:ScientificClaim) WHERE c.id IN $ids RETURN c",
                    ids=list(ids),
                )
                result: dict[str, dict[str, Any]] = {}
                for rec in rows:
                    payload = _claim_payload(rec["c"])
                    if payload.get("id"):
                        result[payload["id"]] = payload
                return result
        except Exception as exc:
            logger.debug("neo4j_fetch_claims_by_ids_failed", extra={"error": str(exc)})
            return {}

    def fetch_entities_by_ids(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        if not self._connected or not ids:
            return {}
        try:
            with self._driver.session() as session:
                rows = session.run(
                    "MATCH (e:ScientificEntity) WHERE e.id IN $ids RETURN e",
                    ids=list(ids),
                )
                result: dict[str, dict[str, Any]] = {}
                for rec in rows:
                    payload = _entity_payload(rec["e"])
                    if payload.get("id"):
                        result[payload["id"]] = payload
                return result
        except Exception as exc:
            logger.debug("neo4j_fetch_entities_by_ids_failed", extra={"error": str(exc)})
            return {}

    def fetch_publications_by_ids(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        if not self._connected or not ids:
            return {}
        try:
            with self._driver.session() as session:
                rows = session.run(
                    "MATCH (p:Publication) WHERE p.id IN $ids RETURN p",
                    ids=list(ids),
                )
                result: dict[str, dict[str, Any]] = {}
                for rec in rows:
                    payload = _publication_payload(rec["p"])
                    if payload.get("id"):
                        result[payload["id"]] = payload
                return result
        except Exception as exc:
            logger.debug("neo4j_fetch_publications_by_ids_failed", extra={"error": str(exc)})
            return {}

    def list_entities(
        self,
        *,
        entity_type: str | None = None,
        search: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]] | None:
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                clauses: list[str] = []
                params: dict[str, Any] = {"limit": limit}
                if entity_type:
                    clauses.append("e.entity_type = $entity_type")
                    params["entity_type"] = entity_type
                if search:
                    clauses.append(
                        "toLower(e.canonical_name) CONTAINS toLower($search) OR ANY(a IN e.aliases WHERE toLower(a) CONTAINS toLower($search))"
                    )
                    params["search"] = search
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
                query = (
                    f"MATCH (e:ScientificEntity) {where} "
                    "RETURN e ORDER BY e.entity_type, e.canonical_name LIMIT $limit"
                )
                rows = session.run(query, **params)
                return [_entity_payload(rec["e"]) for rec in rows]
        except Exception as exc:
            logger.debug("neo4j_list_entities_failed", extra={"error": str(exc)})
            return None

    def get_entity_detail(self, entity_id: str) -> dict[str, Any] | None:
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                rec = session.run(
                    "MATCH (e:ScientificEntity {id: $id}) RETURN e", id=entity_id
                ).single()
                if rec is None:
                    return None
                entity = _entity_payload(rec["e"])
                claims_rows = session.run(
                    "MATCH (c:ScientificClaim)-[:MENTIONS_ENTITY|EVALUATED_BY]->(e:ScientificEntity {id: $id}) "
                    "RETURN c ORDER BY c.evidence_strength DESC",
                    id=entity_id,
                )
                claims = [_claim_payload(rec["c"]) for rec in claims_rows]
                pub_rows = session.run(
                    "MATCH (p:Publication)-[:CONTAINS_CLAIM]->(:ScientificClaim)-[:MENTIONS_ENTITY|EVALUATED_BY]->(e:ScientificEntity {id: $id}) "
                    "RETURN DISTINCT p",
                    id=entity_id,
                )
                publications = [_publication_payload(rec["p"]) for rec in pub_rows]
                return {"entity": entity, "claims": claims, "publications": publications}
        except Exception as exc:
            logger.debug("neo4j_get_entity_detail_failed", extra={"error": str(exc)})
            return None

    def list_claims(
        self,
        *,
        publication_id: str | None = None,
        claim_type: str | None = None,
        min_confidence: float = 0.0,
        min_evidence_strength: float = 0.0,
        limit: int = 200,
    ) -> list[dict[str, Any]] | None:
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                clauses: list[str] = []
                params: dict[str, Any] = {"limit": limit}
                if publication_id:
                    clauses.append("c.publication_id = $publication_id")
                    params["publication_id"] = publication_id
                if claim_type:
                    clauses.append("c.claim_type = $claim_type")
                    params["claim_type"] = claim_type
                if min_confidence:
                    clauses.append("c.confidence_score >= $min_confidence")
                    params["min_confidence"] = min_confidence
                if min_evidence_strength:
                    clauses.append("c.evidence_strength >= $min_evidence_strength")
                    params["min_evidence_strength"] = min_evidence_strength
                where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
                query = (
                    f"MATCH (c:ScientificClaim) {where} "
                    "RETURN c ORDER BY c.evidence_strength DESC LIMIT $limit"
                )
                rows = session.run(query, **params)
                return [_claim_payload(rec["c"]) for rec in rows]
        except Exception as exc:
            logger.debug("neo4j_list_claims_failed", extra={"error": str(exc)})
            return None

    def get_claim_detail(self, claim_id: str) -> dict[str, Any] | None:
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                rec = session.run(
                    "MATCH (c:ScientificClaim {id: $id}) RETURN c", id=claim_id
                ).single()
                if rec is None:
                    return None
                claim = _claim_payload(rec["c"])
                rel_rows = session.run(
                    """
                    MATCH (a:ScientificClaim {id: $id})-[r:SUPPORTS|CONTRADICTS|LIMITS|EXTENDS]-(b:ScientificClaim)
                    RETURN startNode(r).id AS src, endNode(r).id AS tgt, type(r) AS rel_type,
                           r.weight AS weight, r.confidence_score AS confidence_score,
                           r.evidence_strength AS evidence_strength, r.rationale AS rationale
                    """,
                    id=claim_id,
                )
                relations = []
                for rec_r in rel_rows:
                    relations.append(
                        {
                            "source_claim_id": rec_r["src"],
                            "target_claim_id": rec_r["tgt"],
                            "relation_type": (rec_r["rel_type"] or "").lower(),
                            "weight": rec_r["weight"],
                            "confidence_score": rec_r["confidence_score"],
                            "evidence_strength": rec_r["evidence_strength"],
                            "rationale": rec_r["rationale"],
                        }
                    )
                related_rows = session.run(
                    "MATCH (a:ScientificClaim {id: $id})-[:SUPPORTS|CONTRADICTS|LIMITS|EXTENDS]-(b:ScientificClaim) "
                    "RETURN DISTINCT b",
                    id=claim_id,
                )
                related_claims = [_claim_payload(rec_b["b"]) for rec_b in related_rows]
                return {"claim": claim, "relations": relations, "related_claims": related_claims}
        except Exception as exc:
            logger.debug("neo4j_get_claim_detail_failed", extra={"error": str(exc)})
            return None

    def get_claim_evidence(self, claim_id: str) -> dict[str, Any] | None:
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                rec = session.run(
                    """
                    MATCH (c:ScientificClaim {id: $id})
                    OPTIONAL MATCH (c)<-[:CONTAINS_CLAIM]-(p:Publication)
                    OPTIONAL MATCH (chunk:DocumentChunk {id: c.chunk_id})
                    RETURN c, p, chunk
                    """,
                    id=claim_id,
                ).single()
                if rec is None:
                    return None
                claim = _claim_payload(rec["c"])
                publication = _publication_payload(rec["p"]) if rec["p"] else None
                chunk = _chunk_payload(rec["chunk"]) if rec["chunk"] else None
                return {
                    "claim": claim,
                    "chunk": chunk,
                    "publication": publication,
                    "evidence_text": claim.get("evidence_text"),
                    "pages": [claim.get("page_start", 1), claim.get("page_end", 1)],
                    "evidence_strength": claim.get("evidence_strength", 0.0),
                    "source_reliability": claim.get("source_reliability", 0.0),
                }
        except Exception as exc:
            logger.debug("neo4j_get_claim_evidence_failed", extra={"error": str(exc)})
            return None

    def list_relations(self, *, relation_type: str | None = None, limit: int = 500) -> list[dict[str, Any]] | None:
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                if relation_type:
                    label = relation_type.upper()
                    query = (
                        f"MATCH (a:ScientificClaim)-[r:{label}]->(b:ScientificClaim) "
                        "RETURN a.id AS src, type(r) AS rel_type, b.id AS tgt, "
                        "r.weight AS weight, r.confidence_score AS conf, r.evidence_strength AS ev, "
                        "r.rationale AS rationale ORDER BY r.weight DESC LIMIT $limit"
                    )
                else:
                    query = (
                        "MATCH (a:ScientificClaim)-[r:SUPPORTS|CONTRADICTS|LIMITS|EXTENDS]->(b:ScientificClaim) "
                        "RETURN a.id AS src, type(r) AS rel_type, b.id AS tgt, "
                        "r.weight AS weight, r.confidence_score AS conf, r.evidence_strength AS ev, "
                        "r.rationale AS rationale ORDER BY r.weight DESC LIMIT $limit"
                    )
                rows = session.run(query, limit=limit)
                return [
                    {
                        "source_claim_id": rec["src"],
                        "target_claim_id": rec["tgt"],
                        "relation_type": (rec["rel_type"] or "").lower(),
                        "weight": rec["weight"],
                        "confidence_score": rec["conf"],
                        "evidence_strength": rec["ev"],
                        "rationale": rec["rationale"],
                    }
                    for rec in rows
                ]
        except Exception as exc:
            logger.debug("neo4j_list_relations_failed", extra={"error": str(exc)})
            return None

    def list_authors(self) -> list[dict[str, Any]] | None:
        """Авторы и организации лежат как поля Publication.authors / organizations.
        Возвращаем уникальные записи."""
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                rows = session.run("MATCH (p:Publication) RETURN p.authors AS authors, p.organizations AS orgs")
                authors: set[str] = set()
                orgs: set[str] = set()
                for rec in rows:
                    for a in rec["authors"] or []:
                        authors.add(a)
                    for o in rec["orgs"] or []:
                        orgs.add(o)
                return [{"name": a} for a in sorted(authors)] + [{"organization": o} for o in sorted(orgs)]
        except Exception as exc:
            logger.debug("neo4j_list_authors_failed", extra={"error": str(exc)})
            return None

    def count_summary(self) -> dict[str, int] | None:
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                pub_count = int(session.run("MATCH (p:Publication) RETURN count(p) AS c").single()["c"])
                chunk_count = int(session.run("MATCH (c:DocumentChunk) RETURN count(c) AS c").single()["c"])
                entity_count = int(session.run("MATCH (e:ScientificEntity) RETURN count(e) AS c").single()["c"])
                claim_count = int(session.run("MATCH (c:ScientificClaim) RETURN count(c) AS c").single()["c"])
                rel_count = int(session.run(
                    "MATCH ()-[r:SUPPORTS|CONTRADICTS|LIMITS|EXTENDS]->() RETURN count(r) AS c"
                ).single()["c"])
                cite_count = int(session.run(
                    "MATCH ()-[r:CITES]->() RETURN count(r) AS c"
                ).single()["c"])
                return {
                    "publications": pub_count,
                    "chunks": chunk_count,
                    "entities": entity_count,
                    "claims": claim_count,
                    "relations": rel_count,
                    "citations": cite_count,
                }
        except Exception as exc:
            logger.debug("neo4j_count_summary_failed", extra={"error": str(exc)})
            return None

    def fetch_full_state(self) -> dict[str, list[Any]] | None:
        """Возвращает полное содержимое графа для bootstrap'а in-memory кэша.
        Используется при холодном старте, если граф уже наполнен."""
        if not self._connected:
            return None
        try:
            with self._driver.session() as session:
                pubs = [
                    _publication_payload(rec["p"])
                    for rec in session.run("MATCH (p:Publication) RETURN p")
                ]
                chunks = [
                    _chunk_payload(rec["c"])
                    for rec in session.run("MATCH (c:DocumentChunk) RETURN c")
                ]
                entities = [
                    _entity_payload(rec["e"])
                    for rec in session.run("MATCH (e:ScientificEntity) RETURN e")
                ]
                claims = [
                    _claim_payload(rec["c"])
                    for rec in session.run("MATCH (c:ScientificClaim) RETURN c")
                ]
                relations = []
                for rec in session.run(
                    "MATCH (a:ScientificClaim)-[r:SUPPORTS|CONTRADICTS|LIMITS|EXTENDS]->(b:ScientificClaim) "
                    "RETURN a.id AS src, type(r) AS rel_type, b.id AS tgt, "
                    "r.weight AS weight, r.confidence_score AS conf, r.evidence_strength AS ev, "
                    "r.source_reliability AS src_r, r.rationale AS rationale"
                ):
                    relations.append(
                        {
                            "source_claim_id": rec["src"],
                            "target_claim_id": rec["tgt"],
                            "relation_type": (rec["rel_type"] or "").lower(),
                            "weight": rec["weight"],
                            "confidence_score": rec["conf"],
                            "evidence_strength": rec["ev"],
                            "source_reliability": rec["src_r"],
                            "rationale": rec["rationale"],
                        }
                    )
                citations = [
                    {
                        "source_publication_id": rec["src"],
                        "target_publication_id": rec["tgt"],
                        "context": rec["ctx"],
                    }
                    for rec in session.run(
                        "MATCH (a:Publication)-[r:CITES]->(b:Publication) "
                        "RETURN a.id AS src, b.id AS tgt, r.context AS ctx"
                    )
                ]
                return {
                    "publications": pubs,
                    "chunks": chunks,
                    "entities": entities,
                    "claims": claims,
                    "relations": relations,
                    "citations": citations,
                }
        except Exception as exc:
            logger.debug("neo4j_fetch_full_state_failed", extra={"error": str(exc)})
            return None

    # ------------------------------------------------------------------
    # No-op hooks (записываются в PG/pgvector, не в Neo4j).
    # ------------------------------------------------------------------

    def upsert_job(self, job: Any, *, publication: Any | None = None) -> None:
        return

    def upsert_step(self, job: Any, step: Any) -> None:
        return

    def upsert_rag_answer(self, rag: Any) -> None:
        return

    def upsert_evaluation(self, record: Any) -> None:
        return

    def upsert_feedback_event(self, event: Any) -> None:
        return

    def upsert_review_item(self, item: dict[str, Any]) -> None:
        return

    def cache_activation(self, publication_id: str, keys: list[str]) -> None:
        return

    def close(self) -> None:
        if self._driver:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None
            self._connected = False


# ---------------------------------------------------------------------------
# Payload conversion helpers (Neo4j Node → frontend-friendly dict)
# ---------------------------------------------------------------------------


def _publication_payload(node: Any) -> dict[str, Any]:
    if node is None:
        return {}
    props = dict(node)
    return {
        "id": props.get("id") or "",
        "title": props.get("title") or "",
        "abstract": props.get("abstract") or "",
        "source_type": props.get("source_type") or "text",
        "authors": list(props.get("authors") or []),
        "year": props.get("year") or 2026,
        "status": props.get("status") or "ready",
        "pages": props.get("pages") or 1,
        "metadata": {
            "research_field": props.get("research_field"),
            "organizations": list(props.get("organizations") or []),
        },
    }


def _chunk_payload(node: Any) -> dict[str, Any]:
    if node is None:
        return {}
    props = dict(node)
    return {
        "id": props.get("id") or "",
        "publication_id": props.get("publication_id") or "",
        "chunk_index": props.get("chunk_index") or 0,
        "section": props.get("section") or "Body",
        "page_start": props.get("page_start") or 1,
        "page_end": props.get("page_end") or 1,
        "text": props.get("text") or "",
        "metadata": {
            "content_hash": props.get("content_hash"),
            "embedding_provider": props.get("embedding_provider"),
        },
    }


def _entity_payload(node: Any) -> dict[str, Any]:
    if node is None:
        return {}
    props = dict(node)
    return {
        "id": props.get("id") or "",
        "canonical_name": props.get("canonical_name") or "",
        "entity_type": props.get("entity_type") or "Method",
        "aliases": list(props.get("aliases") or []),
        "mentions": [],
        "confidence_score": float(props.get("confidence_score") or 0.7),
    }


def _claim_payload(node: Any) -> dict[str, Any]:
    if node is None:
        return {}
    props = dict(node)
    return {
        "id": props.get("id") or "",
        "publication_id": props.get("publication_id") or "",
        "chunk_id": props.get("chunk_id") or "",
        "extraction_run_id": props.get("extraction_run_id") or "",
        "claim_text": props.get("claim_text") or "",
        "claim_type": props.get("claim_type") or "method_description",
        "subject_entity": props.get("subject_entity") or "",
        "predicate": props.get("predicate") or "",
        "object_entity": props.get("object_entity") or "",
        "comparison_target": props.get("comparison_target"),
        "condition": props.get("condition"),
        "metric": props.get("metric"),
        "value": props.get("value"),
        "evidence_text": props.get("evidence_text") or props.get("claim_text") or "",
        "page_start": props.get("page_start") or 1,
        "page_end": props.get("page_end") or 1,
        "confidence_score": float(props.get("confidence_score") or 0.7),
        "evidence_strength": float(props.get("evidence_strength") or 0.7),
        "source_reliability": float(props.get("source_reliability") or 0.7),
    }


