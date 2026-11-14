import os

from signalroom.common.config import ModelsConfig
from signalroom.common.env import load_dotenv
from signalroom.evals.runner import _key_problems


def test_load_dotenv_sets_missing_names_only(tmp_path, monkeypatch):
    monkeypatch.setenv("ALREADY_SET", "keep")
    monkeypatch.delenv("SR_TEST_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("# comment\nexport SR_TEST_KEY='abc'\nALREADY_SET=override\n")
    assert load_dotenv(env) == ["SR_TEST_KEY"]
    assert os.environ["SR_TEST_KEY"] == "abc" and os.environ["ALREADY_SET"] == "keep"
    monkeypatch.delenv("SR_TEST_KEY")


def test_key_problems_never_echo_the_key(monkeypatch):
    monkeypatch.delenv("SR_MISSING", raising=False)
    config = ModelsConfig.model_validate({
        "budget": {"daily_requests": 1, "daily_tokens": 1, "daily_usd": 1},
        "roles": {"rca": {"providers": [
            {"name": "a", "base_url": "https://x/v1", "model": "m", "api_key_env": "sk-or-v1-secretvalue"},
            {"name": "b", "base_url": "https://x/v1", "model": "m", "api_key_env": "SR_MISSING"}]}},
    })
    problems = _key_problems(config)
    assert len(problems) == 2
    assert not any("secretvalue" in p for p in problems)
