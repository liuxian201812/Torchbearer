import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from torchbearer.command_backend import CommandBackend, WorkerCommand
from torchbearer.contracts import Agent, ModelIdentity, Task
from torchbearer.coordinator import Coordinator
from torchbearer.runtime import Runtime
from torchbearer.store import Store

ROOT = Path(__file__).resolve().parents[1]


class ProcessIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / "state.sqlite")
        self.coordinator = Coordinator(self.store)
        self.coordinator.register(Agent("r", "researcher", ModelIdentity("synthetic", "worker", "example-parameters")))
        self.store.put_artifact("brief", {"question": "Synthetic question"}, visibility="restricted")
        self.coordinator.share("brief", ["r"])
        self.coordinator.submit(Task("task", "r", "research", "Read the permitted brief", ("brief",)))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def backend(self, code, timeout=10):
        return CommandBackend({"r": WorkerCommand((sys.executable, "-c", code), timeout_seconds=timeout)})

    def state(self):
        return self.store.db.execute("SELECT state,attempts,result FROM tasks WHERE id='task'").fetchone()

    def test_worker_gets_structured_materials_and_completion_survives_restart(self):
        backend = CommandBackend({"r": WorkerCommand((sys.executable, str(ROOT / "examples/stdio_worker.py")))})
        self.assertEqual(Runtime(self.coordinator, backend).run(), 1)
        row = self.state()
        self.assertEqual(row["state"], "completed")
        self.assertEqual(json.loads(row["result"])["received_artifact_ids"], ["brief"])
        self.store.close()
        self.store = Store(self.root / "state.sqlite")
        self.assertEqual(Runtime(Coordinator(self.store), backend).run(), 0)

    def test_exit_after_a_side_effect_is_held_until_receipt_reconciliation(self):
        marker = self.root / "receipt.txt"
        code = "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('accepted-once'); sys.exit(7)"
        backend = CommandBackend({"r": WorkerCommand((sys.executable, "-c", code, str(marker)))})
        runtime = Runtime(self.coordinator, backend)
        self.assertEqual(runtime.run(), 1)
        self.assertEqual(self.state()["state"], "held")
        self.assertEqual(runtime.run(), 0)
        self.assertEqual(marker.read_text(), "accepted-once")
        runtime.reconcile("task", evidence="The worker receipt confirms acceptance.", completed={"receipt": marker.read_text()})
        self.assertEqual(self.state()["state"], "completed")

    def test_timeout_and_invalid_output_do_not_retry(self):
        for code, timeout, error in [
            ("import time; time.sleep(5)", 0.05, "worker_timeout"),
            ("print('ordinary log text')", 10, "invalid_worker_json"),
            ("print('{\"status\": \"completed\", \"content\": []}')", 10, "invalid_worker_response"),
        ]:
            with self.subTest(error=error):
                self.store.db.execute("UPDATE tasks SET state='pending',attempts=0,result=NULL WHERE id='task'")
                runtime = Runtime(self.coordinator, self.backend(code, timeout))
                self.assertEqual(runtime.run(), 1)
                row = self.state()
                self.assertEqual((row["state"], row["attempts"]), ("held", 1))
                self.assertEqual(json.loads(row["result"])["error"], error)

    def test_relative_working_directory_is_bound_by_host_config(self):
        workdir = self.root / "worker-dir"
        workdir.mkdir()
        config = self.root / "commands.json"
        code = "import os,json; print(json.dumps({'status':'completed','content':{'cwd':os.getcwd()}}))"
        config.write_text(json.dumps({"agents": {"r": {"argv": [sys.executable, "-c", code], "cwd": "worker-dir"}}}))
        Runtime(self.coordinator, CommandBackend.from_file(config)).run()
        self.assertEqual(json.loads(self.state()["result"])["cwd"], str(workdir))
        with self.assertRaises(ValueError):
            WorkerCommand("python -c arbitrary-shell-text")

    def test_cli_checks_missing_worker_before_dispatch(self):
        config = self.root / "commands.json"
        config.write_text(json.dumps({"agents": {"other": {"argv": [sys.executable, "-c", "pass"]}}}))
        result = subprocess.run([sys.executable, "-m", "torchbearer", "run", "--state", self.store.path,
                                 "--backend-config", str(config)], capture_output=True, text=True, cwd=self.root)
        self.assertEqual(result.returncode, 2)
        self.assertIn("No worker configured", result.stderr)
        self.assertEqual((self.state()["state"], self.state()["attempts"]), ("pending", 0))

    def test_owner_process_death_preserves_running_state_without_replay(self):
        marker = self.root / "owner-receipt.txt"
        script = """
import os, sys
from pathlib import Path
from torchbearer.store import Store
from torchbearer.coordinator import Coordinator
from torchbearer.runtime import Runtime
class InterruptedBackend:
    def run(self, agent, task, materials):
        Path(sys.argv[2]).write_text('one invocation')
        os._exit(73)
store = Store(sys.argv[1])
Runtime(Coordinator(store), InterruptedBackend()).run()
"""
        process = subprocess.run([sys.executable, "-c", script, self.store.path, str(marker)], cwd=self.root,
                                 env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        self.assertEqual(process.returncode, 73)
        self.assertEqual(self.state()["state"], "running")
        runtime = Runtime(self.coordinator, self.backend("raise RuntimeError('must not dispatch')"))
        self.assertEqual(runtime.recover_interrupted(confirmed_stopped=True), ["task"])
        self.assertEqual(runtime.run(), 0)
        self.assertEqual((self.state()["state"], self.state()["attempts"]), ("held", 1))
        self.assertEqual(marker.read_text(), "one invocation")


if __name__ == "__main__":
    unittest.main()
