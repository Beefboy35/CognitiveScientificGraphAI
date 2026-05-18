from __future__ import annotations

import logging
from typing import Any

from .models import FeedbackEvent
from .utils import _id, utc_now


logger = logging.getLogger(__name__)


class ScientificFeedbackMixin:
    """Implements the Feedback Loop from TZ §3.8.

    Feedback events are first-class citizens: they are persisted, applied to
    target objects (claims / relations / publications), and may schedule items
    for human review.  Each application is idempotent — the same event applied
    twice will not double-shift the weights.
    """

    def submit_feedback(
        self,
        *,
        event_type: str,
        target_id: str,
        signal: str,
        weight_delta: float = 0.0,
        payload: dict[str, Any] | None = None,
        apply_now: bool = True,
    ) -> FeedbackEvent:
        event = FeedbackEvent(
            id=_id("fb"),
            event_type=event_type,
            target_id=target_id,
            signal=signal,
            weight_delta=weight_delta,
            payload=payload or {},
        )
        self.feedback_events[event.id] = event
        self._persist("upsert_feedback_event", event)
        if apply_now:
            self.apply_feedback_event(event)
        return event

    def apply_feedback_event(self, event: FeedbackEvent) -> dict[str, Any]:
        if event.payload.get("_applied") is True:
            return {"event_id": event.id, "applied": False, "reason": "already applied"}
        result: dict[str, Any] = {"event_id": event.id, "applied": True, "changes": []}
        target_id = event.target_id
        if target_id in self.claims:
            claim = self.claims[target_id]
            new_confidence = round(max(0.05, min(1.0, claim.confidence_score + event.weight_delta)), 3)
            new_strength = round(max(0.05, min(1.0, claim.evidence_strength + event.weight_delta * 0.5)), 3)
            result["changes"].append(
                {
                    "kind": "claim",
                    "id": claim.id,
                    "confidence_before": claim.confidence_score,
                    "confidence_after": new_confidence,
                    "evidence_strength_before": claim.evidence_strength,
                    "evidence_strength_after": new_strength,
                }
            )
            claim.confidence_score = new_confidence
            claim.evidence_strength = new_strength
            # Записываем в Neo4j (источник истины графа) через Cypher SET.
            persistence = getattr(self, "persistence", None)
            neo4j_adapter = getattr(persistence, "neo4j", None) if persistence else None
            if neo4j_adapter is not None and getattr(neo4j_adapter, "is_active", lambda: False)():
                neo4j_adapter.update_claim_properties(
                    claim.id,
                    {"confidence_score": new_confidence, "evidence_strength": new_strength},
                )
                neo4j_adapter.increment_supports_weights(claim.id, event.weight_delta * 0.5)
            for relation in self.relations.values():
                if relation.source_claim_id != claim.id and relation.target_claim_id != claim.id:
                    continue
                if relation.relation_type != "supports":
                    continue
                new_weight = round(max(0.05, min(1.0, relation.weight + event.weight_delta * 0.5)), 3)
                if abs(new_weight - relation.weight) > 1e-6:
                    result["changes"].append(
                        {
                            "kind": "relation",
                            "id": relation.id,
                            "weight_before": relation.weight,
                            "weight_after": new_weight,
                        }
                    )
                    relation.weight = new_weight
            if event.signal == "review_required":
                self._enqueue_review(
                    item_type="claim",
                    item_id=claim.id,
                    reason=event.payload.get("rag_answer_id", "low evidence"),
                    metadata={"signal": event.signal, "weight_delta": event.weight_delta},
                )
                result["changes"].append({"kind": "review_queue", "id": claim.id})
        elif target_id in self.relations:
            relation = self.relations[target_id]
            new_weight = round(max(0.05, min(1.0, relation.weight + event.weight_delta)), 3)
            result["changes"].append(
                {
                    "kind": "relation",
                    "id": relation.id,
                    "weight_before": relation.weight,
                    "weight_after": new_weight,
                }
            )
            relation.weight = new_weight
        elif target_id in self.publications:
            publication = self.publications[target_id]
            publication.metadata.setdefault("feedback_signals", []).append(
                {"signal": event.signal, "weight_delta": event.weight_delta, "at": utc_now()}
            )
            result["changes"].append({"kind": "publication", "id": publication.id})
        event.payload["_applied"] = True
        self._persist("upsert_feedback_event", event)
        return result

    def apply_pending_feedback(self) -> dict[str, Any]:
        applied = []
        skipped = 0
        for event in list(self.feedback_events.values()):
            if event.payload.get("_applied"):
                skipped += 1
                continue
            applied.append(self.apply_feedback_event(event))
        return {"applied": len(applied), "skipped": skipped, "results": applied}

    def list_review_queue(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self.review_queue.values()]

    def resolve_review_item(
        self,
        review_id: str,
        *,
        action: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        item = self.review_queue.get(review_id)
        if not item:
            raise KeyError("review item not found")
        item["resolution"] = {"action": action, "note": note, "resolved_at": utc_now()}
        item["status"] = "resolved"
        target_id = item.get("item_id")
        if action == "approve" and target_id in self.claims:
            claim = self.claims[target_id]
            claim.confidence_score = round(min(1.0, claim.confidence_score + 0.05), 3)
        elif action == "reject" and target_id in self.claims:
            claim = self.claims[target_id]
            claim.confidence_score = round(max(0.05, claim.confidence_score - 0.10), 3)
        self._persist("upsert_review_item", item)
        return dict(item)

    def _enqueue_review(
        self,
        *,
        item_type: str,
        item_id: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        review_id = _id("rev")
        item = {
            "id": review_id,
            "item_type": item_type,
            "item_id": item_id,
            "reason": reason,
            "status": "open",
            "created_at": utc_now(),
            "metadata": metadata or {},
        }
        self.review_queue[review_id] = item
        self._persist("upsert_review_item", item)
