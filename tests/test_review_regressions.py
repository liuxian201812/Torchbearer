"""Regressions for verification provenance and faithful runtime recovery."""

import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from torchbearer.contracts import Agent, ModelIdentity, Result, Task
from torchbearer.coordinator import Coordinator
from torchbearer.graph import ScientificMemoryGraph, node_id
from torchbearer.memory import record_claim
from torchbearer.runtime import Runtime
from torchbearer.store import Store


class RecordingBackend:
    def run(self, agent, task, materials):
        return Result("completed", {"task_id": task.id, "materials": [m["id"] for m in materials]})


class ReviewRegressionsTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.coordinator = Coordinator(self.store)
        for identity, role, parameters in [("r", "researcher", "weights-r"), ("v", "verifier", "weights-v")]:
            self.coordinator.register(Agent(identity, role, ModelIdentity("synthetic", identity, parameters)))
        self.store.put_artifact("brief", {"question": "Synthetic odd-integer sum"}, visibility="restricted")
        self.store.put_artifact("original", {"argument": "Synthetic arithmetic-series argument"}, visibility="restricted")
        self.coordinator.share("brief", ["r", "v"])
        self.runtime = Runtime(self.coordinator, RecordingBackend())

    def tearDown(self):
        self.store.close()

    def claim(self, case_id="case"):
        return {"id": "claim", "revision": 1, "statement": "The first n positive odd integers sum to n squared.",
                "assumptions": ["n is a nonnegative integer"], "outcome": "supported",
                "evidence_ids": [case_id + ":independent-account"], "topic_ids": ["synthetic-sequences"],
                "depends_on": [], "verification": {"agent": case_id, "human": None}}

    def open_case(self, case_id="case", target=None, original="original"):
        self.coordinator.begin_verification(case_id, "r", "v", ["brief"], original, target_claim=target)
        self.coordinator.submit(Task(case_id + ":derive", "v", "blind_derivation", "Derive independently",
                                     ("brief",), case_id=case_id))

    def complete_case(self, case_id="case", target=None):
        self.open_case(case_id, target)
        self.runtime.run()
        self.coordinator.freeze(case_id, case_id + ":derive")
        self.coordinator.comparison_task(case_id, case_id + ":compare")
        self.runtime.run()
        self.coordinator.close_comparison(case_id, case_id + ":compare")

    def test_verification_tasks_cannot_run_before_the_case_exists(self):
        for kind in ("blind_derivation", "comparison"):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.coordinator.submit(Task(kind, "v", kind, "Premature task", ("brief",), case_id="future-case"))
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)

    def test_only_assigned_tasks_can_advance_each_verification_stage(self):
        self.open_case()
        with self.assertRaises(ValueError):
            self.coordinator.submit(Task("another-derive", "v", "blind_derivation", "Another derivation", ("brief",), case_id="case"))
        with self.assertRaises(ValueError):
            self.coordinator.submit(Task("early-compare", "v", "comparison", "Premature comparison", case_id="case"))
        self.runtime.run()
        self.coordinator.freeze("case", "case:derive")
        self.coordinator.comparison_task("case", "case:compare")
        with self.assertRaises(ValueError):
            self.coordinator.submit(Task("another-compare", "v", "comparison", "Substitute comparison", case_id="case"))
        self.runtime.run()
        with self.assertRaises(ValueError):
            self.coordinator.close_comparison("case", "case:derive")
        self.coordinator.close_comparison("case", "case:compare")
        case = self.store.db.execute("SELECT * FROM cases WHERE id='case'").fetchone()
        self.assertEqual((case["state"], case["derivation_task"], case["comparison_task"]),
                         ("complete", "case:derive", "case:compare"))

    def test_another_cases_completed_task_cannot_be_frozen_or_used_for_comparison(self):
        self.complete_case("old")
        self.store.put_artifact("new-original", {"argument": "A different synthetic argument"}, visibility="restricted")
        self.open_case("new", original="new-original")
        self.runtime.run()
        with self.assertRaises(ValueError):
            self.coordinator.freeze("new", "old:derive")
        self.coordinator.freeze("new", "new:derive")
        self.coordinator.comparison_task("new", "new:compare")
        with self.assertRaises(ValueError):
            self.coordinator.close_comparison("new", "old:compare")
        self.assertEqual(self.store.db.execute("SELECT state FROM cases WHERE id='new'").fetchone()[0], "comparing")
        self.assertEqual(self.store.db.execute("SELECT state FROM tasks WHERE id='new:compare'").fetchone()[0], "pending")

    def test_verification_binds_claim_version_statement_assumptions_evidence_and_dependencies(self):
        claim = self.claim()
        premise = {**self.claim(), "id": "another-premise", "evidence_ids": [],
                   "verification": {"agent": None, "human": None}}
        record_claim(self.store, premise)
        self.complete_case(target=claim)
        changes = {"id": "unrelated", "revision": 2, "statement": "An unrelated model is always stable.",
                   "assumptions": ["A different domain"], "evidence_ids": [], "depends_on": ["another-premise"]}
        for field, replacement in changes.items():
            changed = copy.deepcopy(claim)
            changed[field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                record_claim(self.store, changed)
        record_claim(self.store, claim)
        with self.assertRaisesRegex(ValueError, "must target this exact claim"):
            record_claim(self.store, {**claim, "revision": 2})
        links = [e for e in ScientificMemoryGraph(self.store).snapshot()["edges"] if e["relation"] == "verified_by"]
        self.assertEqual(links, [{"source": node_id("claim_revision", "claim", 1),
                                  "relation": "verified_by", "target": node_id("verification", "case")}])

    def test_verification_does_not_transfer_to_a_revised_prerequisite(self):
        premise = {**self.claim(), "id": "premise", "evidence_ids": [],
                   "verification": {"agent": None, "human": None}}
        record_claim(self.store, premise)
        claim = {**self.claim(), "depends_on": ["premise"]}
        self.complete_case(target=claim)
        record_claim(self.store, {**premise, "revision": 2, "statement": "The premise has changed."})
        with self.assertRaisesRegex(ValueError, "must target this exact claim"):
            record_claim(self.store, claim)
        pinned = {**claim, "depends_on": [{"id": "premise", "revision": 1}]}
        record_claim(self.store, pinned)

    def test_completed_case_without_target_cannot_attest_a_claim(self):
        self.complete_case()
        with self.assertRaisesRegex(ValueError, "must target this exact claim"):
            record_claim(self.store, self.claim())
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM claims").fetchone()[0], 0)

    def test_reconciliation_preserves_a_successful_empty_object(self):
        class UnknownBackend:
            def run(self, agent, task, materials):
                return Result("unknown", {})
        self.coordinator.submit(Task("empty", "r", "research", "Synthetic empty result"))
        runtime = Runtime(self.coordinator, UnknownBackend())
        runtime.run()
        runtime.reconcile("empty", evidence="Synthetic receipt confirms an empty success result", completed={})
        row = self.store.db.execute("SELECT state,result FROM tasks WHERE id='empty'").fetchone()
        self.assertEqual(row["state"], "completed")
        self.assertEqual(json.loads(row["result"]), {})

    def test_attempt_and_dispatch_budgets_require_positive_integers(self):
        for bound in (0, -1, True, 1.5, float("inf"), float("nan")):
            with self.subTest(bound=bound), self.assertRaises(ValueError):
                Task("invalid", "r", "research", "Synthetic task", max_attempts=bound)
            with self.subTest(bound=bound), self.assertRaises(ValueError):
                self.runtime.run(max_steps=bound)
        self.coordinator.submit(Task("valid", "r", "research", "Synthetic task", max_attempts=1))
        self.assertEqual(self.runtime.run(max_steps=1), 1)

    def test_existing_case_table_is_extended_without_inventing_verification_targets(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy.sqlite"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE cases (id TEXT PRIMARY KEY, researcher TEXT NOT NULL, verifier TEXT NOT NULL, "
                       "brief TEXT NOT NULL, original TEXT NOT NULL, state TEXT NOT NULL, "
                       "frozen_artifact TEXT, frozen_hash TEXT, comparison TEXT)")
            db.execute("INSERT INTO cases(id,researcher,verifier,brief,original,state) VALUES('legacy','r','v','[]','original','complete')")
            db.commit()
            db.close()
            reopened = Store(path)
            try:
                row = reopened.db.execute("SELECT * FROM cases WHERE id='legacy'").fetchone()
                self.assertEqual(row["state"], "complete")
                self.assertIsNone(row["target_claim"])
                self.assertIsNone(row["derivation_task"])
                self.assertIsNone(row["comparison_task"])
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
