"""
Embedding utilities for text vectorization.

This legacy helper uses OpenRouter. The main Scientific KB pipeline currently
uses deterministic embeddings, but keeping this module provider-neutral prevents
accidental direct-provider key drift.
"""

import os
from typing import List

import requests


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
OPENROUTER_EMBEDDINGS_URL = os.getenv("OPENROUTER_EMBEDDINGS_URL", f"{OPENROUTER_BASE_URL}/embeddings")
OPENROUTER_HTTP_REFERER = os.getenv("OPENROUTER_HTTP_REFERER", "")
OPENROUTER_APP_TITLE = os.getenv("OPENROUTER_APP_TITLE", "CognitiveBaseAI")

EMBEDDING_MODEL = os.getenv("OPENROUTER_EMBEDDING_MODEL", os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small"))
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))


def _openrouter_headers() -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    }
    if OPENROUTER_HTTP_REFERER:
        headers["HTTP-Referer"] = OPENROUTER_HTTP_REFERER
    if OPENROUTER_APP_TITLE:
        headers["X-OpenRouter-Title"] = OPENROUTER_APP_TITLE
    return headers


def generate_embedding(text: str) -> List[float]:
    """
    Generate an embedding vector from text using OpenRouter.

    Returns a zero vector when OPENROUTER_API_KEY is not configured so tests and
    local demos can run without paid provider credentials.
    """
    if not text or not text.strip():
        raise ValueError("Text cannot be empty")

    if not OPENROUTER_API_KEY:
        print("Warning: OPENROUTER_API_KEY not configured, returning zero vector")
        return [0.0] * EMBEDDING_DIMENSIONS

    try:
        response = requests.post(
            OPENROUTER_EMBEDDINGS_URL,
            headers=_openrouter_headers(),
            json={
                "input": text,
                "model": EMBEDDING_MODEL,
                "dimensions": EMBEDDING_DIMENSIONS,
            },
            timeout=30,
        )

        if response.status_code != 200:
            raise RuntimeError(f"OpenRouter API returned status {response.status_code}: {response.text}")

        result = response.json()
        if "data" not in result or len(result["data"]) == 0:
            raise RuntimeError("Invalid response format from OpenRouter API")

        return result["data"][0]["embedding"]

    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Failed to connect to OpenRouter API: {exc}") from exc


def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """
    Generate embedding vectors for multiple texts using OpenRouter.
    """
    if not texts:
        raise ValueError("Texts list cannot be empty")

    if not OPENROUTER_API_KEY:
        print("Warning: OPENROUTER_API_KEY not configured, returning zero vectors")
        return [[0.0] * EMBEDDING_DIMENSIONS for _ in texts]

    try:
        response = requests.post(
            OPENROUTER_EMBEDDINGS_URL,
            headers=_openrouter_headers(),
            json={
                "input": texts,
                "model": EMBEDDING_MODEL,
                "dimensions": EMBEDDING_DIMENSIONS,
            },
            timeout=60,
        )

        if response.status_code != 200:
            raise RuntimeError(f"OpenRouter API returned status {response.status_code}: {response.text}")

        result = response.json()
        if "data" not in result:
            raise RuntimeError("Invalid response format from OpenRouter API")

        data = sorted(result["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in data]

    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Failed to connect to OpenRouter API: {exc}") from exc


def get_embedding_info() -> dict:
    """
    Get information about current embedding configuration.
    """
    return {
        "model": EMBEDDING_MODEL,
        "dimensions": EMBEDDING_DIMENSIONS,
        "api_configured": bool(OPENROUTER_API_KEY),
        "api_url": OPENROUTER_EMBEDDINGS_URL,
    }
