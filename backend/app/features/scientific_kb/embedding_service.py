"""Embedding service.

Tries to load a real sentence-transformer (default
``sentence-transformers/all-MiniLM-L6-v2`` → 384 dim).  If the package or model
is unavailable, falls back transparently to the deterministic hash-based
embedding so the rest of the pipeline keeps working.
"""

from __future__ import annotations

import hashlib
import logging
import math
import threading
from typing import Any

from .utils import deterministic_embedding

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(
        self,
        *,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        target_dim: int = 384,
        mode: str = "auto",
    ) -> None:
        self.model_name = model_name
        self.target_dim = target_dim
        self.mode = mode
        self._model: Any = None
        self._lock = threading.Lock()
        self._cache: dict[str, list[float]] = {}
        if mode == "deterministic":
            self._provider = "deterministic"
        else:
            self._provider = self._try_load_model()

    def _try_load_model(self) -> str:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self.model_name)
            logger.info("embedding_model_loaded", extra={"model": self.model_name})
            return "sentence-transformer"
        except Exception as exc:
            logger.warning("embedding_model_fallback", extra={"error": str(exc)})
            self._model = None
            return "deterministic"

    def provider(self) -> str:
        return self._provider

    def embed(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self.target_dim
        key = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:24]
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            if self._model is not None:
                try:
                    vector = list(map(float, self._model.encode(text, normalize_embeddings=True)))
                    vector = _resize(vector, self.target_dim)
                except Exception as exc:
                    logger.debug("embedding_runtime_fallback", extra={"error": str(exc)})
                    vector = _resize(deterministic_embedding(text), self.target_dim)
            else:
                vector = _resize(deterministic_embedding(text), self.target_dim)
            self._cache[key] = vector
            if len(self._cache) > 4096:
                # simple eviction of arbitrary half to bound memory
                keys = list(self._cache.keys())[: len(self._cache) // 2]
                for k in keys:
                    self._cache.pop(k, None)
            return vector


def _resize(vector: list[float], target_dim: int) -> list[float]:
    if len(vector) == target_dim:
        return vector
    if len(vector) < target_dim:
        return vector + [0.0] * (target_dim - len(vector))
    return _l2_normalize(vector[:target_dim])


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]
