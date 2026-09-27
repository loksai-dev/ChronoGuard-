from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from openrouter import OpenRouter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings, get_settings
from app.observability.logging import get_logger
from app.observability.metrics import OPENROUTER_LATENCY

logger = get_logger(__name__)


class OpenRouterError(Exception):
    """Raised when OpenRouter returns a non-retryable error."""


class OpenRouterTransientError(OpenRouterError):
    """Raised for timeouts and 429/5xx responses."""


class OpenRouterClient:
    """Real OpenRouter gateway for Jev Decisions and chat completions."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        key = self.settings.openrouter_api_key.get_secret_value()
        if not key:
            raise OpenRouterError(
                "OPENROUTER_API_KEY is not configured. ChronoGuard will not invent Jev decisions."
            )
        self._api_key = key
        self._timeout = self.settings.openrouter_timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.openrouter_http_referer,
            "X-Title": self.settings.openrouter_app_title,
        }

    async def create_decision(
        self,
        *,
        model: str,
        state: dict[str, Any] | str,
        questions: dict[str, Any],
        trace_id: str | None = None,
    ) -> tuple[dict[str, Any], float]:
        payload: dict[str, Any] = {
            "model": model,
            "state": state,
            "questions": questions,
        }
        if trace_id:
            payload["trace"] = {"trace_id": trace_id, "trace_name": "chronoguard-jev"}

        started = time.perf_counter()
        body = await self._post_json(self.settings.openrouter_decisions_url, payload)
        latency_ms = (time.perf_counter() - started) * 1000
        OPENROUTER_LATENCY.observe(latency_ms / 1000)
        return body, latency_ms

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> tuple[str, dict[str, Any], float]:
        started = time.perf_counter()

        def _send() -> Any:
            with OpenRouter(
                api_key=self._api_key,
                http_referer=self.settings.openrouter_http_referer,
                x_open_router_title=self.settings.openrouter_app_title,
            ) as client:
                return client.chat.send(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                )

        try:
            response = await asyncio.to_thread(_send)
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            OPENROUTER_LATENCY.observe(latency_ms / 1000)
            raise OpenRouterError(f"OpenRouter chat failed: {exc}") from exc

        latency_ms = (time.perf_counter() - started) * 1000
        OPENROUTER_LATENCY.observe(latency_ms / 1000)
        content = _extract_chat_content(response)
        usage = _extract_usage(response)
        return content, usage, latency_ms

    async def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        attempts = max(1, self.settings.openrouter_max_retries + 1)

        @retry(
            reraise=True,
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=0.4, min=0.4, max=4),
            retry=retry_if_exception_type(OpenRouterTransientError),
        )
        async def _call() -> dict[str, Any]:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(url, headers=self._headers(), json=payload)
            except httpx.TimeoutException as exc:
                raise OpenRouterTransientError("OpenRouter request timed out") from exc
            except httpx.TransportError as exc:
                raise OpenRouterTransientError(f"OpenRouter transport error: {exc}") from exc

            if response.status_code in {429, 500, 502, 503, 524, 529}:
                raise OpenRouterTransientError(
                    f"OpenRouter transient {response.status_code}: {response.text[:500]}"
                )
            if response.status_code >= 400:
                raise OpenRouterError(
                    f"OpenRouter error {response.status_code}: {response.text[:800]}"
                )
            try:
                return response.json()
            except ValueError as exc:
                raise OpenRouterError("OpenRouter returned non-JSON body") from exc

        return await _call()


def _extract_chat_content(response: Any) -> str:
    if isinstance(response, dict):
        choices = response.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content
    choices = getattr(response, "choices", None)
    if choices:
        first = choices[0]
        message = getattr(first, "message", None)
        content = getattr(message, "content", None) if message else None
        if isinstance(content, str):
            return content
        if isinstance(first, dict):
            return str((first.get("message") or {}).get("content") or "")
    return str(response)


def _extract_usage(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return usage
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }
