from __future__ import annotations

import os

import httpx

from app import config
from app.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS = 20.0

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")


class ProviderError(Exception):
    """Raised when a single provider call fails (network, HTTP, or shape)."""


class AllProvidersFailedError(Exception):

    def __init__(self, attempts: list[tuple[str, str]]):
        self.attempts = attempts
        detail = "; ".join(f"{name}: {err}" for name, err in attempts)
        super().__init__(f"all LLM providers failed -> {detail}")


async def _call_groq(messages: list[dict], api_key: str, timeout: float) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    body = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, headers=headers, json=body)
        except httpx.RequestError as exc:
            raise ProviderError(f"network error calling Groq: {exc}") from exc
    if resp.status_code != 200:
        raise ProviderError(f"Groq returned HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"unexpected Groq response shape: {data}") from exc


async def _call_gemini(messages: list[dict], api_key: str, timeout: float) -> str:
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    user_parts = [m["content"] for m in messages if m["role"] != "system"]
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={api_key}"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": text}]} for text in user_parts],
        "generationConfig": {"temperature": 0},
    }
    if system_parts:
        body["system_instruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, json=body)
        except httpx.RequestError as exc:
            raise ProviderError(f"network error calling Gemini: {exc}") from exc
    if resp.status_code != 200:
        raise ProviderError(f"Gemini returned HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"unexpected Gemini response shape: {data}") from exc


_CALLERS = {
    "groq": (_call_groq, "GROQ_API_KEY"),
    "gemini": (_call_gemini, "GEMINI_API_KEY"),
}


def _provider_order() -> list[str]:
    primary = (config.LLM_PROVIDER or "").strip().lower()
    order = [primary] if primary in _CALLERS else []
    order += [name for name in _CALLERS if name not in order]
    return order


async def complete_with_provider(
    messages: list[dict], timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> tuple[str, str]:
    attempts: list[tuple[str, str]] = []
    for name in _provider_order():
        caller, key_env = _CALLERS[name]
        api_key = getattr(config, key_env, "").strip()
        if not api_key:
            attempts.append((name, f"no {key_env} configured"))
            continue
        try:
            result = await caller(messages, api_key, timeout)
            logger.info("LLM request answered by provider=%s", name)
            return name, result
        except ProviderError as exc:
            logger.warning("Provider %s failed, trying next: %s", name, exc)
            attempts.append((name, str(exc)))
            continue
    logger.error("All LLM providers failed: %s", attempts)
    raise AllProvidersFailedError(attempts)


async def complete(messages: list[dict], timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    _, text = await complete_with_provider(messages, timeout)
    return text
