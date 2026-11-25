import asyncio
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from torchbearer.audit import scorecard
from torchbearer.contracts import Agent, ModelIdentity, Result, Task
from torchbearer.coordinator import Coordinator
from torchbearer.knowledge import ReadOnlyKnowledge
from torchbearer.memory import record_claim
from torchbearer.runtime import Runtime
from torchbearer.store import Store

ROOT = Path(__file__).resolve().parents[1]

# The repository's mcp/ directory is importable even without the SDK installed.
try:
    importlib.metadata.version("mcp")
    MCP_SDK_AVAILABLE = True
except importlib.metadata.PackageNotFoundError:
    MCP_SDK_AVAILABLE = False


class RecordingBackend:
    def __init__(self, status="completed"):
        self.calls = []
        self.status = status

    def run(self, agent, task, materials):
        self.calls.append((agent.id, task.id, [m["id"] for m in materials]))
        content = {"argument": "Independent account", "materials": self.calls[-1][2]}
        if self.status == "retryable_failure":
            content.update(retry_basis="confirmed_not_executed", receipt="Synthetic transport receipt: invocation was not accepted.")
        return Result(self.status, content)


class FrameworkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "state.sqlite"
        self.store = Store(self.path)
        self.c = Coordinator(self.store)
        self.c.register(Agent("r", "researcher", ModelIdentity("example", "A", "weights-A")))
        self.c.register(Agent("v", "verifier", ModelIdentity("example", "B", "weights-B")))
        self.store.put_artifact("brief", {"question": "Toy question"}, visibility="restricted")
        self.store.put_artifact("original", {"argument": "Originating argument"}, visibility="restricted", origin="r")
        self.c.share("brief", ["r"])

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_independent_account_is_retained_before_disclosure(self):
        self.c.begin_verification("case", "r", "v", ["brief"], "original")
        with self.assertRaises(ValueError):
            self.c.comparison_task("case", "early")
        with self.assertRaises(PermissionError):
            self.c.share("original", ["v"])
        with self.assertRaises(PermissionError):
            self.c.submit(Task("leak", "v", "blind_derivation", "Derive", ("brief",), case_id="case", context={"original": "argument"}))
        backend = RecordingBackend()
        self.c.submit(Task("derive", "v", "blind_derivation", "Derive independently", ("brief",), case_id="case"))
        Runtime(self.c, backend).run()
        frozen_id = self.c.freeze("case", "derive")
        frozen = self.store.get_artifact(frozen_id)
        self.assertEqual(backend.calls, [("v", "derive", ["brief"])])
        self.assertFalse(self.store.authorized("original", "v"))
        self.c.comparison_task("case", "compare")
        Runtime(self.c, backend).run()
        self.c.close_comparison("case", "compare")
        self.assertEqual(backend.calls[-1][0], "v")
        self.assertIn("original", backend.calls[-1][2])
        self.assertEqual(self.store.get_artifact(frozen_id), frozen)
        self.assertEqual(self.store.db.execute("SELECT state FROM cases").fetchone()[0], "complete")
        with self.assertRaises(ValueError):
            self.store.put_artifact(frozen_id, {"argument": "Rewritten"}, visibility="restricted")

    def test_different_aliases_of_same_parameters_are_rejected(self):
        self.c.register(Agent("same", "verifier", ModelIdentity("example", "another-alias", "weights-A")))
        with self.assertRaises(ValueError):
            self.c.begin_verification("case", "r", "same", ["brief"], "original")
        self.c.share("original", ["v"])
        with self.assertRaises(ValueError):
            self.c.begin_verification("exposed", "r", "v", ["brief"], "original")

    def test_model_ids_reject_surrounding_whitespace(self):
        for parameter_id in ["weights-A ", " unknown ", "", "\tweights-A"]:
            with self.subTest(parameter_id=parameter_id), self.assertRaises(ValueError):
                ModelIdentity("example", "alias", parameter_id)

    def test_dependencies_pause_and_restart_preserve_completed_work(self):
        self.c.register(Agent("r2", "researcher", ModelIdentity("example", "C", "weights-C")))
        self.c.share("brief", ["r2"])
        self.c.submit(Task("a", "r", "research", "First task", ("brief",)))
        self.c.submit(Task("b", "r2", "research", "Use prior result", ("brief",), depends_on=("a",)))
        backend = RecordingBackend()
        runtime = Runtime(self.c, backend)
        self.c.guide("Review the resource allocation before further work.", pause=True)
        self.assertEqual(runtime.run(), 0)
        self.c.resume()
        self.assertEqual(runtime.run(max_steps=1), 1)
        self.store.close()
        self.store = Store(self.path)
        self.c = Coordinator(self.store)
        self.assertEqual(Runtime(self.c, backend).run(), 1)
        self.assertEqual([c[1] for c in backend.calls], ["a", "b"])

    def test_unknown_outcome_requires_reconciliation(self):
        self.c.submit(Task("a", "r", "research", "Task", ("brief",)))
        runtime = Runtime(self.c, RecordingBackend("unknown"))
        self.assertEqual(runtime.run(), 1)
        self.assertEqual(self.store.db.execute("SELECT state FROM tasks").fetchone()[0], "held")
        self.assertEqual(runtime.run(), 0)
        runtime.reconcile("a", evidence="Provider receipt confirms the completed invocation.", completed={"result": "retained"})
        self.assertEqual(self.store.db.execute("SELECT state FROM tasks").fetchone()[0], "completed")

    def test_interrupted_running_task_is_held_not_replayed(self):
        self.c.submit(Task("a", "r", "research", "Task", ("brief",)))
        self.store.db.execute("UPDATE tasks SET state='running',attempts=1 WHERE id='a'")
        runtime = Runtime(self.c, RecordingBackend())
        with self.assertRaises(ValueError):
            runtime.recover_interrupted(confirmed_stopped=False)
        self.assertEqual(runtime.recover_interrupted(confirmed_stopped=True), ["a"])
        self.assertEqual(runtime.run(), 0)

    def test_definite_retryable_failure_obeys_attempt_bound(self):
        self.c.submit(Task("a", "r", "research", "Task", ("brief",), max_attempts=2))
        backend = RecordingBackend("retryable_failure")
        self.assertEqual(Runtime(self.c, backend).run(), 2)
        self.assertEqual(len(backend.calls), 2)
        self.assertEqual(self.store.db.execute("SELECT state,attempts FROM tasks").fetchone()[:], ("failed", 2))

    def test_retry_without_safety_receipt_is_held(self):
        class UnsafeRetryBackend:
            def run(self, agent, task, materials):
                return Result("retryable_failure", {"error": "Failure after a possible partial effect"})
        self.c.submit(Task("a", "r", "research", "Task", ("brief",)))
        self.assertEqual(Runtime(self.c, UnsafeRetryBackend()).run(), 1)
        self.assertEqual(self.store.db.execute("SELECT state FROM tasks").fetchone()[0], "held")

    def test_informative_failure_is_versioned(self):
        claim = {"id": "failure", "revision": 1, "statement": "A toy approximation fails.",
                 "assumptions": ["Specified toy input"], "outcome": "failed_attempt",
                 "failure_reason": "The prediction disagrees with direct evaluation.",
                 "evidence_ids": ["brief"], "topic_ids": ["topic-A", "topic-B"],
                 "depends_on": [], "verification": {"agent": None, "human": None}}
        record_claim(self.store, claim)
        with self.assertRaises(ValueError):
            record_claim(self.store, {**claim, "statement": "Overwrite"})
        record_claim(self.store, {**claim, "revision": 2, "outcome": "conditional", "statement": "A restricted version is supported."})
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM claims").fetchone()[0], 2)


