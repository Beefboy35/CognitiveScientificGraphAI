from __future__ import annotations

import hashlib
import math
import re
import uuid
from datetime import datetime, timezone

from .ontology import ALIASES

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _stable_id(prefix: str, *parts: str | int | None, length: int = 16) -> str:
    """Идемпотентный id, derived from content.

    Гарантирует, что повторная обработка той же публикации/чанка/сущности
    даёт тот же id — это устраняет дубликаты в Neo4j между рестартами
    backend и делает MERGE-операции по-настоящему idempotent.
    """
    payload = "|".join("" if p is None else str(p) for p in parts)
    digest = hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Zа-яА-Я0-9@+\-]+", text.lower())


def _expanded_query_tokens(text: str) -> list[str]:
    tokens = _tokenize(text)
    expanded = list(tokens)
    for token in tokens:
        canonical = ALIASES.get(token)
        if canonical:
            expanded.extend(_tokenize(canonical))
        if token.endswith("s") and len(token) > 4:
            expanded.append(token[:-1])
        if token.endswith("es") and len(token) > 5:
            expanded.append(token[:-2])
    return expanded


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 24]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def deterministic_embedding(text: str, dim: int = 64) -> list[float]:
    vector = [0.0] * dim
    for token in _tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "big") % dim
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[idx] += sign * (1.0 + min(len(token), 16) / 16.0)
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [round(v / norm, 6) for v in vector]
