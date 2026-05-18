from __future__ import annotations

from typing import Any, Literal, TypedDict

import httpx

from app.config.settings import settings


Role = Literal["system", "user", "assistant", "tool"]


class ChatMessage(TypedDict):
    role: Role
    content: str


def openrouter_headers() -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }
    if settings.openrouter_http_referer:
        headers["HTTP-Referer"] = settings.openrouter_http_referer
    if settings.openrouter_app_title:
        headers["X-OpenRouter-Title"] = settings.openrouter_app_title
    return headers


async def create_chat_completion(
    messages: list[ChatMessage],
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float = 60,
) -> dict[str, Any]:
    api_key = settings.openrouter_api_key.get_secret_value()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    selected_model = model or settings.openrouter_model
    if not selected_model:
        raise RuntimeError("OPENROUTER_MODEL is not configured")

    payload: dict[str, Any] = {
        "model": selected_model,
        "messages": messages,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    base_url = settings.openrouter_base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers=openrouter_headers(),
            json=payload,
        )
        response.raise_for_status()
        return response.json()
