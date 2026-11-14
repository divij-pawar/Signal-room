"""Model provider client (ARCHITECTURE.md section 3.6).

Guardian and RCA call `ModelClient.chat` and never a vendor SDK. Every provider speaks the
OpenAI-compatible chat completions API (OpenRouter, Ollama), so one code path covers hosted
and local models. The client scrubs secrets before each call, enforces the daily budget,
retries with backoff, falls through the provider chain, and records every attempt.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import BudgetConfig, ModelsConfig, ProviderConfig
from .scrub import scrub

T = TypeVar("T", bound=BaseModel)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class ModelUnavailable(RuntimeError):
    """No provider in the chain produced a response. Callers report unknown or "no RCA"."""


class BudgetExceeded(ModelUnavailable):
    """The daily request, token or spend budget is used up."""


class InvalidModelOutput(RuntimeError):
    """The model's output failed schema validation, even after one repair attempt."""


@dataclass(frozen=True)
class CallRecord:
    """One attempt against one provider. Feeds the cost log and the audit trail."""

    role: str
    provider: str
    model: str
    started_at: datetime
    latency_s: float
    ok: bool
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    status: int | None = None
    retry_after_s: float | None = None
    error: str | None = None
    redactions: int = 0


@dataclass(frozen=True)
class ChatResult:
    content: str
    record: CallRecord


class InMemoryBudget:
    """Daily budget kept in process. The Postgres-backed budget shares this interface."""

    def __init__(self, config: BudgetConfig, today: Callable[[], date] = date.today):
        self._config = config
        self._today = today
        self._day = today()
        self.requests = 0
        self.tokens = 0
        self.usd = 0.0

    def _roll(self) -> None:
        if self._today() != self._day:
            self._day = self._today()
            self.requests, self.tokens, self.usd = 0, 0, 0.0

    def check(self) -> None:
        self._roll()
        c = self._config
        if self.requests >= c.daily_requests:
            raise BudgetExceeded("daily request budget used up")
        if self.tokens >= c.daily_tokens:
            raise BudgetExceeded("daily token budget used up")
        if self.usd >= c.daily_usd:
            raise BudgetExceeded("daily spend budget used up")

    def record(self, rec: CallRecord) -> None:
        self._roll()
        self.requests += 1
        self.tokens += rec.tokens_in + rec.tokens_out
        self.usd += rec.cost_usd


@dataclass
class ModelClient:
    config: ModelsConfig
    budget: InMemoryBudget | None = None
    transport: httpx.BaseTransport | None = None
    recorder: Callable[[CallRecord], None] | None = None
    max_retries: int = 2
    backoff_s: float = 1.0
    max_wait_s: float = 60.0
    sleep: Callable[[float], None] = time.sleep
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))

    def __post_init__(self) -> None:
        if self.budget is None:
            self.budget = InMemoryBudget(self.config.budget)
        self._http = httpx.Client(transport=self.transport)

    def chat(self, role: str, messages: list[dict[str, str]]) -> ChatResult:
        role_cfg = self.config.roles[role]
        redactions = 0
        clean: list[dict[str, str]] = []
        for m in messages:
            result = scrub(m["content"])
            redactions += result.redacted
            clean.append({"role": m["role"], "content": result.text})

        errors: list[str] = []
        for provider in role_cfg.providers:
            for attempt in range(self.max_retries + 1):
                self.budget.check()
                rec, content = self._call(role, provider, clean, role_cfg.temperature,
                                          role_cfg.max_output_tokens, redactions)
                self.budget.record(rec)
                if self.recorder:
                    self.recorder(rec)
                if rec.ok:
                    return ChatResult(content, rec)
                errors.append(f"{provider.name}: {rec.error}")
                if rec.status not in RETRYABLE_STATUS or attempt == self.max_retries:
                    break
                # Free tiers rate-limit hard; honor the provider's Retry-After when given.
                wait = max(self.backoff_s * 2**attempt, rec.retry_after_s or 0)
                self.sleep(min(wait, self.max_wait_s))
        raise ModelUnavailable("; ".join(errors) or "no providers configured")

    def chat_json(self, role: str, messages: list[dict[str, str]], schema: type[T]) -> T:
        """Chat, then validate the reply against `schema`, with one repair attempt."""
        result = self.chat(role, messages)
        try:
            return schema.model_validate_json(extract_json(result.content))
        except (ValidationError, ValueError) as first_error:
            repair = messages + [
                {"role": "assistant", "content": result.content},
                {"role": "user", "content": (
                    "Your reply did not match the required JSON schema. Error:\n"
                    f"{first_error}\nReply again with only the corrected JSON object."
                )},
            ]
            result = self.chat(role, repair)
            try:
                return schema.model_validate_json(extract_json(result.content))
            except (ValidationError, ValueError) as e:
                raise InvalidModelOutput(str(e)) from e

    def _call(self, role: str, provider: ProviderConfig, messages: list[dict[str, str]],
              temperature: float, max_tokens: int, redactions: int) -> tuple[CallRecord, str]:
        started = datetime.now(timezone.utc)
        t0 = time.monotonic()

        def record(ok: bool, **kw) -> CallRecord:
            return CallRecord(role=role, provider=provider.name, model=provider.model,
                              started_at=started, latency_s=time.monotonic() - t0, ok=ok,
                              redactions=redactions, **kw)

        headers = {"Content-Type": "application/json"}
        if provider.api_key_env:
            key = self.env.get(provider.api_key_env)
            if not key:
                return record(False, error=f"missing env var {provider.api_key_env}"), ""
            headers["Authorization"] = f"Bearer {key}"

        body = {"model": provider.model, "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens}
        try:
            resp = self._http.post(f"{provider.base_url.rstrip('/')}/chat/completions",
                                   json=body, headers=headers, timeout=provider.timeout_s)
        except httpx.TimeoutException:
            return record(False, status=408, error="timeout"), ""
        except httpx.HTTPError as e:
            return record(False, status=503, error=f"transport error: {type(e).__name__}"), ""

        if resp.status_code != 200:
            return record(False, status=resp.status_code, error=f"HTTP {resp.status_code}",
                          retry_after_s=_retry_after(resp)), ""
        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError):
            return record(False, status=502, error="malformed response"), ""
        if not content.strip():
            return record(False, status=502, error="empty response"), ""

        usage = data.get("usage") or {}
        tokens_in = int(usage.get("prompt_tokens", 0))
        tokens_out = int(usage.get("completion_tokens", 0))
        return record(True, status=200, tokens_in=tokens_in, tokens_out=tokens_out,
                      cost_usd=provider.cost_usd(tokens_in, tokens_out)), content


def _retry_after(resp: httpx.Response) -> float | None:
    try:
        return float(resp.headers["retry-after"])
    except (KeyError, ValueError):
        return None


_THINK = re.compile(r"<think>.*?</think>", re.S)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> str:
    """Pull the JSON object out of a model reply (drops reasoning blocks and code fences)."""
    text = _THINK.sub("", text).strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object in model reply")
    candidate = text[start:end + 1]
    json.loads(candidate)  # fail early with a clear error
    return candidate
