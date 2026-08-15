from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class ExecutionRecord:
    preview_id: str
    action: str
    instance: str
    parameters: dict[str, Any]
    preview: dict[str, Any]
    status: str = "previewed"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preview_id": self.preview_id,
            "action": self.action,
            "instance": self.instance,
            "parameters": deepcopy(self.parameters),
            "preview": deepcopy(self.preview),
            "status": self.status,
            "result": deepcopy(self.result),
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ExecutionHistory:
    """Process-local preview/apply history for console workflows."""

    def __init__(self) -> None:
        self._records: dict[str, ExecutionRecord] = {}
        self._order: list[str] = []

    def add_preview(self, action: str, instance: str, parameters: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
        preview_id = preview["preview_id"]
        record = ExecutionRecord(
            preview_id=preview_id,
            action=action,
            instance=instance,
            parameters=deepcopy(parameters),
            preview=deepcopy(preview),
        )
        if preview_id not in self._records:
            self._order.append(preview_id)
        self._records[preview_id] = record
        return record.to_dict()

    def mark_applied(self, preview_id: str, result: dict[str, Any]) -> dict[str, Any]:
        record = self.get_record(preview_id)
        record.result = deepcopy(result)
        record.status = "succeeded" if result.get("applied") else "failed"
        record.error = None if result.get("applied") else result.get("reason", "Apply did not complete")
        record.updated_at = _now()
        return record.to_dict()

    def mark_rejected(self, preview_id: str) -> dict[str, Any]:
        record = self.get_record(preview_id)
        record.status = "rejected"
        record.updated_at = _now()
        return record.to_dict()

    def get_record(self, preview_id: str) -> ExecutionRecord:
        try:
            return self._records[preview_id]
        except KeyError as exc:
            raise KeyError(f"Unknown preview_id: {preview_id}") from exc

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        keys = list(reversed(self._order[-limit:]))
        return [self._records[key].to_dict() for key in keys]
