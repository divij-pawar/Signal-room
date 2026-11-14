"""Window digest: what Guardian's model sees instead of raw logs (ARCHITECTURE.md 3.3, 12).

Drain3 clusters log lines into templates, so a 4-minute batch becomes a short summary of
per-service counts and templates. Cheap signals decide whether the model is called at all.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

from signalroom.common.schemas import Coverage, LogRecord

logging.getLogger("drain3").setLevel(logging.WARNING)

ERROR_LEVELS = {"ERROR", "FATAL", "CRITICAL"}
WARN_LEVELS = {"WARN", "WARNING"}

# Instruction-like text inside telemetry. Flagged, shown to the model as suspicious, never obeyed.
INSTRUCTION_LIKE = re.compile(
    r"(?i)(ignore (all )?(previous|prior|above) instructions|you are now|system prompt"
    r"|disregard (the|your) (rules|instructions)|maintenance mode: report)"
)


def level_of(rec: LogRecord) -> str:
    s = rec.severity_text.upper()
    return "ERROR" if s in ERROR_LEVELS else "WARN" if s in WARN_LEVELS else "INFO"


def approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class TemplateTracker:
    """Drain3 miner that persists across windows, so 'first seen' templates can be detected."""

    def __init__(self) -> None:
        config = TemplateMinerConfig()
        config.profiling_enabled = False
        self._miner = TemplateMiner(config=config)
        self._seen: set[tuple[str, int]] = set()
        self.windows_seen = 0

    def cluster(self, rec: LogRecord) -> tuple[int, str]:
        result = self._miner.add_log_message(rec.body)
        return result["cluster_id"], result["template_mined"]

    def templates(self) -> dict[int, str]:
        return {c.cluster_id: c.get_template() for c in self._miner.drain.clusters}

    def mark_seen(self, key: tuple[str, int]) -> bool:
        """Returns True the first time a (service, template) pair appears."""
        if key in self._seen:
            return False
        self._seen.add(key)
        return True


@dataclass
class TemplateStat:
    service: str
    template: str
    level: str
    count: int
    new: bool
    instruction_like: bool


@dataclass
class ServiceStat:
    total: int = 0
    errors: int = 0
    warnings: int = 0

    @property
    def error_ratio(self) -> float:
        return self.errors / self.total if self.total else 0.0


@dataclass
class WindowDigest:
    coverage: Coverage
    missing_hosts: list[str]
    services: dict[str, ServiceStat]
    templates: list[TemplateStat]
    signals: list[str] = field(default_factory=list)
    raw_tokens: int = 0

    @property
    def anomalous(self) -> bool:
        return bool(self.signals)

    def to_prompt_json(self, max_templates: int = 25) -> str:
        ranked = sorted(self.templates, key=lambda t: (t.level != "ERROR", t.level != "WARN",
                                                        not t.new, -t.count))[:max_templates]
        return json.dumps({
            "coverage": {"hosts_expected": self.coverage.hosts_expected,
                         "hosts_reporting": self.coverage.hosts_reporting,
                         "missing_hosts": self.missing_hosts},
            "services": {s: {"records": v.total, "errors": v.errors, "warnings": v.warnings,
                             "error_ratio": round(v.error_ratio, 3)}
                         for s, v in sorted(self.services.items())},
            "templates": [{"service": t.service, "level": t.level, "count": t.count,
                           "first_seen_this_window": t.new, "flagged_instruction_like": t.instruction_like,
                           "template": t.template[:300]} for t in ranked],
            "signals": self.signals,
        }, separators=(",", ":"))

    @property
    def digest_tokens(self) -> int:
        return approx_tokens(self.to_prompt_json())


def build_digest(records: list[LogRecord], hosts_expected: list[str], tracker: TemplateTracker,
                 min_errors: int = 5, error_ratio: float = 0.05) -> WindowDigest:
    reporting = {r.host for r in records} & set(hosts_expected)
    coverage = Coverage(hosts_expected=len(hosts_expected), hosts_reporting=len(reporting))
    services: dict[str, ServiceStat] = defaultdict(ServiceStat)
    counts: Counter[tuple[str, int, str]] = Counter()
    flagged: set[tuple[str, int]] = set()

    for r in records:
        lvl = level_of(r)
        st = services[r.service]
        st.total += 1
        st.errors += lvl == "ERROR"
        st.warnings += lvl == "WARN"
        cid, _ = tracker.cluster(r)
        counts[(r.service, cid, lvl)] += 1
        if INSTRUCTION_LIKE.search(r.body):
            flagged.add((r.service, cid))

    # Read templates after the whole window is mined; Drain3 generalizes them as it goes.
    templates = tracker.templates()

    warm_up = tracker.windows_seen == 0
    stats = []
    for (service, cid, lvl), n in counts.items():
        new = tracker.mark_seen((service, cid)) and not warm_up
        stats.append(TemplateStat(service, templates.get(cid, ""), lvl, n, new, (service, cid) in flagged))
    tracker.windows_seen += 1

    signals = []
    for s, st in sorted(services.items()):
        if st.errors >= min_errors and st.error_ratio >= error_ratio:
            signals.append(f"error_rate:{s}")
    for t in stats:
        if t.new and t.level in ("ERROR", "WARN"):
            signals.append(f"new_{t.level.lower()}_template:{t.service}")
    if flagged:
        signals.append("instruction_like_text")

    return WindowDigest(
        coverage=coverage,
        missing_hosts=sorted(set(hosts_expected) - reporting),
        services=dict(services),
        templates=stats,
        signals=sorted(set(signals)),
        # Baseline for the pre-filter metric: the log lines a naive Guardian would send verbatim.
        raw_tokens=sum(approx_tokens(f"{r.timestamp.isoformat()} {r.host} {r.service} "
                                     f"{r.severity_text} {r.body}") for r in records),
    )
