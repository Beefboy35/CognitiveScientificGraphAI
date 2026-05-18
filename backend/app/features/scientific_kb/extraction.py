from __future__ import annotations

import logging
import re
from typing import Any, Literal

from .models import ClaimRelation, DocumentChunk, ScientificClaim, ScientificEntity
from .ontology import (
    ALIASES,
    CLAIM_TYPE_WEIGHT,
    ONTOLOGY,
    SECTION_WEIGHT,
    EntityType,
)
from .utils import _id, _sentences, _stable_id, _tokenize


logger = logging.getLogger(__name__)


ENTITY_TYPE_SET = {
    "Method",
    "Model",
    "Dataset",
    "Metric",
    "Task",
    "Tool",
    "ResearchField",
    "Limitation",
    "Result",
}


CLAIM_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    # English (compatibility)
    ("definition", "defines", re.compile(r"\b(is defined as|we define|defined as|refers to)\b", re.I)),
    ("hypothesis", "hypothesizes", re.compile(r"\b(we hypothesize|we conjecture|we posit|we expect that|we predict)\b", re.I)),
    ("replication_note", "replicates", re.compile(r"\b(replicated|reproducibility|across (?:three|five|two) (?:seeds|runs|datasets|campaigns)|under independent|verified by an independent)\b", re.I)),
    ("contradiction_candidate", "contradicts", re.compile(r"\b(contrary to|unlike|differs from|contradicting earlier|however we found|however,? we observe|but we (?:found|observe)|disagrees with)\b", re.I)),
    ("conclusion", "concludes", re.compile(r"\b(we conclude|in conclusion|overall,|therefore,?|thus,?|the results show|the results indicate)\b", re.I)),
    ("limitation", "is_limited_by", re.compile(r"\b(limit|limits|limitation|may (?:miss|fail|leak)|cannot|does not generalise|fails|drops on|annotation cost|reproducibility risk|context window limit|retrieval precision drop|suffers from)\b", re.I)),
    ("comparison", "compares", re.compile(r"\b(compared with|in comparison|outperform|outperforms|better than|than the|over the baseline|trades a)\b", re.I)),
    ("experimental_result", "improves", re.compile(r"\b(improve|improves|improved|achieve|achieves|increase|increases|reduce|reduces|reduced|drops|gain|gains)\b", re.I)),
    ("method_description", "uses", re.compile(r"\b(we propose|our method|our approach|the proposed (?:method|approach)|the system uses|the pipeline relies)\b", re.I)),
    # Russian
    ("definition", "определяет", re.compile(r"(определяется как|определяются как|по определению|называется|называют|\bпонимается\b|обозначает понятие|—\s*это|представляет собой|является\s+(?:способом|задачей|методом|техникой|алгоритмом))", re.I | re.U)),
    ("hypothesis", "выдвигает гипотезу", re.compile(r"(мы предполагаем|мы выдвигаем гипотезу|выдвинута гипотеза|по нашему мнению|мы ожидаем что|допустим что)", re.I | re.U)),
    ("replication_note", "воспроизводит", re.compile(r"(воспроизвед(ен|ено|ена|ены)|воспроизводимост|повторено на|по результатам (?:трёх|пяти|двух)\s+(?:запусков|прогонов|экспериментов)|подтверждено независимо)", re.I | re.U)),
    ("contradiction_candidate", "противоречит", re.compile(r"(в отличие от|противоречит|противоречие|однако мы (?:обнаружили|наблюдаем)|напротив|напротив,|расходится с|вопреки)", re.I | re.U)),
    ("conclusion", "заключает", re.compile(r"(мы заключаем|в заключение|таким образом|следовательно|подытоживая|итого,|результаты показывают|результаты демонстрируют)", re.I | re.U)),
    ("limitation", "ограничивается", re.compile(r"(ограничивается|ограничение|не справляется|не способен|не способна|требует значительн|уступает по|слабая сторона|трудоём|зависит от качества|плохо масштабируется|деградирует)", re.I | re.U)),
    ("comparison", "сравнивает", re.compile(r"(по сравнению с|превосходит|обгоняет|лучше чем|хуже чем|в сравнении|опережает|быстрее на|медленнее на|точнее на)", re.I | re.U)),
    ("experimental_result", "улучшает", re.compile(r"(улучшает|улучшил|улучшила|улучшили|повышает|повышает на|снижает|снижает на|сокращает|увеличивает|уменьшает|достигает|показал|показала|показали|даёт прирост|обеспечивает прирост)", re.I | re.U)),
    ("method_description", "использует", re.compile(r"(мы предлагаем|предложенн(ый|ая) метод|наш метод|наш подход|используется метод|применяется метод|опирается на|базируется на|основан на|мы определяем|алгоритм работает|программа берёт|метод работает)", re.I | re.U)),
    # Дополнительные паттерны для нового компактного учебного корпуса.
    # Используются конструкции, типичные для школьно-образовательного текста.
    ("limitation", "ограничивается", re.compile(r"(работает только если|применимо только|не работает на|не применимо|требует условия|требует предварительн|становится медленн|становится неприемлем|невозможн[оа] применить)", re.I | re.U)),
    ("experimental_result", "улучшает", re.compile(r"(для массива длины|для таблицы из|число операций сравнения|число операций|число шагов|за \d+\s*шаг|выполняется за|обходится дороже|ускорение составляет|в \d+\s*раз)", re.I | re.U)),
    ("definition", "определяет", re.compile(r"(мы определяем\s+\S+\s+(?:как|так)|называется\s+(?:способ|метод|приём|алгоритм|структур))", re.I | re.U)),
]


