"""One coordinator routes multiple agents and controls scientific context."""

import json
from dataclasses import asdict
from .contracts import Agent, ModelIdentity, Task, verification_target
from .graph import resolve_dependencies
from .store import Store, canonical, now


class Coordinator:
    def __init__(self, store: Store):
        self.store = store

    def register(self, agent: Agent):
        if self.store.db.execute('SELECT 1 FROM human_reviews WHERE reviewer_id=?', (agent.id,)).fetchone():
            raise ValueError('Human reviewer and agent identities must remain distinct')
        spec = canonical(asdict(agent))
        row = self.store.db.execute("SELECT spec FROM agents WHERE id=?", (agent.id,)).fetchone()
        if row and row["spec"] != spec:
            raise ValueError("A new model deployment needs a new agent identity")
        self.store.db.execute("INSERT OR IGNORE INTO agents VALUES(?,?)", (agent.id, spec))

    def agent(self, agent_id: str) -> Agent:
        row = self.store.db.execute("SELECT spec FROM agents WHERE id=?", (agent_id,)).fetchone()
        if row is None:
            raise KeyError(agent_id)
        d = json.loads(row["spec"])
        d["model"] = ModelIdentity(**d["model"])
        return Agent(**d)

    def share(self, artifact_id: str, recipients: list[str]):
        """Distribute existing material to named agents through the coordinator."""
        with self.store.transaction():
            for agent_id in recipients:
                self.agent(agent_id)
                active = self.store.db.execute(
                    "SELECT id,brief FROM cases WHERE verifier=? AND state='deriving'", (agent_id,)).fetchall()
                for case in active:
                    if artifact_id not in json.loads(case["brief"]):
                        raise PermissionError("An active blinded verifier only receives its approved brief")
                self.store.grant(artifact_id, agent_id)
            self.store.event("material.shared", artifact_id=artifact_id, recipients=recipients)

    def submit(self, task: Task):
        with self.store.transaction():
            self._submit(task)

    def _submit(self, task: Task):
        """Queue a task inside the caller's transaction."""
        self.agent(task.agent_id)
        for dep in task.depends_on:
            if not self.store.db.execute("SELECT 1 FROM tasks WHERE id=?", (dep,)).fetchone():
                raise ValueError(f"Unknown dependency: {dep}")
        for artifact_id in task.artifact_ids:
            if not self.store.authorized(artifact_id, task.agent_id):
                raise PermissionError(f"Material is outside this agent's scope: {artifact_id}")
        self._check_blind_scope(task, assigning=True)
        self.store.db.execute("INSERT INTO tasks(id,spec,state,updated_at) VALUES(?,?,'pending',?)",
                              (task.id, canonical(asdict(task)), now()))
        if task.kind == "blind_derivation":
            self.store.db.execute("UPDATE cases SET derivation_task=? WHERE id=?", (task.id, task.case_id))
        self.store.event("task.queued", task_id=task.id, agent_id=task.agent_id, task_kind=task.kind)

    def _check_blind_scope(self, task: Task, *, assigning: bool = False):
        if task.kind in {"blind_derivation", "comparison"}:
            case = self.store.db.execute("SELECT * FROM cases WHERE id=?", (task.case_id,)).fetchone()
            stage, field = ("deriving", "derivation_task") if task.kind == "blind_derivation" else ("comparing", "comparison_task")
            if not case or case["state"] != stage or case["verifier"] != task.agent_id:
                raise ValueError("Verification tasks require their assigned case and active stage")
            first_derivation = assigning and task.kind == "blind_derivation" and case[field] is None
            if not first_derivation and case[field] != task.id:
                raise ValueError("Use the task assigned to this verification stage")
        active = self.store.db.execute("SELECT * FROM cases WHERE verifier=? AND state='deriving'",
                                       (task.agent_id,)).fetchall()
        for case in active:
            if task.case_id != case["id"] or task.kind != "blind_derivation":
                raise PermissionError("Reserve the verifier context for its active independent derivation")
            if not set(task.artifact_ids).issubset(json.loads(case["brief"])):
                raise PermissionError("The independent stage only accepts the approved brief")
            if task.context:
                raise PermissionError("Additional context must enter through the approved brief")

    def materials(self, task: Task) -> list[dict]:
        self._check_blind_scope(task)
        result = []
        for artifact_id in task.artifact_ids:
            if not self.store.authorized(artifact_id, task.agent_id):
                raise PermissionError(artifact_id)
            result.append(self.store.get_artifact(artifact_id))
        return result

    def begin_verification(self, case_id: str, researcher: str, verifier: str,
                           brief_ids: list[str], original_id: str, *, target_claim: dict | None = None):
        r, v = self.agent(researcher), self.agent(verifier)
        if r.role != "researcher" or v.role != "verifier":
            raise ValueError("Assign a researcher and a verifier to the case")
        if r.model.parameter_id == v.model.parameter_id:
            raise ValueError("Use different model parameter identities for research and verification")
        if original_id in brief_ids or not brief_ids:
            raise ValueError("The brief must be complete and exclude the originating argument")
        self.store.get_artifact(original_id)
        if self.store.authorized(original_id, verifier):
            raise ValueError("Use an unexposed verifier context for blinded derivation")
        if self.store.db.execute("SELECT 1 FROM cases WHERE verifier=? AND state='deriving'", (verifier,)).fetchone():
            raise ValueError("This verifier already has an active independent derivation")
        with self.store.transaction():
            for artifact_id in brief_ids:
                self.store.get_artifact(artifact_id)
                self.store.grant(artifact_id, verifier)
            target = None
            if target_claim is not None:
                target = canonical(verification_target(target_claim,
                    dependencies=resolve_dependencies(self.store, target_claim.get("depends_on", []))))
            self.store.db.execute("INSERT INTO cases(id,researcher,verifier,brief,original,state,target_claim) VALUES(?,?,?,?,?,'deriving',?)",
                                  (case_id, researcher, verifier, canonical(brief_ids), original_id, target))
            self.store.event("verification.opened", case_id=case_id, researcher=researcher,
                             verifier=verifier, researcher_parameters=r.model.parameter_id,
                             verifier_parameters=v.model.parameter_id, brief_ids=brief_ids)

    def freeze(self, case_id: str, task_id: str):
        case = self.store.db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        task = self.store.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not case or case["state"] != "deriving" or not task or task["state"] != "completed":
            raise ValueError("Freeze a completed independent account in an open case")
        spec = json.loads(task["spec"])
        if (task_id != case["derivation_task"] or spec["agent_id"] != case["verifier"]
                or spec["case_id"] != case_id or spec["kind"] != "blind_derivation"):
            raise ValueError("The completed task does not belong to this independent stage")
        body = json.loads(task["result"])
        artifact_id = f"{case_id}:independent-account"
        with self.store.transaction():
            sha = self.store.put_artifact(artifact_id, body, visibility="restricted", origin=task_id)
            self.store.grant(artifact_id, case["verifier"])
            self.store.db.execute("UPDATE cases SET state='frozen',frozen_artifact=?,frozen_hash=? WHERE id=?",
                                  (artifact_id, sha, case_id))
            self.store.event("verification.frozen", case_id=case_id, artifact_id=artifact_id, sha256=sha)
        return artifact_id

    def comparison_task(self, case_id: str, task_id: str) -> Task:
        """Atomically disclose the original and enqueue the comparison task."""
        case = self.store.db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if not case or case["state"] != "frozen":
            raise ValueError("Retain the independent account before releasing the original")
        frozen = self.store.get_artifact(case["frozen_artifact"])
        if frozen["sha256"] != case["frozen_hash"]:
            raise ValueError("Frozen account integrity check failed")
        task = Task(task_id, case["verifier"], "comparison",
                    "Compare the retained independent account with the originating argument; record agreement, discrepancies and scope.",
                    tuple(json.loads(case["brief"]) + [case["frozen_artifact"], case["original"]]), case_id=case_id)
        with self.store.transaction():
            self.store.grant(case["original"], case["verifier"])
            self.store.db.execute("UPDATE cases SET state='comparing',comparison_task=? WHERE id=?", (task_id, case_id))
            self.store.event("verification.disclosed", case_id=case_id, original_id=case["original"])
            self._submit(task)
        return task

    def close_comparison(self, case_id: str, task_id: str):
        case = self.store.db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        task = self.store.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not case or case["state"] != "comparing" or not task or task["state"] != "completed":
            raise ValueError("A completed comparison is required")
        spec = json.loads(task["spec"])
        if (task_id != case["comparison_task"] or spec["case_id"] != case_id
                or spec["agent_id"] != case["verifier"] or spec["kind"] != "comparison"):
            raise ValueError("Comparison task identity mismatch")
        self.store.db.execute("UPDATE cases SET state='complete',comparison=? WHERE id=?", (task["result"], case_id))
        self.store.event("verification.completed", case_id=case_id, task_id=task_id)

    def guide(self, message: str, *, task_ids: list[str] | None = None, pause: bool = False):
        """Human guidance enters control state, then is translated into scoped tasks."""
        if not message.strip():
            raise ValueError("Guidance must contain an instruction")
        if task_ids:
            for task_id in task_ids:
                if not self.store.db.execute("SELECT 1 FROM tasks WHERE id=?", (task_id,)).fetchone():
                    raise ValueError(f"Unknown task: {task_id}")
        with self.store.transaction():
            self.store.event("human.guidance", message=message, task_ids=task_ids or [], pause_requested=pause)
            if pause:
                self.store.db.execute("INSERT OR REPLACE INTO controls VALUES('paused','true')")

    def resume(self):
        self.store.db.execute("INSERT OR REPLACE INTO controls VALUES('paused','false')")
        self.store.event("runtime.resumed")