class KnowledgeAndAuditTest(unittest.TestCase):
    def test_search_and_read_share_the_same_scope(self):
        k = ReadOnlyKnowledge(ROOT / "examples/corpus.json", ["toy:brief", "toy:reference"])
        self.assertNotIn("toy:original", [x["id"] for x in k.search("")])
        with self.assertRaises(PermissionError):
            k.read("toy:original")
        with self.assertRaises(ValueError):
            k.search("", limit=51)
        with self.assertRaises(ValueError):
            k.search("", limit=True)

    def test_scorecard_tracks_evidence_and_action_changes(self):
        trace = json.loads((ROOT / "examples/audit_trace.json").read_text())
        first = scorecard(trace)
        self.assertAlmostEqual(first["metrics"]["previous_effective_method_families"], 3)
        self.assertEqual(first["metrics"]["current_effective_method_families"], 1)
        self.assertEqual(first["metrics"]["actionable_frontier"], 1)
        self.assertIn("search_path_contraction", first["review_cues"])
        self.assertIn("premature_research_closure", first["review_cues"])
        trace["termination_requested"] = False
        trace["actions"][0]["status"] = "completed"
        trace["evidence"].append({"id": "new-result", "basis": "The toy calculation establishes a new identity.", "source_ids": ["s3"]})
        trace["steps"][-1]["new_evidence_ids"] = ["new-result"]
        trace["assessments"] = []
        second = scorecard(trace)
        self.assertEqual(second["metrics"]["new_evidence_items"], 1)
        self.assertEqual(second["review_cues"], [])

    def test_scorecard_rejects_malformed_fields(self):
        for collection, key, value in [("actions", "feasible", "false"),
                                       ("steps", "new_evidence_ids", "abc"),
                                       ("steps", "candidate_id", ["c1"]),
                                       ("assessments", "goal_narrowed", "false")]:
            trace = json.loads((ROOT / "examples/audit_trace.json").read_text())
            trace[collection][0][key] = value
            with self.subTest(collection=collection, key=key), self.assertRaises(ValueError):
                scorecard(trace)

    @unittest.skipUnless(MCP_SDK_AVAILABLE, "Optional MCP SDK not installed")
    def test_real_mcp_stdio_scope(self):
        async def exercise():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            params = StdioServerParameters(command=sys.executable,
                args=["-m", "torchbearer.mcp_server", "--corpus", str(ROOT / "examples/corpus.json"),
                      "--scope", str(ROOT / "examples/verifier_scope.json")],
                env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    tools = {t.name: t for t in (await client.list_tools()).tools}
                    self.assertEqual(set(tools), {"read_record", "search_records"})
                    limit_schema = tools["search_records"].inputSchema["properties"]["limit"]
                    self.assertEqual(limit_schema["minimum"], 1)
                    self.assertEqual(limit_schema["maximum"], 50)
                    good = await client.call_tool("read_record", {"record_id": "toy:brief"})
                    self.assertFalse(good.isError)
                    hidden = await client.call_tool("read_record", {"record_id": "toy:original"})
                    self.assertTrue(hidden.isError)
                    search = await client.call_tool("search_records", {"query": "", "limit": 50})
                    self.assertFalse(search.isError)
                    self.assertNotIn("toy:original", json.dumps(search.model_dump()))
                    for invalid_limit in (True, "2", 0, 51):
                        with self.subTest(limit=invalid_limit):
                            rejected = await client.call_tool("search_records", {"query": "", "limit": invalid_limit})
                            self.assertTrue(rejected.isError)
        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
