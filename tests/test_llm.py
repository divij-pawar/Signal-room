import json

import httpx
import pytest

from signalroom.common.config import ModelsConfig
from signalroom.common.llm import (
    BudgetExceeded,
    InvalidModelOutput,
    ModelClient,
    ModelUnavailable,
    extract_json,
)
from signalroom.common.schemas import Confidence, RCAReport


def make_config(providers=None, **budget) -> ModelsConfig:
    providers = providers or [{"name": "primary", "base_url": "https://primary.test/v1", "model": "m1",
                               "api_key_env": "KEY", "price_in_per_m": 1.0, "price_out_per_m": 2.0}]
    return ModelsConfig.model_validate({
        "budget": {"daily_requests": 100, "daily_tokens": 10**7, "daily_usd": 10.0} | budget,
        "roles": {"rca": {"providers": providers}},
    })


def reply(content: str, tokens_in: int = 1000, tokens_out: int = 500) -> httpx.Response:
    return httpx.Response(200, json={
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
    })


def client(handler, config=None, **kw) -> tuple[ModelClient, list]:
    records = []
    c = ModelClient(config or make_config(), transport=httpx.MockTransport(handler),
                    recorder=records.append, sleep=lambda s: None, env={"KEY": "k", "KEY2": "k2"}, **kw)
    return c, records


MSG = [{"role": "user", "content": "hi"}]


def test_success_records_tokens_and_cost():
    c, records = client(lambda req: reply("hello"))
    result = c.chat("rca", MSG)
    assert result.content == "hello"
    assert records[0].ok and records[0].tokens_in == 1000
    assert result.record.cost_usd == pytest.approx((1000 * 1.0 + 500 * 2.0) / 1e6)


def test_secrets_are_scrubbed_before_leaving():
    sent = []

    def handler(req):
        sent.append(json.loads(req.content))
        assert req.headers["Authorization"] == "Bearer k"
        return reply("ok")

    c, records = client(handler)
    c.chat("rca", [{"role": "user", "content": "db at postgres://app:S3cr3tPassw0rd@db/shop"}])
    assert "S3cr3tPassw0rd" not in json.dumps(sent)
    assert records[0].redactions == 1


def test_retries_rate_limit_then_succeeds():
    calls = iter([httpx.Response(429), reply("ok")])
    c, records = client(lambda req: next(calls))
    assert c.chat("rca", MSG).content == "ok"
    assert [r.status for r in records] == [429, 200]


def test_falls_back_to_next_provider():
    config = make_config(providers=[
        {"name": "primary", "base_url": "https://primary.test/v1", "model": "gone", "api_key_env": "KEY"},
        {"name": "backup", "base_url": "https://backup.test/v1", "model": "m2", "api_key_env": "KEY2"},
    ])

    def handler(req):
        return httpx.Response(404) if req.url.host == "primary.test" else reply("from backup")

    c, records = client(handler, config)
    result = c.chat("rca", MSG)
    assert result.record.provider == "backup"
    assert [r.provider for r in records] == ["primary", "backup"]


def test_missing_key_skips_provider_and_all_failures_raise():
    config = make_config(providers=[
        {"name": "p", "base_url": "https://p.test/v1", "model": "m", "api_key_env": "ABSENT"},
    ])
    c, records = client(lambda req: reply("never"), config)
    with pytest.raises(ModelUnavailable, match="missing env var ABSENT"):
        c.chat("rca", MSG)


def test_timeouts_and_empty_replies_are_failures():
    def handler(req):
        raise httpx.ReadTimeout("slow", request=req)

    c, _ = client(handler, max_retries=1)
    with pytest.raises(ModelUnavailable, match="timeout"):
        c.chat("rca", MSG)

    c, _ = client(lambda req: reply("   "), max_retries=0)
    with pytest.raises(ModelUnavailable, match="empty response"):
        c.chat("rca", MSG)


def test_budget_stops_calls():
    c, _ = client(lambda req: reply("ok"), make_config(daily_requests=1))
    c.chat("rca", MSG)
    with pytest.raises(BudgetExceeded):
        c.chat("rca", MSG)


REPORT = {"severity": "sev2", "root_cause_service": "payment", "root_cause_category": "config",
          "root_cause": "bad config", "confidence": "high"}


def test_chat_json_validates_and_repairs_once():
    calls = iter([reply("<think>hmm</think> not json"), reply("```json\n" + json.dumps(REPORT) + "\n```")])
    c, records = client(lambda req: next(calls))
    report = c.chat_json("rca", MSG, RCAReport)
    assert report.confidence is Confidence.HIGH
    assert len(records) == 2


def test_chat_json_gives_up_after_one_repair():
    c, _ = client(lambda req: reply('{"severity": "none"}'))
    with pytest.raises(InvalidModelOutput):
        c.chat_json("rca", MSG, RCAReport)


def test_extract_json():
    assert json.loads(extract_json('<think>{"x": 1}</think>Answer: {"a": 1}')) == {"a": 1}
    with pytest.raises(ValueError):
        extract_json("no braces here")


def test_rate_limit_honors_retry_after():
    waits = []
    calls = iter([httpx.Response(429, headers={"Retry-After": "7"}), reply("ok")])
    c = ModelClient(make_config(), transport=httpx.MockTransport(lambda req: next(calls)),
                    sleep=waits.append, env={"KEY": "k"})
    assert c.chat("rca", MSG).content == "ok"
    assert waits == [7.0]
