"""Thin wrapper around the Anthropic SDK. Handles retries and JSON parsing."""

from __future__ import annotations

import json
import re
from typing import Any

from anthropic import Anthropic, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
    wait_fixed,
)

from medstudy.config import Settings


class LLMClient:
    """Anthropic Claude client with strict JSON output enforcement."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = Anthropic(api_key=settings.anthropic_api_key)

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int | None = None,
    ) -> Any:
        """Call the model and parse JSON from the response.

        Uses two retry layers: fast retries for transient errors, slow retries
        (65s wait) for rate-limit errors so the per-minute window resets.
        """
        return self._call_rate_limit(system, user, max_tokens=max_tokens)

    @retry(
        stop=stop_after_attempt(6),
        wait=wait_fixed(65),
        retry=retry_if_exception_type(RateLimitError),
        reraise=True,
    )
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=20),
        retry=retry_if_not_exception_type(RateLimitError),
        reraise=True,
    )
    def _call_rate_limit(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int | None = None,
    ) -> Any:
        response = self.client.messages.create(
            model=self.settings.llm_model,
            max_tokens=max_tokens or self.settings.llm_max_tokens,
            temperature=self.settings.llm_temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        return _parse_json(text)


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def _parse_json(text: str) -> Any:
    """Best-effort JSON extraction from a model response."""
    cleaned = _FENCE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Find the first [ or { and the matching last ] or }
        start = min(
            (i for i in (cleaned.find("["), cleaned.find("{")) if i >= 0),
            default=-1,
        )
        end = max(cleaned.rfind("]"), cleaned.rfind("}"))
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise
