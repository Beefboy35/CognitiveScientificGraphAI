from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .feedback_service import ScientificFeedbackMixin
from .models import EvaluationRecord, FeedbackEvent, RagAnswer
from .utils import _id


class ScientificRagMixin(ScientificFeedbackMixin):
    def ask_with_evidence(
        self,
        question: str,
        top_k: int = 6,
        language: str = "ru",
    ) -> RagAnswer:
        package = self.build_evidence(question, top_k)
        evidence = package["evidence"]
        coverage = package["coverage"]
        strong = [item for item in evidence if item["score"] >= 0.20]
        contradictions = [item for item in strong if item.get("contradiction_risk", 0.0) > 0.30]

        self.user_queries[_id("q")] = {
            "question": question,
            "top_k": top_k,
            "language": language,
            "coverage": coverage,
            "strong_count": len(strong),
        }

        if len(strong) < 2 or coverage < 0.16:
            return self._refusal_answer(question, evidence, package, language, coverage, strong)

        claim_lines: list[str] = []
        contradiction_lines: list[str] = []
        for item in strong[:4]:
            if item.get("claim_text"):
                claim_lines.append(f"- {item['claim_text']}")
            else:
                claim_lines.append(f"- {item['evidence_text'][:220]}")
        for item in contradictions[:3]:
            if item.get("claim_text"):
                contradiction_lines.append(f"- {item['claim_text']}")

        if language == "en":
            answer = (
                "Based on the uploaded sources, the system can highlight these supported points:\n"
                + "\n".join(claim_lines)
            )
            if contradiction_lines:
                answer += "\n\nThe knowledge graph also contains claims that contradict the above:\n" + "\n".join(contradiction_lines)
            answer += "\n\nThe conclusion is limited to the selected publications and should not be treated as external scientific expertise."
            limitations = [
                "The MVP uses heuristic extraction and a sentence-transformer or deterministic embedding fallback.",
                "Production-level accuracy requires human-in-the-loop review and a dedicated LLM/ML extraction layer.",
            ]
            if contradictions:
                limitations.append(f"{len(contradictions)} contradicting claim(s) were detected and disclosed.")
        else:
            answer = (
                "На основе загруженных источников можно показать такие подтверждённые положения:\n"
                + "\n".join(claim_lines)
            )
            if contradiction_lines:
                answer += "\n\nВ графе знаний также есть утверждения, которые противоречат сказанному выше:\n" + "\n".join(contradiction_lines)
            answer += "\n\nВывод ограничен найденными публикациями и не заменяет научную экспертизу."
            limitations = [
                "MVP использует эвристическое извлечение и sentence-transformer или детерминированный fallback для embeddings.",
                "Для промышленной точности нужен human-in-the-loop review и отдельный LLM/ML extraction layer.",
            ]
            if contradictions:
                limitations.append(f"Обнаружено противоречащих claim'ов: {len(contradictions)} — они показаны отдельно.")

        used_claim_ids = [item["claim_id"] for item in strong if item.get("claim_id")]
        used_entities = self._entities_for_claims(used_claim_ids)
        used_claims_map = self._fetch_claims_by_ids(used_claim_ids) if used_claim_ids else {}
        rag = RagAnswer(
            id=_id("rag"),
            question=question,
            answer=answer,
            status="answered",
            confidence_score=round(min(0.95, coverage + sum(i["evidence_strength"] for i in strong[:4]) / 5), 3),
            sources=strong[:top_k],
            used_entities=[asdict(e) for e in used_entities],
            used_claims=[asdict(used_claims_map[cid]) for cid in used_claim_ids if cid in used_claims_map],
            reasoning_trace=[
                "question",
                "activation_keys",
                "entities",
                "claims",
                "evidence_builder",
                "contradiction_disclosure" if contradictions else "evidence_aggregation",
                "grounded_answer",
            ],
            limitations=limitations,
        )
        self.rag_answers[rag.id] = rag
        self._persist("upsert_rag_answer", rag)
        return rag

    def _refusal_answer(
        self,
        question: str,
        evidence: list[dict[str, Any]],
        package: dict[str, Any],
        language: str,
        coverage: float,
        strong: list[dict[str, Any]],
    ) -> RagAnswer:
        if language == "en":
            answer = (
                "There is not enough verifiable evidence in the knowledge base to answer confidently. "
                "The system found too few relevant facts or sources, so it did not generate an unsupported answer."
            )
            limitations = [
                "Not enough relevant evidence fragments were found.",
                "Add more publications on this topic or make the question more specific.",
            ]
        else:
            answer = (
                "В загруженной базе недостаточно проверяемых источников для уверенного ответа. "
                "Система нашла слишком мало релевантных фактов или фрагментов, поэтому не стала придумывать ответ."
            )
            limitations = [
                "Недостаточно релевантных фрагментов из источников.",
                "Добавьте публикации по теме или уточните вопрос.",
            ]
        rag = RagAnswer(
            id=_id("rag"),
            question=question,
            answer=answer,
            status="insufficient_evidence",
            confidence_score=round(min(0.45, coverage + len(strong) * 0.08), 3),
            sources=evidence[:3],
            used_entities=package["activation"]["activated_entities"][:8],
            used_claims=package["activation"]["activated_claims"][:8],
            reasoning_trace=[
                "question",
                "activation_keys",
                "insufficient_entities_or_claims",
                "honest_refusal",
            ],
            limitations=limitations,
        )
        self.rag_answers[rag.id] = rag
        self._persist("upsert_rag_answer", rag)
        return rag

    def evaluate_rag_answer(self, rag_answer_id: str) -> EvaluationRecord:
        rag = self.rag_answers.get(rag_answer_id)
        if not rag:
            raise KeyError("rag answer not found")
        source_count = len(rag.sources)
        claim_count = len(rag.used_claims)
        faithfulness = self._faithfulness(rag)
        hallucination_rate = max(0.0, 1.0 - faithfulness) if rag.status == "answered" else 0.0
        contradiction_awareness = self._contradiction_awareness(rag)
        metrics = {
            "faithfulness": round(faithfulness, 3),
            "source_coverage": round(min(1.0, source_count / 4), 3),
            "hallucination_rate": round(hallucination_rate, 3),
            "answer_completeness": round(min(1.0, claim_count / 3), 3) if rag.status == "answered" else 0.0,
            "citation_correctness": 1.0 if source_count else 0.0,
            "limitation_honesty": 0.98 if rag.limitations else 0.5,
            "reasoning_trace_quality": round(min(1.0, len(rag.reasoning_trace) / 7), 3),
            "contradiction_awareness": round(contradiction_awareness, 3),
        }
        events: list[str] = []
        signal = "positive" if metrics["faithfulness"] >= 0.8 else "review_required"
        for source in rag.sources:
            target_id = source.get("claim_id")
            if not target_id:
                continue
            event = self.submit_feedback(
                event_type="evaluation_signal",
                target_id=target_id,
                signal=signal,
                weight_delta=0.03 if signal == "positive" else -0.05,
                payload={"rag_answer_id": rag.id, "metrics": metrics},
                apply_now=True,
            )
            events.append(event.id)
        record = EvaluationRecord(
            id=_id("eval"),
            rag_answer_id=rag.id,
            metrics=metrics,
            feedback_events_created=events,
        )
        self.evaluations[record.id] = record
        self._persist("upsert_evaluation", record)
        return record

    def _faithfulness(self, rag: RagAnswer) -> float:
        if rag.status == "insufficient_evidence":
            return 1.0
        if not rag.sources:
            return 0.4
        strong_sources = [s for s in rag.sources if s.get("score", 0.0) >= 0.30]
        coverage_ratio = min(1.0, len(strong_sources) / max(1, len(rag.sources)))
        evidence_mean = sum(s.get("evidence_strength", 0.5) for s in rag.sources) / len(rag.sources)
        return min(0.97, 0.55 + 0.25 * coverage_ratio + 0.20 * evidence_mean)

    def _contradiction_awareness(self, rag: RagAnswer) -> float:
        if rag.status != "answered":
            return 1.0
        contradicting = sum(1 for s in rag.sources if s.get("contradiction_risk", 0.0) > 0.3)
        if contradicting == 0:
            return 0.7
        mentioned = "противореч" in rag.answer.lower() or "contradict" in rag.answer.lower()
        return 1.0 if mentioned else 0.5

    def create_feedback_event(
        self,
        *,
        event_type: str,
        target_id: str,
        signal: str,
        weight_delta: float = 0.0,
        payload: dict[str, Any] | None = None,
    ) -> FeedbackEvent:
        return self.submit_feedback(
            event_type=event_type,
            target_id=target_id,
            signal=signal,
            weight_delta=weight_delta,
            payload=payload,
            apply_now=True,
        )
