from app.features.scientific_kb import ScientificKnowledgeBase


def test_demo_corpus_builds_claims_and_activation_index():
    kb = ScientificKnowledgeBase()

    summary = kb.summary()

    # Компактный демо-корпус: 20 русскоязычных статей в 5 тематических кластерах.
    assert summary["publications"] >= 18
    assert summary["chunks"] >= 50
    assert summary["entities"] >= 10
    assert summary["claims"] >= 30
    assert summary["activation_keys"] >= 20


def test_hybrid_search_returns_score_breakdown():
    kb = ScientificKnowledgeBase()

    hits = kb.search_hybrid("двоичный поиск", top_k=5)

    assert hits
    assert hits[0].score > 0
    assert "evidence_strength" in hits[0].score_breakdown
    assert any(key in hits[0].score_breakdown for key in ("keyword", "semantic", "graph", "activation"))


def test_graph_all_contains_publications_claims_entities_and_edges():
    kb = ScientificKnowledgeBase()

    graph = kb.graph_all()
    kinds = {node["kind"] for node in graph["nodes"]}
    node_ids = {node["id"] for node in graph["nodes"]}
    connected_ids = {edge["source"] for edge in graph["edges"]} | {edge["target"] for edge in graph["edges"]}

    assert "Publication" in kinds
    assert "ScientificClaim" in kinds
    assert graph["summary"]["entities"] >= 10
    assert len(graph["edges"]) >= graph["summary"]["claims"]
    assert node_ids <= connected_ids
    assert all(isinstance(edge.get("weight"), float) for edge in graph["edges"])
    assert min(edge["weight"] for edge in graph["edges"]) > 0
    assert max(edge["weight"] for edge in graph["edges"]) <= 1


def test_graph_all_is_dag_for_demo_corpus():
    kb = ScientificKnowledgeBase()

    graph = kb.graph_all()
    node_ids = {node["id"] for node in graph["nodes"]}
    adjacency = {node_id: [] for node_id in node_ids}
    indegree = {node_id: 0 for node_id in node_ids}
    for edge in graph["edges"]:
        adjacency[edge["source"]].append(edge["target"])
        indegree[edge["target"]] += 1

    queue = [node_id for node_id, count in indegree.items() if count == 0]
    seen = 0
    while queue:
        node_id = queue.pop()
        seen += 1
        for target in adjacency[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    assert seen == len(node_ids)


def test_rag_answer_is_grounded_and_evaluable():
    kb = ScientificKnowledgeBase()

    answer = kb.ask_with_evidence("что такое двоичный поиск и как он работает?", top_k=6)
    evaluation = kb.evaluate_rag_answer(answer.id)

    assert answer.status == "answered"
    assert answer.sources
    assert answer.used_claims
    assert "evidence_builder" in answer.reasoning_trace
    assert evaluation.metrics["faithfulness"] >= 0.7
    assert evaluation.feedback_events_created


def test_rag_refuses_when_evidence_is_missing():
    kb = ScientificKnowledgeBase()

    # Запрос полностью вне домена корпуса (мифология / поп-культура).
    answer = kb.ask_with_evidence("кто такой Зевс?", top_k=4)

    assert answer.status == "insufficient_evidence"
    assert answer.confidence_score <= 0.45
