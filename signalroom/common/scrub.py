"""Secret scrubbing, applied before every model call and before every Slack post."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

REDACTED = "[REDACTED]"

# Order matters: the broad key=value rule runs last so specific formats are counted correctly.
_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        REDACTED,
    ),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"), REDACTED),
    ("bearer", re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + REDACTED),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), REDACTED),
    (
        "api_key",
        re.compile(
            r"\b(?:sk-(?:or-v1-|proj-|ant-)?[A-Za-z0-9_-]{16,}"
            r"|gh[pousr]_[A-Za-z0-9]{20,}"
            r"|xox[abprs]-[A-Za-z0-9-]{10,}"
            r"|AIza[0-9A-Za-z_-]{30,})"
        ),
        REDACTED,
    ),
    ("url_credentials", re.compile(r"(://[^/\s:@]+):[^@\s/]+@"), r"\1:" + REDACTED + "@"),
    (
        "key_value",
        re.compile(
            r"""(?ix)
            (["']?\b(?:password|passwd|pwd|secret|client_secret|token|access_token|refresh_token
                |api[_-]?key|access[_-]?key|private[_-]?key)\b["']?\s*[:=]\s*)
            (["']?)(?!\[REDACTED\])[^\s"',;}&]{3,}\2
            """
        ),
        r"\1\2" + REDACTED + r"\2",
    ),
]


@dataclass(frozen=True)
class ScrubResult:
    text: str
    counts: Counter[str] = field(default_factory=Counter)

    @property
    def redacted(self) -> int:
        return sum(self.counts.values())


def scrub(text: str) -> ScrubResult:
    counts: Counter[str] = Counter()
    for kind, pattern, replacement in _PATTERNS:
        text, n = pattern.subn(replacement, text)
        if n:
            counts[kind] += n
    return ScrubResult(text, counts)
