import json
from pathlib import Path

from signalroom.evals.export import main

SCENARIOS = Path(__file__).resolve().parent.parent / "evals" / "scenarios"


def test_export_writes_scrubbed_bundles(tmp_path):
    assert main(["--split", "selftest", "--scenarios", str(SCENARIOS), "--out", str(tmp_path)]) == 0
    index = json.loads((tmp_path / "index.json").read_text())
    assert not index["reportable"]
    assert {e["id"] for e in index["scenarios"]} == {p.stem for p in SCENARIOS.glob("selftest-*.yaml")}

    raw = (tmp_path / "selftest-injection.json").read_text()
    assert "S3cr3tPassw0rd" not in raw  # planted secret never published
    bundle = json.loads(raw)
    assert bundle["guardrails"]["redactions"] == {"url_credentials": 1}
    assert bundle["guardrails"]["instruction_like_refs"]
    assert len(bundle["windows"]) == bundle["scenario"]["windows"]
    assert bundle["incident"]["slack"]["posted"] in (True, False)
    assert "[REDACTED]" in bundle["incident"]["slack"]["text"]


def test_export_refuses_heldout(tmp_path):
    assert main(["--split", "heldout", "--scenarios", str(SCENARIOS), "--out", str(tmp_path)]) == 2
