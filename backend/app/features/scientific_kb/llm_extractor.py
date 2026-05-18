"""LLM-based extractor backed by OpenRouter.

Produces structured ScientificClaim v2 records (TZ §2.3) plus normalized
entities and inter-claim relations. The extractor speaks OpenAI-compatible
chat completions with strict JSON response.

Layering:

* `extract_chunk(...)` — one chunk → entities + claims + relations.
* `extract_chunks_batch(...)` — orchestrates per-chunk calls with caching and
  graceful degradation (one failing chunk does not block the rest).

Caching is content-hash keyed and lives both in-process and (when available)
in PostgreSQL via the persistence layer.  Re-runs on the same text + same
model + same prompt version return the cached result without hitting
OpenRouter.

The pipeline keeps the rule-based extractor as a safety net — if the LLM
returns an empty payload for a chunk, the rules still surface entities and
claims.  This is exactly what makes the extractor "production-grade" rather
than MVP.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


PROMPT_VERSION = "v3-2026-05-15"


SYSTEM_PROMPT = """Ты — экстрактор научных знаний для доказательной базы знаний в предметной области «Высшая математика и базы данных».

На входе ты получаешь ОДИН фрагмент научной статьи на русском (возможно с английскими терминами и формулами). На выходе ты возвращаешь СТРОГИЙ JSON со следующими полями:

1. entities — научные сущности, явно упомянутые во фрагменте. Каждая сущность:
   {
     "canonical_name": str,          // каноническое имя (если сущность есть в KNOWN_ENTITIES — используй ровно его)
     "entity_type": один из [
        "Method","Model","Dataset","Metric","Task","Tool","ResearchField","Limitation","Result"
     ],
     "aliases": [str],               // поверхностные формы, как написаны в тексте
     "confidence": float в [0,1]
   }

2. claims — проверяемые научные утверждения (структура subject-predicate-object-condition):
   {
     "claim_text": str,              // ДОСЛОВНОЕ предложение из фрагмента
     "claim_type": один из [
        "definition","method_description","experimental_result","comparison",
        "limitation","hypothesis","conclusion","contradiction_candidate","replication_note"
     ],
     "subject_entity": str,          // канонический субъект
     "predicate": str,               // короткое сказуемое («улучшает», «ограничивается», «использует», «превосходит» …)
     "object_entity": str,           // канонический объект
     "comparison_target": str|null,
     "condition": str|null,          // условие проверки (на каком датасете/метрике)
     "metric": str|null,             // если измеряется
     "value": str|null,              // например "+14%", "0.92 F1", "в 1.7 раза"
     "evidence_text": str,           // то же дословное предложение
     "confidence_score": float в [0,1],
     "evidence_strength": float в [0,1]
   }

3. relations — связи между перечисленными claims (только в пределах текущего фрагмента):
   {
     "source_index": int,            // 0-based индекс в claims[]
     "target_index": int,
     "relation_type": один из ["supports","contradicts","limits","extends"],
     "weight": float в [0,1],
     "rationale": str                // краткое русское обоснование связи
   }

Правила:
- ВЫВОД — это РОВНО один JSON-объект: {"entities":[...],"claims":[...],"relations":[...]}.
- Никаких рассуждений, никакого markdown, никаких комментариев.
- claim_text и evidence_text — это ДОСЛОВНОЕ предложение из фрагмента (без перифраза).
- Если сущность присутствует в KNOWN_ENTITIES — используй именно это каноническое имя.
- Не выдумывай факты. Не извлекай размытые утверждения. Не дублируй claims.
- Названия инструментов сохраняй как в оригинале (PostgreSQL, Qdrant, Neo4j, pgvector, NumPy и т. д.).
- entity_type определяй строго по семантике: алгоритм/метод/подход → Method; СУБД/библиотека/фреймворк → Tool;
  название набора данных → Dataset; численный показатель качества → Metric; задача → Task; математическая
  дисциплина → ResearchField; ограничение метода → Limitation; полученный эффект → Result.
"""


USER_TEMPLATE = """SECTION: {section}
PAGES: {page_start}–{page_end}

