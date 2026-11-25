"""Queue a synthetic task and configure its independent worker process."""

import argparse
import json
from pathlib import Path
import sys

from torchbearer.contracts import Agent, ModelIdentity, Task
from torchbearer.coordinator import Coordinator
from torchbearer.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True)
    parser.add_argument("--backend-config", required=True)
    args = parser.parse_args()
    store = Store(args.state)
    try:
        coordinator = Coordinator(store)
        coordinator.register(Agent("command-example", "researcher",
            ModelIdentity("synthetic", "stdio-example", "synthetic-parameters")))
        store.put_artifact("command:brief", {"question": "Receive a synthetic scientific brief."}, visibility="restricted")
        coordinator.share("command:brief", ["command-example"])
        if not store.db.execute("SELECT 1 FROM tasks WHERE id='command-task'").fetchone():
            coordinator.submit(Task("command-task", "command-example", "research",
                                   "Exercise the worker protocol.", ("command:brief",)))
        config = Path(args.backend_config)
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps({"agents": {"command-example": {
            "argv": [sys.executable, str(Path(__file__).with_name("stdio_worker.py").resolve())],
            "timeout_seconds": 30}}}, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"example_type": "synthetic_protocol_example", "state": str(Path(args.state).resolve()),
                          "backend_config": str(config.resolve())}))
    finally:
        store.close()


if __name__ == "__main__":
    main()
