"""Run scientific-agent tasks, inspect durable state and review research traces."""

import argparse
import json
from .audit import AuditPolicy, scorecard
from .backends import DemonstrationBackend
from .command_backend import CommandBackend
from .contracts import Agent, ModelIdentity, Task
from .coordinator import Coordinator
from .memory import record_claim
from .graph import ScientificMemoryGraph
from .release import export_reviewed_claims, release_status
from .runtime import Runtime
from .store import Store


def summary(store: Store) -> dict:
    return {
        "tasks": [dict(r) for r in store.db.execute("SELECT id,state,attempts FROM tasks ORDER BY rowid")],
        "verification_cases": [dict(r) for r in store.db.execute("SELECT id,state,frozen_hash FROM cases")],
        "agents": store.db.execute("SELECT COUNT(*) FROM agents").fetchone()[0],
        "claim_revisions": store.db.execute("SELECT COUNT(*) FROM claims").fetchone()[0],
        "events": store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
    }


def demo(store: Store) -> dict:
    c = Coordinator(store)
    for name, role, parameter in [
        ("research-a", "researcher", "demo-weights-a"),
        ("research-b", "researcher", "demo-weights-b"),
        ("verify-a", "verifier", "demo-weights-c"),
        ("verify-b", "verifier", "demo-weights-d"),
        ("direction-a", "auditor", "demo-weights-e"),
    ]:
        c.register(Agent(name, role, ModelIdentity("synthetic", name, parameter)))
    store.put_artifact("toy:brief", {"problem": "Derive the sum of the first n positive odd integers.",
                                    "assumptions": ["n is a nonnegative integer"]}, visibility="restricted")
    store.put_artifact("toy:original", {"argument": "Use n terms, with endpoints 1 and 2n-1; their arithmetic mean is n, so the sum is n squared."},
                       visibility="restricted", origin="research-a")
    c.share("toy:brief", ["research-a", "research-b"])
    verified_claim = {"id": "toy-claim", "revision": 1,
        "statement": "The first n positive odd integers sum to n squared.",
        "assumptions": ["n is a nonnegative integer"], "outcome": "supported",
        "evidence_ids": ["toy-check:independent-account"], "topic_ids": ["toy-sequences"],
        "depends_on": [], "verification": {"agent": "toy-check", "human": None},
        "example_type": "synthetic_protocol_example"}

    def queue_once(task):
        if not store.db.execute("SELECT 1 FROM tasks WHERE id=?", (task.id,)).fetchone():
            c.submit(task)

    queue_once(Task("research-1", "research-a", "research", "Investigate the supplied toy sequence.", ("toy:brief",)))
    queue_once(Task("research-2", "research-b", "research", "Use an alternative representation for the toy sequence.", ("toy:brief",)))
    runtime = Runtime(c, DemonstrationBackend())
    runtime.run()
    if not store.db.execute("SELECT 1 FROM cases WHERE id='toy-check'").fetchone():
        c.begin_verification("toy-check", "research-a", "verify-a", ["toy:brief"], "toy:original",
                             target_claim=verified_claim)
    row = store.db.execute("SELECT state FROM cases WHERE id='toy-check'").fetchone()
    if row["state"] == "deriving":
        queue_once(Task("verify-1", "verify-a", "blind_derivation", "Derive the supplied toy result independently.",
                        ("toy:brief",), depends_on=("research-1",), case_id="toy-check"))
        runtime.run()
        c.freeze("toy-check", "verify-1")
    row = store.db.execute("SELECT state FROM cases WHERE id='toy-check'").fetchone()
    if row["state"] == "frozen":
        queue_once(c.comparison_task("toy-check", "compare-1"))
    row = store.db.execute("SELECT state FROM cases WHERE id='toy-check'").fetchone()
    if row["state"] == "comparing":
        runtime.run()
        c.close_comparison("toy-check", "compare-1")
    if not store.db.execute("SELECT 1 FROM claims WHERE id='toy-claim'").fetchone():
        record_claim(store, verified_claim)
        record_claim(store, {"id": "toy-failure", "revision": 1,
            "statement": "The trial formula n(n+1) does not describe the odd-integer sum.",
            "assumptions": ["n is a positive integer"], "outcome": "failed_attempt",
            "failure_reason": "At n=1 the formula gives 2 instead of 1.",
            "evidence_ids": ["toy:brief"], "topic_ids": ["toy-sequences"],
            "depends_on": [], "verification": {"agent": None, "human": None},
            "example_type": "synthetic_protocol_example"})
    return {"example_type": "synthetic_protocol_example", **summary(store)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["demo", "run", "status", "events", "audit", "graph", "trace", "impact", "release-status", "export-reviewed"])
    parser.add_argument("--state", default=".torchbearer/demo.sqlite")
    parser.add_argument("--trace", help="JSON trace used by the audit command")
    parser.add_argument("--policy", help="Optional audit policy JSON")
    parser.add_argument("--backend-config", help="Host-owned JSON agent-to-command mapping for run")
    parser.add_argument("--max-steps", type=int, default=100, help="Maximum dispatches in this run")
    parser.add_argument("--claim", action="append", help="Claim identity; repeat for a release packet")
    parser.add_argument("--revision", type=int, help="Exact claim revision for tracing or impact analysis")
    parser.add_argument("--depth", type=int, default=4, help="Maximum graph traversal depth")
    args = parser.parse_args()
    if args.command == "audit":
        if not args.trace:
            parser.error("audit requires --trace")
        policy = AuditPolicy()
        if args.policy:
            with open(args.policy, encoding="utf-8") as f:
                policy = AuditPolicy(**json.load(f))
        with open(args.trace, encoding="utf-8") as f:
            print(json.dumps(scorecard(json.load(f), policy), indent=2))
        return
    store = Store(args.state)
    try:
        if args.command in {"graph", "trace", "impact", "release-status", "export-reviewed"}:
            graph = ScientificMemoryGraph(store)
            if args.command == "graph":
                output = graph.snapshot()
            elif args.command in {"trace", "impact"}:
                if not args.claim or len(args.claim) != 1:
                    parser.error("trace and impact require exactly one --claim")
                if args.command == "impact" and args.revision is None:
                    parser.error("impact requires --revision")
                operation = graph.evidence_trace if args.command == "trace" else graph.affected_by
                output = operation(args.claim[0], args.revision, max_depth=args.depth)
            else:
                if not args.claim:
                    parser.error("Release operations require --claim")
                operation = release_status if args.command == "release-status" else export_reviewed_claims
                try:
                    output = operation(store, args.claim)
                except PermissionError as exc:
                    parser.error(str(exc))
        elif args.command == "run":
            if not args.backend_config or args.max_steps < 1:
                parser.error("run requires --backend-config and positive --max-steps")
            backend = CommandBackend.from_file(args.backend_config)
            queued = {json.loads(row[0])["agent_id"] for row in store.db.execute("SELECT spec FROM tasks WHERE state='pending'")}
            if queued - backend.commands.keys():
                parser.error("No worker configured for queued agents: " + ", ".join(sorted(queued - backend.commands.keys())))
            dispatched = Runtime(Coordinator(store), backend).run(max_steps=args.max_steps)
            output = {"dispatched": dispatched, **summary(store)}
        else:
            output = demo(store) if args.command == "demo" else store.events() if args.command == "events" else summary(store)
        print(json.dumps(output, ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
