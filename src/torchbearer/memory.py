"""Append scientific claims and their typed Scientific Memory Graph relations."""

import json
from .contracts import verification_target
from .graph import ScientificMemoryGraph, index_claim, resolve_dependencies
from .store import Store, canonical

OUTCOMES = {"supported", "conditional", "counterexample", "failed_attempt", "unresolved", "corrected"}


def record_claim(store: Store, claim: dict):
    claim = json.loads(canonical(claim))
    required = {"id", "revision", "statement", "assumptions", "outcome", "evidence_ids", "topic_ids", "depends_on", "verification"}
    if required - claim.keys():
        raise ValueError(f"Missing fields: {sorted(required - claim.keys())}")
    if claim["outcome"] not in OUTCOMES or type(claim["revision"]) is not int or claim["revision"] < 1:
        raise ValueError("Invalid outcome or revision")
    for key in ["assumptions", "evidence_ids", "topic_ids", "depends_on"]:
        if not isinstance(claim[key], list):
            raise ValueError(f"{key} must be a list")
    if not isinstance(claim["id"], str) or not claim["id"].strip() or not isinstance(claim["statement"], str) or not claim["statement"].strip():
        raise ValueError("A claim needs a scientific statement")
    for key in ["assumptions", "evidence_ids", "topic_ids"]:
        if any(not isinstance(x, str) or not x.strip() for x in claim[key]) or len(set(claim[key])) != len(claim[key]):
            raise ValueError(f"{key} must contain distinct nonempty strings")
    verification = claim["verification"]
    if not isinstance(verification, dict) or set(verification) != {"agent", "human"} or verification["human"] is not None:
        raise ValueError("Human assessments enter through the authenticated human-review gateway")
    if claim["outcome"] == "failed_attempt" and not claim.get("failure_reason"):
        raise ValueError("Preserve what failed and why the attempt remains informative")
    previous = store.db.execute("SELECT MAX(revision) FROM claims WHERE id=?", (claim["id"],)).fetchone()[0]
    if claim["revision"] != (previous or 0) + 1:
        raise ValueError("Append the next revision; never replace retained scientific records")
    for artifact_id in claim["evidence_ids"]:
        store.get_artifact(artifact_id)
    claim['resolved_dependencies'] = resolve_dependencies(store, claim["depends_on"])
    if verification["agent"] is not None:
        case = store.db.execute("SELECT state,target_claim FROM cases WHERE id=?", (verification["agent"],)).fetchone()
        if not case or case['state'] != 'complete':
            raise ValueError("Reference a completed independent-verification case")
        if case['target_claim'] != canonical(verification_target(claim)):
            raise ValueError("The verification case must target this exact claim version, statement and evidence")
    ScientificMemoryGraph(store)
    with store.transaction():
        store.db.execute("INSERT INTO claims VALUES(?,?,?)", (claim["id"], claim["revision"], canonical(claim)))
        index_claim(store, claim)
        store.event("memory.revision", claim_id=claim["id"], revision=claim["revision"], outcome=claim["outcome"])