CLAIM_TYPE_SPECIFICITY: dict[str, int] = {
    "definition": 9,
    "hypothesis": 9,
    "replication_note": 9,
    "contradiction_candidate": 8,
    "conclusion": 7,
    "limitation": 6,
    "comparison": 5,
    "experimental_result": 4,
    "method_description": 3,
}


SECTION_BONUS: dict[str, dict[str, int]] = {
    "Results": {"experimental_result": 6},
    "Experiments": {"experimental_result": 6},
    "Evaluation": {"experimental_result": 5},
    "Comparison": {"comparison": 6},
    "Comparisons": {"comparison": 6},
    "Reproducibility": {"replication_note": 4},
    "Replication": {"replication_note": 4},
    "Conclusion": {"conclusion": 4},
    "Conclusions": {"conclusion": 4},
    "Limitations": {"limitation": 4},
    "Hypothesis": {"hypothesis": 4},
    "Hypotheses": {"hypothesis": 4},
    "Contradiction": {"contradiction_candidate": 4},
    "Methods": {"method_description": 4},
    "Method": {"method_description": 4},
    "Approach": {"method_description": 4},
}


VALUE_RE = re.compile(r"([+-]?\d+(?:\.\d+)?\s?%|\d+(?:\.\d+)?\s?(?:points|pp|x))", re.I)
CONDITION_RE = re.compile(r"\b(on|under|when|for|across)\s+([^.;,]+)", re.I)


