"""Bounded dispatch, durable checkpoints and explicit recovery."""

import json
from .contracts import AgentBackend, Result, Task
from .coordinator import Coordinator
from .store import canonical, now


class Runtime:
    def __init__(self, coordinator: Coordinator, backend: AgentBackend):
        self.coordinator, self.store, self.backend = coordinator, coordinator.store, backend

    def tick(self) -> str | None:
        """Dispatch one eligible task. Each call is a recoverable control boundary."""
        with self.store.transaction():
            pause = self.store.db.execute("SELECT value FROM controls WHERE key='paused'").fetchone()
            if pause and pause["value"] == "true":
                return None
            chosen = None
            for row in self.store.db.execute("SELECT * FROM tasks WHERE state='pending' ORDER BY rowid"):
                spec = json.loads(row["spec"])
                ready = all(self.store.db.execute("SELECT state FROM tasks WHERE id=?", (dep,)).fetchone()["state"] == "completed"
                            for dep in spec["depends_on"])
                if ready:
                    chosen = (row, spec)
                    break
            if chosen is None:
                return None
            row, spec = chosen
            self.store.db.execute("UPDATE tasks SET state='running',attempts=attempts+1,updated_at=? WHERE id=?",
                                  (now(), row["id"]))
            self.store.event("task.dispatched", task_id=row["id"], attempt=row["attempts"] + 1)
        task = Task(**spec)
        try:
            materials = self.coordinator.materials(task)
            result = self.backend.run(self.coordinator.agent(task.agent_id), task, materials)
            if not isinstance(result, Result) or result.status not in {"completed", "retryable_failure", "unknown"}:
                raise ValueError("Invalid backend result")
            if result.status == "retryable_failure":
                basis = result.content.get("retry_basis")
                receipt = result.content.get("receipt")
                if basis not in {"confirmed_not_executed", "idempotent_operation"} or not isinstance(receipt, str) or not receipt.strip():
                    raise ValueError("A retry requires a confirmed non-execution or idempotency receipt")
            canonical(result.content)
        except Exception as exc:
            # The backend may already have started work: do not replay an ambiguous call.
            result = Result("unknown", {"error_type": type(exc).__name__, "detail": str(exc)})
        with self.store.transaction():
            attempts = self.store.db.execute("SELECT attempts FROM tasks WHERE id=?", (task.id,)).fetchone()["attempts"]
            if result.status == "completed":
                state = "completed"
            elif result.status == "retryable_failure":
                state = "pending" if attempts < task.max_attempts else "failed"
            else:
                state = "held"
            self.store.db.execute("UPDATE tasks SET state=?,result=?,updated_at=? WHERE id=?",
                                  (state, canonical(result.content), now(), task.id))
            self.store.event("task.checkpoint", task_id=task.id, state=state, attempt=attempts)
        return task.id

    def run(self, max_steps: int = 100) -> int:
        if type(max_steps) is not int or max_steps < 1:
            raise ValueError("Use a positive dispatch budget")
        count = 0
        while count < max_steps and self.tick() is not None:
            count += 1
        return count

    def recover_interrupted(self, *, confirmed_stopped: bool):
        """Call after the owner process has stopped; uncertain work is held."""
        if not confirmed_stopped:
            raise ValueError("Confirm that the prior owner has stopped before recovery")
        with self.store.transaction():
            ids = [r["id"] for r in self.store.db.execute("SELECT id FROM tasks WHERE state='running'")]
            for task_id in ids:
                self.store.db.execute("UPDATE tasks SET state='held',updated_at=? WHERE id=?", (now(), task_id))
                self.store.event("task.recovered", task_id=task_id, state="held")
        return ids

    def reconcile(self, task_id: str, *, evidence: str, completed: dict | None = None,
                  definitely_not_executed: bool = False):
        if not evidence.strip() or ((completed is not None) == definitely_not_executed):
            raise ValueError("Provide receipt evidence and exactly one reconciled outcome")
        row = self.store.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row or row["state"] != "held":
            raise ValueError("Only held tasks need reconciliation")
        spec = json.loads(row["spec"])
        state = "completed" if completed is not None else ("pending" if row["attempts"] < spec["max_attempts"] else "failed")
        with self.store.transaction():
            self.store.db.execute("UPDATE tasks SET state=?,result=?,updated_at=? WHERE id=?",
                                  (state, canonical(completed if completed is not None else {"reconciliation": evidence}), now(), task_id))
            self.store.event("task.reconciled", task_id=task_id, evidence=evidence, state=state)
