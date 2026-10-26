from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
import os
from typing import Any
from uuid import uuid4

from engineering_ops.services.identity import current_actor
from engineering_ops.services.state import StateDatabase


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return {"invalid_number": str(value)}
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(v) for v in value]
    return value


def fingerprint(value: Any) -> str:
    return sha256(json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode()).hexdigest()


def _event(db, action, actor, target, outcome, details=None):
    db.execute("INSERT INTO audit(data) VALUES (?)", (json.dumps({
        "action": action, "actor": actor, "target": target, "outcome": outcome,
        "details": details or {}, "created_at": _now(),
    }),))


@dataclass
class ExecutionRecord:
    data: dict[str, Any]

    @property
    def status(self):
        return self.data["status"]

    def to_dict(self):
        return json.loads(json.dumps(self.data))


class ExecutionHistory:
    """Transactional approvals and a write-ahead step journal, optionally on disk."""

    def __init__(self, path=None):
        self.db = path if isinstance(path, StateDatabase) else StateDatabase(path)

    def add_preview(self, action, instance, parameters, preview):
        actor = current_actor()
        parameters, preview = _json_safe(parameters), _json_safe(preview)
        # Strip presentation and lifecycle metadata before deriving duplicate-operation identity.
        source = {k: v for k, v in preview.items() if k not in {"mode", "can_apply", "preview_id"}}
        source_version = fingerprint(source)
        operation_key = fingerprint({"action": action, "instance": instance, "source": source_version, "parameters": parameters})
        record = {
            "preview_id": uuid4().hex, "action": action, "instance": instance,
            "actor": actor, "parameters": parameters, "preview": preview,
            "source_version": source_version, "operation_key": operation_key,
            "status": "previewed", "result": None, "error": None,
            "created_at": _now(), "updated_at": _now(),
        }
        with self.db.transaction() as db:
            db.execute("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,NULL)", (
                record["preview_id"], action, instance, actor, operation_key, source_version,
                "previewed", json.dumps(record), record["created_at"],
            ))
            _event(db, "approval_preview_created", actor, record["preview_id"], "previewed")
        return self.get_record(record["preview_id"]).to_dict()

    def _row(self, db, preview_id):
        row = db.execute("SELECT * FROM executions WHERE preview_id=?", (preview_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown preview_id: {preview_id}")
        return row

    def _save(self, db, record, *, owner_pid=None):
        record["updated_at"] = _now()
        db.execute("UPDATE executions SET status=?, data=?, owner_pid=? WHERE preview_id=?", (
            record["status"], json.dumps({k: v for k, v in record.items() if k != "steps"}), owner_pid, record["preview_id"],
        ))

    def _check_scope(self, row, action=None, instance=None):
        if row["actor"] != current_actor():
            raise ValueError("Preview belongs to a different actor; create a new review")
        if action is not None and row["action"] != action:
            raise ValueError(f"Preview action must be {action}")
        if instance is not None and row["instance"] != instance:
            raise ValueError("Preview belongs to a different instance")

    def resources(self, record):
        params, preview = record["parameters"], record["preview"]
        resources = ["operation:" + record["operation_key"]]
        if record["action"] == "create_issue":
            resources.append("operation:create:" + preview["recovery_label"])
        if record["action"] == "close_sprint":
            resources += [f"{record['instance']}:sprint:{params[key]}" for key in ("sprint_id", "next_sprint_id")]
        keys = [item.get("issue_key") for item in preview.get("issues", [])]
        keys += [item.get("issue_key") for item in preview.get("changes", [])]
        keys += list(preview.get("move_issue_keys", []))
        keys += [item.get("source_issue_key") for item in preview.get("split_plans", [])]
        resources += [f"{record['instance']}:issue:{key}" for key in keys if key]
        return sorted(set(resources))

    def begin_apply(self, preview_id, *, action=None, instance=None, recovery=False):
        with self.db.transaction() as db:
            row = self._row(db, preview_id)
            self._check_scope(row, action, instance)
            record = json.loads(row["data"])
            expected = "recovery_required" if recovery else "previewed"
            if row["status"] != expected:
                raise ValueError(f"Cannot apply preview in {row['status']} status; reconcile or review a new plan")
            for resource in self.resources(record):
                claim = db.execute("SELECT preview_id FROM claims WHERE resource=?", (resource,)).fetchone()
                if claim and claim[0] != preview_id:
                    raise ValueError("An equivalent or overlapping operation already owns this source; reconcile it first")
                db.execute("INSERT OR IGNORE INTO claims VALUES (?,?)", (resource, preview_id))
            record["status"] = "applying"
            self._save(db, record, owner_pid=os.getpid())
            _event(db, "approval_apply_started", current_actor(), preview_id, "applying")
        return self.get_record(preview_id).to_dict()

    def mark_applied(self, preview_id, result):
        with self.db.transaction() as db:
            row = self._row(db, preview_id)
            record = json.loads(row["data"])
            steps = db.execute("SELECT status FROM steps WHERE preview_id=?", (preview_id,)).fetchall()
            record["result"] = result
            record["status"] = "succeeded" if result.get("applied") else "recovery_required" if steps else "failed"
            record["error"] = None if result.get("applied") else result.get("reason", "Apply did not complete")
            self._save(db, record)
            # Completed operation fingerprints stay claimed; ordinary source locks are released.
            if record["status"] == "succeeded":
                db.execute("DELETE FROM claims WHERE preview_id=? AND resource NOT LIKE 'operation:%'", (preview_id,))
            elif record["status"] == "failed":
                db.execute("DELETE FROM claims WHERE preview_id=?", (preview_id,))
            _event(db, "approval_apply_finished", row["actor"], preview_id, record["status"])
        return self.get_record(preview_id).to_dict()

    def mark_rejected(self, preview_id):
        with self.db.transaction() as db:
            row = self._row(db, preview_id)
            self._check_scope(row)
            if row["status"] not in {"previewed", "failed", "rejected"}:
                raise ValueError(f"Cannot reject preview in {row['status']} status")
            record = json.loads(row["data"])
            record["status"] = "rejected"
            self._save(db, record)
            _event(db, "approval_preview_rejected", current_actor(), preview_id, "rejected")
        return self.get_record(preview_id).to_dict()

    def get_record(self, preview_id):
        with self.db.lock:
            row = self._row(self.db.connection, preview_id)
            data = json.loads(row["data"])
            data["steps"] = self.steps(preview_id)
            return ExecutionRecord(data)

    def steps(self, preview_id):
        with self.db.lock:
            rows = self.db.connection.execute("SELECT * FROM steps WHERE preview_id=? ORDER BY rowid", (preview_id,)).fetchall()
            return [{"step_id": r["step_id"], "kind": r["kind"], "status": r["status"],
                     "request": json.loads(r["request"]), "result": json.loads(r["result"]) if r["result"] else None,
                     "error": r["error"]} for r in rows]

    def start_step(self, preview_id, step_id, kind, request):
        with self.db.transaction() as db:
            row = self._row(db, preview_id)
            self._check_scope(row)
            if row["status"] != "applying" or row["owner_pid"] != os.getpid():
                raise ValueError("This worker does not own an active execution")
            existing = db.execute("SELECT * FROM steps WHERE preview_id=? AND step_id=?", (preview_id, step_id)).fetchone()
            if existing:
                if existing["kind"] != kind or json.loads(existing["request"]) != request:
                    raise ValueError("Step no longer matches the reviewed action")
                if existing["status"] == "succeeded":
                    return json.loads(existing["result"])
                if existing["status"] not in {"not_applied", "pending"}:
                    raise ValueError("Step has an uncertain outcome; reconcile before retry")
                db.execute("UPDATE steps SET status='started', error=NULL WHERE preview_id=? AND step_id=?", (preview_id, step_id))
            else:
                db.execute("INSERT INTO steps VALUES (?,?,?,?,?,NULL,NULL)", (preview_id, step_id, kind, "started", json.dumps(request)))
            _event(db, "execution_step_started", row["actor"], preview_id, "started", {"step_id": step_id, "kind": kind})
        return None

    def finish_step(self, preview_id, step_id, status, result=None, error=None, *, reconciling=False):
        with self.db.transaction() as db:
            row = self._row(db, preview_id)
            if reconciling and row["status"] != "recovery_required":
                raise ValueError("Execution resumed during reconciliation; reload its state")
            db.execute("UPDATE steps SET status=?, result=?, error=? WHERE preview_id=? AND step_id=?", (
                status, json.dumps(result) if result is not None else None, error, preview_id, step_id,
            ))
            _event(db, "execution_step_finished", row["actor"], preview_id, status, {"step_id": step_id})

    def prepare_reconciliation(self, preview_id):
        with self.db.transaction() as db:
            row = self._row(db, preview_id)
            self._check_scope(row)
            if row["status"] == "applying":
                try:
                    os.kill(row["owner_pid"], 0)
                except ProcessLookupError:
                    record = json.loads(row["data"])
                    record["status"] = "recovery_required"
                    self._save(db, record)
                    _event(db, "execution_worker_lost", row["actor"], preview_id, "recovery_required")
                else:
                    raise ValueError("Execution worker is still running; do not reconcile an active operation")
            elif row["status"] != "recovery_required":
                raise ValueError(f"Cannot reconcile preview in {row['status']} status")
        return self.get_record(preview_id).to_dict()

    def list(self, limit=50):
        with self.db.lock:
            keys = self.db.connection.execute("SELECT preview_id FROM executions ORDER BY rowid DESC LIMIT ?", (max(1, min(int(limit), 1000)),)).fetchall()
            return [self.get_record(row[0]).to_dict() for row in keys]
