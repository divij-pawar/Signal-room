"""Read-only telemetry interface used by Guardian and RCA (ARCHITECTURE.md section 3.2).

The eval harness replays recorded fixtures through `InMemoryTelemetry`. A Maple-backed
implementation will expose the same methods; agents only ever see this interface.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .schemas import LogRecord, TimeWindow


def record_ref(rec: LogRecord) -> str:
    """Stable reference to one log record, used as the `ref` of cited evidence."""
    return f"log:{rec.service}:{rec.timestamp.isoformat()}"


class Telemetry(Protocol):
    def query_logs(self, window: TimeWindow, *, service: str | None = None,
                   trace_id: str | None = None, limit: int = 500) -> list[LogRecord]: ...

    def get_record(self, ref: str) -> LogRecord | None: ...


class InMemoryTelemetry:
    def __init__(self, records: Iterable[LogRecord]):
        self._records = sorted(records, key=lambda r: r.timestamp)
        self._by_ref = {record_ref(r): r for r in self._records}

    @classmethod
    def from_jsonl(cls, path: str | Path) -> InMemoryTelemetry:
        with open(path) as f:
            return cls(LogRecord.model_validate(json.loads(line)) for line in f if line.strip())

    @property
    def records(self) -> list[LogRecord]:
        return list(self._records)

    def span(self) -> tuple[datetime, datetime]:
        return self._records[0].timestamp, self._records[-1].timestamp

    def query_logs(self, window: TimeWindow, *, service: str | None = None,
                   trace_id: str | None = None, limit: int = 500) -> list[LogRecord]:
        out = []
        for r in self._records:
            if not window.contains(r.timestamp):
                continue
            if service is not None and r.service != service:
                continue
            if trace_id is not None and r.trace_id != trace_id:
                continue
            out.append(r)
            if len(out) >= limit:
                break
        return out

    def get_record(self, ref: str) -> LogRecord | None:
        return self._by_ref.get(ref)