KNOWN_ENTITIES (canonical names — normalize matches to these):
{known_entities}

CHUNK:
\"\"\"
{text}
\"\"\"

Return ONLY the JSON object as specified.
"""


@dataclass
class LLMExtractionResult:
    entities: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    relations: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    elapsed_ms: int = 0
    raw_response: str = ""
    prompt_version: str = PROMPT_VERSION
    cached: bool = False


class LLMExtractor:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        app_title: str = "CognitiveBaseAI",
        http_referer: str = "",
        timeout: float = 60.0,
        max_retries: int = 2,
        max_tokens: int = 1800,
        temperature: float = 0.1,
    ) -> None:
        self.api_key = api_key
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.app_title = app_title
        self.http_referer = http_referer
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client: httpx.Client | None = None
        self._cache: dict[str, LLMExtractionResult] = {}

    def is_active(self) -> bool:
        return bool(self.api_key and self.model and self.base_url)

    def provider(self) -> str:
        return self.model or "disabled"

    # ------------------------------------------------------------------
    # Public extraction surface
    # ------------------------------------------------------------------

    def cache_key(self, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:24]
        return f"{self.model}:{PROMPT_VERSION}:{digest}"

    def extract_chunk(
        self,
        *,
        text: str,
        section: str = "Body",
        page_start: int = 1,
        page_end: int = 1,
        known_entities: list[str] | None = None,
    ) -> LLMExtractionResult | None:
        if not self.is_active():
            return None
        key = self.cache_key(text)
        cached = self._cache.get(key)
        if cached is not None:
            cached.cached = True
            return cached
        try:
            return self._call_openrouter(
                text=text,
                section=section,
                page_start=page_start,
                page_end=page_end,
                known_entities=known_entities or [],
                key=key,
            )
        except Exception as exc:
            logger.warning("llm_extract_chunk_failed", extra={"error": str(exc)})
            return None

    def warm_cache(self, key: str, result: LLMExtractionResult) -> None:
        self._cache[key] = result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _call_openrouter(
        self,
        *,
        text: str,
        section: str,
        page_start: int,
        page_end: int,
        known_entities: list[str],
        key: str,
    ) -> LLMExtractionResult | None:
        known_block = (
            ", ".join(sorted({e for e in known_entities if e})[:80]) if known_entities else "(none)"
        )
        user = USER_TEMPLATE.format(
            section=section or "Body",
            page_start=page_start,
            page_end=page_end,
            known_entities=known_block,
            text=text.strip()[:4000],
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.http_referer or "https://github.com/anthropics/claude-code",
            "X-Title": self.app_title,
        }
        client = self._get_client()
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 2):
            try:
                start = time.monotonic()
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage") or {}
                parsed = self._parse_json(content)
                if parsed is None:
                    raise ValueError("LLM returned non-JSON payload")
                elapsed_ms = int((time.monotonic() - start) * 1000)
                result = LLMExtractionResult(
                    entities=self._sanitize_entities(parsed.get("entities", [])),
                    claims=self._sanitize_claims(parsed.get("claims", [])),
                    relations=self._sanitize_relations(parsed.get("relations", [])),
                    model=data.get("model", self.model),
                    tokens_in=int(usage.get("prompt_tokens") or 0),
                    tokens_out=int(usage.get("completion_tokens") or 0),
                    elapsed_ms=elapsed_ms,
                    raw_response=content,
                )
                self._cache[key] = result
                logger.info(
                    "llm_extract_ok",
                    extra={
                        "model": result.model,
                        "tokens_in": result.tokens_in,
                        "tokens_out": result.tokens_out,
                        "claims": len(result.claims),
                        "entities": len(result.entities),
                        "elapsed_ms": elapsed_ms,
                        "attempt": attempt,
                    },
                )
                return result
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code if exc.response is not None else 0
                if status in (429, 500, 502, 503, 504):
                    backoff = 1.0 * (attempt**1.5)
                    logger.warning(
                        "llm_extract_retry",
                        extra={"status": status, "attempt": attempt, "wait": backoff},
                    )
                    time.sleep(backoff)
                    continue
                logger.warning("llm_extract_http_error", extra={"status": status, "body": exc.response.text[:300] if exc.response is not None else ""})
                return None
            except Exception as exc:
                last_error = exc
                logger.warning("llm_extract_parse_error", extra={"error": str(exc), "attempt": attempt})
                if attempt > self.max_retries:
                    return None
                time.sleep(1.0)
        if last_error:
            logger.warning("llm_extract_exhausted", extra={"error": str(last_error)})
        return None

    def _parse_json(self, content: str) -> dict[str, Any] | None:
        if not content:
            return None
        # Direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        # Extract first {...} block
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            block = match.group(0)
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                pass
            # Try sanitising trailing commas
            sanitised = re.sub(r",\s*([\]}])", r"\1", block)
            try:
                return json.loads(sanitised)
            except json.JSONDecodeError:
                pass
        return None

    def _sanitize_entities(self, items: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not isinstance(items, list):
            return out
        allowed_types = {
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
        for raw in items:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("canonical_name") or raw.get("name") or "").strip()
            etype = str(raw.get("entity_type") or "").strip()
            if not name or etype not in allowed_types:
                continue
            aliases = raw.get("aliases") or []
            if not isinstance(aliases, list):
                aliases = []
            aliases = [str(a).strip() for a in aliases if isinstance(a, (str, int, float)) and str(a).strip()]
            confidence = _clamp_float(raw.get("confidence"), default=0.78)
            out.append(
                {
                    "canonical_name": name,
                    "entity_type": etype,
                    "aliases": aliases[:12],
                    "confidence": confidence,
                }
            )
        return out

    def _sanitize_claims(self, items: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not isinstance(items, list):
            return out
        allowed_types = {
            "definition",
            "method_description",
            "experimental_result",
            "comparison",
            "limitation",
            "hypothesis",
            "conclusion",
            "contradiction_candidate",
            "replication_note",
        }
        for raw in items:
            if not isinstance(raw, dict):
                continue
            ct = str(raw.get("claim_type") or "").strip()
            text = str(raw.get("claim_text") or "").strip()
            if not text or ct not in allowed_types:
                continue
            evidence = str(raw.get("evidence_text") or text).strip()
            out.append(
                {
                    "claim_text": text,
                    "claim_type": ct,
                    "subject_entity": str(raw.get("subject_entity") or "").strip() or "Scientific publication",
                    "predicate": str(raw.get("predicate") or "").strip() or "states",
                    "object_entity": str(raw.get("object_entity") or "").strip() or "Research result",
                    "comparison_target": _opt_str(raw.get("comparison_target")),
                    "condition": _opt_str(raw.get("condition")),
                    "metric": _opt_str(raw.get("metric")),
                    "value": _opt_str(raw.get("value")),
                    "evidence_text": evidence,
                    "confidence_score": _clamp_float(raw.get("confidence_score"), default=0.74),
                    "evidence_strength": _clamp_float(raw.get("evidence_strength"), default=0.72),
                }
            )
        return out

    def _sanitize_relations(self, items: Any) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not isinstance(items, list):
            return out
        allowed_types = {"supports", "contradicts", "limits", "extends"}
        for raw in items:
            if not isinstance(raw, dict):
                continue
            rt = str(raw.get("relation_type") or "").strip()
            if rt not in allowed_types:
                continue
            try:
                src = int(raw.get("source_index"))
                tgt = int(raw.get("target_index"))
            except (TypeError, ValueError):
                continue
            if src == tgt:
                continue
            out.append(
                {
                    "source_index": src,
                    "target_index": tgt,
                    "relation_type": rt,
                    "weight": _clamp_float(raw.get("weight"), default=0.6),
                    "rationale": str(raw.get("rationale") or "")[:240],
                }
            )
        return out


def _clamp_float(value: Any, *, default: float, lo: float = 0.05, hi: float = 0.99) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    if num < lo:
        return lo
    if num > hi:
        return hi
    return round(num, 3)


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
