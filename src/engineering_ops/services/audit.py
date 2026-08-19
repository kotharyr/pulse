from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class AuditEvent:
    event_id: int
    action: str
    actor: str = "system"
    target: str | None = None
    outcome: str = "recorded"
    correlation_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        row = {
            "event_id": self.event_id,
            "action": self.action,
            "actor": self.actor,
            "target": self.target,
            "outcome": self.outcome,
            "correlation_id": self.correlation_id,
            "details": deepcopy(self.details),
            "created_at": self.created_at,
        }
        return {key: value for key, value in row.items() if value is not None}


class AuditTrail:
    """Process-local audit trail for previews, applies, config, and diagnostics."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._next_id = 1

    def record(
        self,
        action: str,
        *,
        actor: str = "system",
        target: str | None = None,
        outcome: str = "recorded",
        correlation_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = AuditEvent(
            event_id=self._next_id,
            action=action,
            actor=actor,
            target=target,
            outcome=outcome,
            correlation_id=correlation_id,
            details=deepcopy(details or {}),
        )
        self._next_id += 1
        self._events.append(event)
        return event.to_dict()

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._events[-max(1, int(limit)):]
        return [event.to_dict() for event in reversed(rows)]

    def count(self) -> int:
        return len(self._events)