class ScientificExtractionMixin:
    def _llm_enrich_chunks(self, chunks: list[DocumentChunk]) -> dict[str, Any]:
        """Run OpenRouter extraction on every chunk and store results in cache.

        The pipeline calls this BEFORE rule-based extraction. Both LLM and
        rule-based outputs are merged downstream, so LLM failure is never fatal.
        """
        summary = {"used": False, "chunks": 0, "claims": 0, "entities": 0, "tokens_in": 0, "tokens_out": 0}
        if not getattr(self, "_use_llm_for_current_run", False):
            return summary
        extractor = getattr(self, "_llm_extractor", None)
        if extractor is None or not extractor.is_active():
            return summary
        if not hasattr(self, "_llm_chunk_cache") or self._llm_chunk_cache is None:
            self._llm_chunk_cache = {}
        known_entity_names = sorted(self._entity_by_canonical.keys())
        summary["used"] = True
        for chunk in chunks:
            try:
                result = extractor.extract_chunk(
                    text=chunk.text,
                    section=chunk.section,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    known_entities=known_entity_names,
                )
            except Exception as exc:
                logger.warning("llm_chunk_extract_failed", extra={"chunk_id": chunk.id, "error": str(exc)})
                continue
            if result is None:
                continue
            self._llm_chunk_cache[chunk.id] = result
            summary["chunks"] += 1
            summary["claims"] += len(result.claims)
            summary["entities"] += len(result.entities)
            summary["tokens_in"] += int(getattr(result, "tokens_in", 0) or 0)
            summary["tokens_out"] += int(getattr(result, "tokens_out", 0) or 0)
        return summary

    def _extract_entities(self, chunks: list[DocumentChunk]) -> list[ScientificEntity]:
        touched: list[ScientificEntity] = []
        for chunk in chunks:
            lowered = chunk.text.lower()
            for entity_type, names in ONTOLOGY.items():
                for name in names:
                    aliases = [a for a, canonical in ALIASES.items() if canonical == name]
                    candidates = [name, *aliases]
                    if not any(self._mentions(candidate, lowered) for candidate in candidates):
                        continue
                    entity = self._upsert_entity(name, entity_type, aliases)
                    entity.mentions.append(
                        {
                            "publication_id": chunk.publication_id,
                            "chunk_id": chunk.id,
                            "page": chunk.page_start,
                            "section": chunk.section,
                            "surface": name,
                        }
                    )
                    entity.confidence_score = round(min(0.98, entity.confidence_score + 0.02), 3)
                    touched.append(entity)

            seen_acronyms_in_chunk: set[str] = set()
            for acronym in re.findall(r"\b[A-Z][A-Z0-9]{2,}\b", chunk.text):
                if acronym in seen_acronyms_in_chunk:
                    continue
                seen_acronyms_in_chunk.add(acronym)
                canonical = ALIASES.get(acronym.lower(), acronym)
                if canonical in self._entity_by_canonical:
                    entity = self.entities[self._entity_by_canonical[canonical]]
                else:
                    entity = self._upsert_entity(
                        canonical,
                        "Model",
                        [acronym] if canonical != acronym else [],
                    )
                entity.mentions.append(
                    {
                        "publication_id": chunk.publication_id,
                        "chunk_id": chunk.id,
                        "page": chunk.page_start,
                        "section": chunk.section,
                        "surface": acronym,
                    }
                )
                touched.append(entity)
        # Merge LLM-discovered entities (only available when LLM extractor ran)
        llm_cache = getattr(self, "_llm_chunk_cache", None) or {}
        for chunk in chunks:
            result = llm_cache.get(chunk.id)
            if result is None:
                continue
            for raw in getattr(result, "entities", []) or []:
                name = (raw.get("canonical_name") or "").strip()
                etype = (raw.get("entity_type") or "").strip()
                if not name or etype not in ENTITY_TYPE_SET:
                    continue
                canonical = ALIASES.get(name.lower(), name)
                aliases = [str(a) for a in raw.get("aliases") or [] if isinstance(a, str)]
                entity = self._upsert_entity(canonical, etype, aliases)
                entity.confidence_score = round(
                    max(entity.confidence_score, float(raw.get("confidence") or 0.78)),
                    3,
                )
                entity.mentions.append(
                    {
                        "publication_id": chunk.publication_id,
                        "chunk_id": chunk.id,
                        "page": chunk.page_start,
                        "section": chunk.section,
                        "surface": canonical,
                        "source": "llm",
                    }
                )
                touched.append(entity)
        return touched

    def _mentions(self, candidate: str, lowered_text: str) -> bool:
        candidate_lower = candidate.lower()
        if not candidate_lower:
            return False
        pattern = r"(?<![A-Za-z0-9])" + re.escape(candidate_lower) + r"(?![A-Za-z0-9])"
        return re.search(pattern, lowered_text) is not None

    def _upsert_entity(self, name: str, entity_type: EntityType, aliases: list[str]) -> ScientificEntity:
        canonical = ALIASES.get(name.lower(), name)
        entity_id = self._entity_by_canonical.get(canonical)
        if entity_id:
            entity = self.entities[entity_id]
            entity.aliases = sorted(set(entity.aliases) | set(aliases))
            return entity
        # Stable id по canonical_name — entity dedup'ируется автоматически.
        entity = ScientificEntity(
            id=_stable_id("ent", canonical),
            canonical_name=canonical,
            entity_type=entity_type,
            aliases=sorted(set(aliases)),
            mentions=[],
            confidence_score=0.72,
        )
        self.entities[entity.id] = entity
        self._entity_by_canonical[canonical] = entity.id
        return entity

    def _normalize_entities(self) -> None:
        for alias, canonical in ALIASES.items():
            entity_id = self._entity_by_canonical.get(canonical)
            if entity_id:
                entity = self.entities[entity_id]
                entity.aliases = sorted(set(entity.aliases) | {alias})

    def _extract_claims(self, chunks: list[DocumentChunk], extraction_run_id: str) -> list[ScientificClaim]:
        new_claims: list[ScientificClaim] = []
        seen_signatures: set[tuple[str, str]] = set()  # (chunk_id, claim_text)
        # 1) LLM-first: any claims the LLM extracted take priority and bypass rule heuristics.
        llm_cache = getattr(self, "_llm_chunk_cache", None) or {}
        llm_claim_index: dict[str, dict[int, str]] = {}
        for chunk in chunks:
            result = llm_cache.get(chunk.id)
            if result is None:
                continue
            index_to_id: dict[int, str] = {}
            for idx, raw in enumerate(getattr(result, "claims", []) or []):
                text = (raw.get("claim_text") or "").strip()
                ct = (raw.get("claim_type") or "").strip()
                if not text or ct not in CLAIM_TYPE_WEIGHT:
                    continue
                signature = (chunk.id, text.lower())
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                claim = ScientificClaim(
                    id=_stable_id("claim", chunk.publication_id, chunk.id, text),
                    claim_text=text,
                    claim_type=ct,
                    subject_entity=raw.get("subject_entity") or "Scientific publication",
                    predicate=raw.get("predicate") or "states",
                    object_entity=raw.get("object_entity") or "Research result",
                    comparison_target=raw.get("comparison_target"),
                    condition=raw.get("condition"),
                    metric=raw.get("metric"),
                    value=raw.get("value"),
                    evidence_text=(raw.get("evidence_text") or text),
                    publication_id=chunk.publication_id,
                    chunk_id=chunk.id,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    confidence_score=float(raw.get("confidence_score") or 0.74),
                    evidence_strength=float(raw.get("evidence_strength") or 0.72),
                    source_reliability=self._source_reliability(chunk.section, ct),
                    extraction_run_id=extraction_run_id,
                )
                self.claims[claim.id] = claim
                new_claims.append(claim)
                index_to_id[idx] = claim.id
            if index_to_id:
                llm_claim_index[chunk.id] = index_to_id
        # 2) Rule-based safety net for sentences the LLM did not surface.
        for chunk in chunks:
            entity_names = self._entity_names_in_text(chunk.text)
            for sentence in _sentences(chunk.text):
                if not self._looks_like_claim(sentence):
                    continue
                signature = (chunk.id, sentence.strip().lower())
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                claim_type, predicate = self._claim_type_predicate(sentence, chunk.section)
                subject, obj = self._subject_object(sentence, entity_names, claim_type)
                metric = self._first_entity_of_type(entity_names, "Metric")
                value = self._extract_value(sentence)
                source_reliability = self._source_reliability(chunk.section, claim_type)
                claim = ScientificClaim(
                    id=_stable_id("claim", chunk.publication_id, chunk.id, sentence.strip()),
                    claim_text=sentence.strip(),
                    claim_type=claim_type,
                    subject_entity=subject,
                    predicate=predicate,
                    object_entity=obj,
                    comparison_target=self._comparison_target(sentence, entity_names, subject, obj),
                    condition=self._condition(sentence),
                    metric=metric,
                    value=value,
                    evidence_text=sentence.strip(),
                    publication_id=chunk.publication_id,
                    chunk_id=chunk.id,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    confidence_score=self._claim_confidence(sentence, claim_type),
                    evidence_strength=self._evidence_strength(sentence, claim_type, chunk.section, metric),
                    source_reliability=source_reliability,
                    extraction_run_id=extraction_run_id,
                )
                self.claims[claim.id] = claim
                new_claims.append(claim)
        # 3) LLM-suggested inter-claim relations are persisted alongside rule-based ones later.
        self._llm_relation_index = llm_claim_index
        return new_claims

    def _looks_like_claim(self, sentence: str) -> bool:
        for _, _, pattern in CLAIM_PATTERNS:
            if pattern.search(sentence):
                return True
        return False

    def _claim_type_predicate(self, sentence: str, section: str) -> tuple[str, str]:
        section_norm = (section or "").title()
        bonuses = SECTION_BONUS.get(section_norm, {})
        scored: list[tuple[int, str, str]] = []
        for claim_type, predicate, pattern in CLAIM_PATTERNS:
            if not pattern.search(sentence):
                continue
            weight = CLAIM_TYPE_SPECIFICITY.get(claim_type, 0) + bonuses.get(claim_type, 0)
            scored.append((weight, claim_type, predicate))
        if scored:
            scored.sort(reverse=True)
            return scored[0][1], scored[0][2]
        if section_norm == "Limitations":
            return "limitation", "is_limited_by"
        if section_norm in {"Conclusion", "Conclusions"}:
            return "conclusion", "concludes"
        if section_norm in {"Results", "Experiments", "Evaluation"}:
            return "experimental_result", "improves"
        if section_norm in {"Hypothesis", "Hypotheses"}:
            return "hypothesis", "hypothesizes"
        if section_norm in {"Reproducibility", "Replication"}:
            return "replication_note", "replicates"
        if section_norm == "Contradiction":
            return "contradiction_candidate", "contradicts"
        return "method_description", "uses"

    def _subject_object(self, sentence: str, entity_names: list[str], claim_type: str) -> tuple[str, str]:
        if not entity_names:
            return "Scientific publication", "Research result"
        lower = sentence.lower()
        ordered = sorted(
            entity_names,
            key=lambda e: lower.find(e.lower()) if e.lower() in lower else 9999,
        )
        subject = ordered[0]
        obj = ordered[1] if len(ordered) > 1 else "Research result"
        if claim_type == "definition" and len(ordered) >= 1:
            obj = "definition"
        return subject, obj

    def _comparison_target(
        self, sentence: str, entity_names: list[str], subject: str, obj: str
    ) -> str | None:
        lower = sentence.lower()
        if not any(marker in lower for marker in ("compared with", "than ", "over the", "contrary to", "unlike")):
            return None
        for name in entity_names:
            if name not in {subject, obj}:
                return name
        return None

    def _condition(self, sentence: str) -> str | None:
        match = CONDITION_RE.search(sentence)
        if not match:
            return None
        return match.group(0).strip().rstrip(".,;:")[:200]

    def _extract_value(self, sentence: str) -> str | None:
        match = VALUE_RE.search(sentence)
        return match.group(1).strip() if match else None

    def _first_entity_of_type(self, entity_names: list[str], entity_type: EntityType) -> str | None:
        for name in entity_names:
            entity_id = self._entity_by_canonical.get(name)
            if entity_id and self.entities[entity_id].entity_type == entity_type:
                return name
        return None

    def _claim_confidence(self, sentence: str, claim_type: str) -> float:
        score = 0.62
        if self._extract_value(sentence):
            score += 0.12
        if len(self._entity_names_in_text(sentence)) >= 2:
            score += 0.10
        if claim_type in ("experimental_result", "comparison"):
            score += 0.06
        if claim_type in ("hypothesis", "definition"):
            score -= 0.04
        if re.search(r"\b(may|might|could|seems|appears|candidate)\b", sentence, re.I):
            score -= 0.08
        return round(max(0.35, min(0.95, score)), 3)

    def _evidence_strength(
        self, sentence: str, claim_type: str, section: str, metric: str | None
    ) -> float:
        section_w = SECTION_WEIGHT.get((section or "").title(), 0.55)
        type_w = CLAIM_TYPE_WEIGHT.get(claim_type, 0.55)
        extraction_w = 0.55
        if metric:
            extraction_w += 0.10
        if self._extract_value(sentence):
            extraction_w += 0.12
        if re.search(r"\b(may|might|could)\b", sentence, re.I):
            extraction_w -= 0.07
        extraction_w = max(0.30, min(0.96, extraction_w))
        strength = 0.25 * extraction_w + 0.20 * section_w + 0.20 * type_w + 0.15 * 0.74 + 0.10 * 0.55 - 0.10 * 0.05
        return round(max(0.20, min(0.96, strength + 0.10)), 3)

    def _source_reliability(self, section: str, claim_type: str) -> float:
        base = 0.70
        section_norm = (section or "").title()
        if section_norm in {"Results", "Experiments", "Evaluation"}:
            base += 0.08
        if section_norm in {"Reproducibility", "Replication"}:
            base += 0.06
        if claim_type in {"hypothesis", "definition"}:
            base -= 0.04
        return round(max(0.40, min(0.95, base)), 3)

    def _entity_names_in_text(self, text: str) -> list[str]:
        lowered = text.lower()
        names: list[tuple[str, int]] = []
        for entity in self.entities.values():
            candidates = [entity.canonical_name, *entity.aliases]
            best_pos: int | None = None
            for candidate in candidates:
                if not self._mentions(candidate, lowered):
                    continue
                pos = lowered.find(candidate.lower())
                if pos == -1:
                    continue
                if best_pos is None or pos < best_pos:
                    best_pos = pos
            if best_pos is not None:
                names.append((entity.canonical_name, best_pos))
        return [n for n, _ in sorted(set(names), key=lambda item: item[1])]

    def _build_claim_relations(self, claims: list[ScientificClaim]) -> list[ClaimRelation]:
        """Извлечение связей между claims.

        Строгий контракт:
        - Связь создаётся **только при наличии evidence** (текстового маркера,
          совпадения subject_entity + claim_type из разных публикаций, или
          явного указания LLM).
        - **Никогда** не создаём связь только из-за "shared metric/object"
          или для покрытия онтологии — это давало взрывной N² рост.
        - Связи внутри одной публикации не строим (это внутренняя структура
          одного материала, а не граф знаний).
        - Каждая связь имеет provenance `created_by`: rule | llm | manual.
        """
        existing = {(r.source_claim_id, r.target_claim_id, r.relation_type) for r in self.relations.values()}
        created: list[ClaimRelation] = []

        # ── 1) LLM-proposed relations ─────────────────────────────────────
        # LLM видел контекст обоих claims одновременно и явно предложил связь.
        # Доверяем больше, чем rule-based — но всё равно требуем валидный тип.
        llm_cache = getattr(self, "_llm_chunk_cache", None) or {}
        llm_index = getattr(self, "_llm_relation_index", None) or {}
        for chunk_id, idx_map in llm_index.items():
            result = llm_cache.get(chunk_id)
            if result is None:
                continue
            for raw in getattr(result, "relations", []) or []:
                src_idx = raw.get("source_index")
                tgt_idx = raw.get("target_index")
                rt = raw.get("relation_type")
                if rt not in {"supports", "contradicts", "limits", "extends"}:
                    continue
                src_id = idx_map.get(src_idx)
                tgt_id = idx_map.get(tgt_idx)
                if not src_id or not tgt_id or src_id == tgt_id:
                    continue
                key = (src_id, tgt_id, rt)
                if key in existing:
                    continue
                left = self.claims.get(src_id)
                right = self.claims.get(tgt_id)
                if left is None or right is None:
                    continue
                relation = ClaimRelation(
                    id=_stable_id("rel", src_id, tgt_id, rt),
                    source_claim_id=src_id,
                    target_claim_id=tgt_id,
                    relation_type=rt,  # type: ignore[arg-type]
                    weight=round(float(raw.get("weight") or 0.75), 3),
                    confidence_score=round((left.confidence_score + right.confidence_score) / 2, 3),
                    evidence_strength=round((left.evidence_strength + right.evidence_strength) / 2, 3),
                    source_reliability=round((left.source_reliability + right.source_reliability) / 2, 3),
                    rationale=str(raw.get("rationale") or "LLM-extracted relation"),
                    created_by="llm",
                )
                self.relations[relation.id] = relation
                created.append(relation)
                existing.add(key)

        # ── 2) Rule-based relations — строгие критерии ────────────────────
        # Группируем claims по нормализованному subject_entity для O(k²)
        # внутри группы вместо O(N²) по всему корпусу. Это и логично, и быстро:
        # связи имеют смысл только между claims об одной сущности.
        by_subject: dict[str, list[ScientificClaim]] = {}
        for claim in claims:
            subj = (claim.subject_entity or "").strip().lower()
            if not subj:
                continue
            by_subject.setdefault(subj, []).append(claim)

        for subj, group in by_subject.items():
            # Если в группе меньше 2 claims — связей не может быть.
            if len(group) < 2:
                continue
            for i, left in enumerate(group):
                for right in group[i + 1 :]:
                    # Игнорируем пары из одной публикации — внутренняя структура.
                    if left.publication_id == right.publication_id:
                        continue
                    relation_type = self._infer_relation_strict(left, right)
                    if relation_type is None:
                        continue
                    key = (left.id, right.id, relation_type)
                    if key in existing:
                        continue
                    strength = round((left.evidence_strength + right.evidence_strength) / 2, 3)
                    confidence = round((left.confidence_score + right.confidence_score) / 2, 3)
                    weight = round(min(0.97, 0.45 + strength / 2 + (0.05 if relation_type == "supports" else 0.0)), 3)
                    rationale = self._explain_relation(left, right, relation_type, subj)
                    relation = ClaimRelation(
                        id=_stable_id("rel", left.id, right.id, relation_type),
                        source_claim_id=left.id,
                        target_claim_id=right.id,
                        relation_type=relation_type,
                        weight=weight,
                        confidence_score=confidence,
                        evidence_strength=strength,
                        source_reliability=round((left.source_reliability + right.source_reliability) / 2, 3),
                        rationale=rationale,
                        created_by="rule",
                    )
                    self.relations[relation.id] = relation
                    created.append(relation)
                    existing.add(key)
        return created

    # ── Маркеры в тексте, явно указывающие на тип связи ────────────────
    # Регэкспы детерминированные; матч → +confidence что связь действительно есть.
    _EXTENDS_MARKERS = re.compile(
        r"\b(extends|builds on|based on|развивает|опирается на|обобщает|"
        r"расширяет|на основе|улучшен(ие|ный)|развитие)\b",
        re.IGNORECASE,
    )
    _CONTRADICTS_MARKERS = re.compile(
        r"\b(unlike|contrary to|however|but we found|в отличие|однако|"
        r"противоречит|не согласуется|опровергает|неверно)\b",
        re.IGNORECASE,
    )
    _LIMITS_MARKERS = re.compile(
        r"\b(only when|fails under|not applicable|requires|только если|"
        r"не применимо|при условии|ограничен(о|ие)|работает лишь)\b",
        re.IGNORECASE,
    )

    def _infer_relation_strict(
        self, left: ScientificClaim, right: ScientificClaim
    ) -> Literal["supports", "contradicts", "limits", "extends"] | None:
        """Строгий инференс типа связи.

        Возвращает relation_type ТОЛЬКО при наличии evidence:
        - CONTRADICTS: одинаковая метрика + противоположные значения, ИЛИ
          текстовый маркер противоречия в evidence_text одного из claims.
        - LIMITS: один из claims имеет claim_type='limitation', ИЛИ
          текстовый маркер ограничения.
        - EXTENDS: явный текстовый маркер расширения, ИЛИ один claim имеет
          claim_type='method_description', а другой — 'experimental_result'
          на ту же сущность (метод + его экспериментальная валидация).
        - SUPPORTS: одинаковый claim_type ∈ {definition, conclusion,
          experimental_result, method_description, replication_note} —
          т.е. оба claims делают одно и то же утверждение о субъекте.

        Во всех остальных случаях возвращает None.
        """
        # Текстовые маркеры — самый сильный сигнал. Проверяем оба evidence_text.
        text_blob = f"{left.evidence_text} {right.evidence_text} {left.claim_text} {right.claim_text}"

        # 1) CONTRADICTS: противоположные значения метрики ИЛИ маркер противоречия.
        if left.metric and right.metric and left.metric.strip().lower() == right.metric.strip().lower():
            if left.value and right.value and self._opposite_signs(left.value, right.value):
                return "contradicts"
        if self._CONTRADICTS_MARKERS.search(text_blob):
            return "contradicts"
        if left.claim_type == "contradiction_candidate" or right.claim_type == "contradiction_candidate":
            return "contradicts"

        # 2) LIMITS: limitation-claim ограничивает только содержательные
        # claims (method/conclusion/experimental_result), не другие limitations.
        # Это даёт более осмысленное "ограничивает применимость X".
        types = {left.claim_type, right.claim_type}
        target_types = {"method_description", "conclusion", "experimental_result", "definition"}
        if "limitation" in types and types & target_types:
            return "limits"
        # Маркер ограничения в тексте — отдельный сильный сигнал.
        if self._LIMITS_MARKERS.search(text_blob):
            return "limits"

        # 3) EXTENDS: явный маркер расширения ИЛИ метод+результат-пара.
        if self._EXTENDS_MARKERS.search(text_blob):
            return "extends"
        types = {left.claim_type, right.claim_type}
        if types == {"method_description", "experimental_result"}:
            return "extends"

        # 4) SUPPORTS: одинаковый claim_type из "утвердительных" категорий.
        AFFIRMATIVE = {
            "definition",
            "conclusion",
            "experimental_result",
            "method_description",
            "replication_note",
        }
        if left.claim_type == right.claim_type and left.claim_type in AFFIRMATIVE:
            return "supports"

        # Иначе — связи нет. Лучше пусть claim останется orphan,
        # чем мы засорим граф шумом.
        return None

    def _explain_relation(
        self,
        left: ScientificClaim,
        right: ScientificClaim,
        rt: str,
        subject: str,
    ) -> str:
        """Человеко-читаемое объяснение, почему связь была создана. Идёт в UI."""
        if rt == "supports":
            return (
                f"Обе публикации делают утверждение типа '{left.claim_type}' про '{subject}'. "
                f"Источники независимы → подтверждение."
            )
        if rt == "contradicts":
            if left.metric and left.value and right.value:
                return f"Метрика '{left.metric}' принимает значения с разными знаками в разных публикациях."
            return f"Найден текстовый маркер противоречия в evidence про '{subject}'."
        if rt == "limits":
            if "limitation" in {left.claim_type, right.claim_type}:
                return f"Один из claims обозначен как 'limitation' для сущности '{subject}'."
            return f"Найден маркер ограничения применимости в evidence про '{subject}'."
        if rt == "extends":
            types = sorted({left.claim_type, right.claim_type})
            if len(types) >= 2:
                return f"Связь '{types[0]} + {types[1]}' про '{subject}' — экспериментальное расширение метода."
            return f"Расширение идеи про '{subject}' (тип '{types[0]}')."
        return f"Связь типа '{rt}' между claims о '{subject}'"

    def _opposite_signs(self, left_value: str, right_value: str) -> bool:
        left_negative = "-" in left_value or "drop" in left_value.lower()
        right_negative = "-" in right_value or "drop" in right_value.lower()
        return left_negative != right_negative

    def _rebuild_activation_index(self) -> None:
        self.activation_index.clear()
        for entity in self.entities.values():
            for token in _tokenize(" ".join([entity.canonical_name, *entity.aliases])):
                if len(token) > 2:
                    self.activation_index[token]["entities"].add(entity.id)
        for chunk in self.chunks.values():
            for token in set(_tokenize(chunk.text)):
                if len(token) > 2:
                    self.activation_index[token]["chunks"].add(chunk.id)
        for claim in self.claims.values():
            text = " ".join(
                [
                    claim.claim_text,
                    claim.subject_entity,
                    claim.object_entity,
                    claim.metric or "",
                    claim.predicate,
                    claim.claim_type,
                ]
            )
            for token in set(_tokenize(text)):
                if len(token) > 2:
                    self.activation_index[token]["claims"].add(claim.id)
