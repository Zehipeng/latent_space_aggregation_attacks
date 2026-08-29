from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

UnitStatus = Literal["PENDING", "RUNNING", "COMPLETE", "FAILED"]


@dataclass(frozen=True)
class LedgerEvent:
    unit_id: str
    status: UnitStatus
    detail: str = ""
    timestamp: str = ""

    def record(self) -> dict[str, str]:
        value = asdict(self)
        value["timestamp"] = self.timestamp or datetime.now(timezone.utc).isoformat()
        return value


def append_event(path: str | Path, event: LedgerEvent) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(event.record(), ensure_ascii=False, allow_nan=False) + "\n"
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def read_latest_states(path: str | Path) -> dict[str, UnitStatus]:
    source = Path(path)
    if not source.exists():
        return {}
    states: dict[str, UnitStatus] = {}
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        try:
            event = json.loads(line)
            states[event["unit_id"]] = event["status"]
        except (json.JSONDecodeError, KeyError) as exc:
            raise ValueError(f"Corrupt ledger line {line_number}") from exc
    return states

