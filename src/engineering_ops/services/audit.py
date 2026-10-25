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
    """Durable local audit events, shared with the execution database in production."""

    def __init__(self, path=None):
        from engineering_ops.services.state import StateDatabase
        self.db = path if isinstance(path, StateDatabase) else StateDatabase(path)

    def record(self, action, *, actor=None, target=None, outcome="recorded", correlation_id=None, details=None):
        import json
        from engineering_ops.services.identity import current_actor
        event = AuditEvent(0, action, actor or current_actor(), target, outcome, correlation_id, details or {})
        row = event.to_dict()
        row.pop("event_id")
        with self.db.transaction() as db:
            cursor = db.execute("INSERT INTO audit(data) VALUES (?)", (json.dumps(row),))
            row["event_id"] = cursor.lastrowid
        return row

    def list(self, limit=100):
        import json
        with self.db.lock:
            rows = self.db.connection.execute("SELECT event_id,data FROM audit ORDER BY event_id DESC LIMIT ?", (max(1, min(int(limit), 1000)),)).fetchall()
            return [{**json.loads(row["data"]), "event_id": row["event_id"]} for row in rows]

    def count(self):
        with self.db.lock:
            return self.db.connection.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
