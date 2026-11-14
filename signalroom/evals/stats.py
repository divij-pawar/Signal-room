"""Small statistics helpers (EVALS.md section 12)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Proportion:
    k: int
    n: int
    p: float | None
    lo: float | None
    hi: float | None

    def as_dict(self) -> dict:
        return {"k": self.k, "n": self.n, "p": self.p, "ci95": [self.lo, self.hi]}


def wilson(k: int, n: int, z: float = 1.96) -> Proportion:
    """Wilson score interval; behaves sensibly for small n and for k = 0 or k = n."""
    if n == 0:
        return Proportion(k, n, None, None, None)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return Proportion(k, n, p, max(0.0, centre - half), min(1.0, centre + half))


def median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
