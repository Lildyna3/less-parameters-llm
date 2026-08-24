"""AI provider abstraction.

ARES is not coupled to one vendor. Providers implement `narrate()` — turning
a structured, evidence-based analysis (built by the deterministic analysis
engine) into natural language. The LLM never invents bias, confidence, or
levels; those come from measurable evidence and are passed in.

When no provider/key is configured, the AI component is truthfully OFFLINE
and the Command Center falls back to a deterministic narrator (clearly not
an LLM, but also not fake — it renders the same structured evidence).

Secrets: API keys come from env only, are registered with the log redactor,
and are never sent to the frontend. MT5 credentials are never included in
any AI request.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

import httpx

from ..config import AISettings
from ..logging_setup import get_logger, register_secret
from ..status import ComponentState, status_registry

log = get_logger("ai")

SYSTEM_STYLE = (
    "You are ARES, an AI trading intelligence analyst. You are given a JSON "
    "analysis produced by a deterministic engine from real market data. "
    "Narrate it concisely and conversationally — confident, analytical, a "
    "little casual, but clear and professional about risk. Never change the "
    "bias, confidence score, or levels. Never invent data that is not in the "
    "JSON. 2–6 short paragraphs max, minimal emoji."
)


class AIProvider(ABC):
    name = "none"

    @abstractmethod
    async def narrate(self, analysis: dict, question: str | None = None) -> str: ...

    async def verify(self) -> tuple[bool, str]:
        """Cheap connectivity/auth check; providers may override."""
        return True, "ok"


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, settings: AISettings) -> None:
        self.key = settings.api_key or ""
        self.model = settings.model or "gemini-2.0-flash"
        self.timeout = settings.timeout_seconds
        register_secret(self.key)

    async def narrate(self, analysis: dict, question: str | None = None) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        prompt = SYSTEM_STYLE + "\n\nANALYSIS JSON:\n" + json.dumps(analysis)
        if question:
            prompt += f"\n\nUSER QUESTION: {question}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                url, params={"key": self.key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
            )
            resp.raise_for_status()
            data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    async def verify(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    params={"key": self.key, "pageSize": 1},
                )
            if resp.status_code == 200:
                return True, "Gemini API reachable and key accepted"
            return False, f"Gemini API returned HTTP {resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, f"Gemini API unreachable: {exc}"


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, settings: AISettings) -> None:
        self.key = settings.api_key or ""
        self.model = settings.model or "gpt-4o-mini"
        self.timeout = settings.timeout_seconds
        register_secret(self.key)

    async def narrate(self, analysis: dict, question: str | None = None) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_STYLE},
            {"role": "user", "content": "ANALYSIS JSON:\n" + json.dumps(analysis)
             + (f"\n\nUSER QUESTION: {question}" if question else "")},
        ]
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.key}"},
                json={"model": self.model, "messages": messages},
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def verify(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {self.key}"},
                )
            if resp.status_code == 200:
                return True, "OpenAI API reachable and key accepted"
            return False, f"OpenAI API returned HTTP {resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, f"OpenAI API unreachable: {exc}"


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, settings: AISettings) -> None:
        self.key = settings.api_key or ""
        self.model = settings.model or "claude-haiku-4-5-20251001"
        self.timeout = settings.timeout_seconds
        register_secret(self.key)

    async def narrate(self, analysis: dict, question: str | None = None) -> str:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                json={
                    "model": self.model,
                    "max_tokens": 1000,
                    "system": SYSTEM_STYLE,
                    "messages": [{"role": "user", "content": "ANALYSIS JSON:\n" + json.dumps(analysis)
                                  + (f"\n\nUSER QUESTION: {question}" if question else "")}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return data["content"][0]["text"]

    async def verify(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"},
                )
            if resp.status_code == 200:
                return True, "Anthropic API reachable and key accepted"
            return False, f"Anthropic API returned HTTP {resp.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, f"Anthropic API unreachable: {exc}"


async def build_provider(settings: AISettings) -> AIProvider | None:
    """Instantiate + genuinely verify the configured provider. Publishes the
    real AI component status either way."""
    if settings.provider == "none" or not settings.api_key:
        status_registry.set(
            "ai", ComponentState.OFFLINE,
            "No AI provider configured — structured analysis remains available; "
            "set ARES_AI__PROVIDER and an API key in .env to enable narration.",
        )
        return None

    provider: AIProvider
    if settings.provider == "gemini":
        provider = GeminiProvider(settings)
    elif settings.provider == "openai":
        provider = OpenAIProvider(settings)
    elif settings.provider == "anthropic":
        provider = AnthropicProvider(settings)
    else:
        status_registry.set("ai", ComponentState.OFFLINE, f"Unknown AI provider '{settings.provider}'")
        return None

    ok, reason = await provider.verify()
    if ok:
        status_registry.set("ai", ComponentState.ONLINE, reason, {"provider": provider.name})
        return provider
    status_registry.set("ai", ComponentState.OFFLINE, reason, {"provider": provider.name})
    log.warning("AI provider %s failed verification: %s", provider.name, reason)
    return None
