"""Evidence-linked tests for premature closure and search-path contraction."""

from collections import Counter
from dataclasses import dataclass
from math import exp, isfinite, log
from typing import Any


@dataclass(frozen=True)
class AuditPolicy:
    minimum_effective_family_drop: float = 0.0
    require_matched_windows: bool = True

    def __post_init__(self):
        value = self.minimum_effective_family_drop
        if (type(value) not in {int, float} or not isfinite(value) or value < 0
                or type(self.require_matched_windows) is not bool):
            raise ValueError("Use a finite nonnegative diversity drop and boolean window-matching rule")


def validate_trace(trace: dict[str, Any]):
    def identifier(value):
        return isinstance(value, str) and bool(value) and value == value.strip()

    def string_list(value):
        return isinstance(value, list) and all(identifier(x) for x in value) and len(set(value)) == len(value)

    def basis(row):
        return isinstance(row.get("basis"), str) and bool(row["basis"].strip()) and string_list(row.get("source_ids")) and bool(row["source_ids"])

    if (not isinstance(trace, dict) or trace.get("schema_version") != 2
            or not identifier(trace.get("window_id")) or type(trace.get("termination_requested")) is not bool):
        raise ValueError("A version-2 trace needs a window identity and boolean termination_requested")
    for key in ("steps", "previous_steps", "candidates", "actions", "evidence", "assessments"):
        rows = trace.get(key)
        if not isinstance(rows, list) or not all(isinstance(row, dict) and identifier(row.get("id")) for row in rows):
            raise ValueError(f"{key} must be records with canonical IDs")
        if len({row["id"] for row in rows}) != len(rows):
            raise ValueError(f"Duplicate {key} IDs")
    candidates = {c["id"]: c for c in trace["candidates"]}
    evidence = {e["id"] for e in trace["evidence"]}
    actions = {a["id"] for a in trace["actions"]}
    baseline = trace.get("baseline_evidence_ids")
    if not string_list(baseline) or not set(baseline).issubset(evidence):
        raise ValueError("Baseline evidence must refer to declared evidence records")
    for row in trace["candidates"]:
        if not identifier(row.get("method_family")) or not isinstance(row.get("description"), str) or not row["description"].strip():
            raise ValueError("Each candidate needs a description and a fixed method-family label")
    for row in trace["evidence"]:
        if not basis(row):
            raise ValueError("Evidence records need a scientific basis and source references")
    seen = set()
    for collection in ("previous_steps", "steps"):
        for row in trace[collection]:
            cid = row.get("candidate_id")
            if (row["id"] in seen or not identifier(cid) or cid not in candidates
                    or row.get("method_family") != candidates[cid]["method_family"]
                    or not string_list(row.get("new_evidence_ids"))
                    or not set(row["new_evidence_ids"]).issubset(evidence)):
                raise ValueError("Steps need unique IDs, fixed candidate families and declared evidence references")
            if collection == "previous_steps" and not set(row["new_evidence_ids"]).issubset(baseline):
                raise ValueError("Evidence from the preceding window belongs in the baseline")
            seen.add(row["id"])
    for row in trace["actions"]:
        if (type(row.get("feasible")) is not bool or not identifier(row.get("candidate_id"))
                or row["candidate_id"] not in candidates or not basis(row)
                or row.get("status") not in {"ready", "running", "completed", "blocked", "ruled_out", "deferred"}):
            raise ValueError("Each action needs a candidate, explicit status, boolean feasibility and referenced basis")
    focus = trace.get("focus")
    if (not isinstance(focus, dict) or not isinstance(focus.get("reason"), str)
            or not string_list(focus.get("supporting_evidence_ids"))
            or not set(focus["supporting_evidence_ids"]).issubset(evidence)):
        raise ValueError("A focus rationale needs a reason and declared evidence references")
    for row in trace["assessments"]:
        if not string_list(row.get("source_ids")) or not row["source_ids"]:
            raise ValueError("Each assessment needs source references")
        for key in ("goal_narrowed", "limitation_identified", "feasible_followup"):
            if key in row and type(row[key]) is not bool:
                raise ValueError(f"{key} must be boolean")
        linked = row.get("supporting_evidence_ids", [])
        if not string_list(linked) or not set(linked).issubset(evidence):
            raise ValueError("Supporting evidence must refer to declared evidence records")
        if row.get("followup_action_id") is not None and (not identifier(row["followup_action_id"]) or row["followup_action_id"] not in actions):
            raise ValueError("A follow-up action must refer to a declared action")


def effective_families(steps: list[dict]) -> float | None:
    """Exponential Shannon entropy of substantive steps over fixed method families."""
    counts = Counter(step["method_family"] for step in steps)
    total = sum(counts.values())
    return exp(-sum((n / total) * log(n / total) for n in counts.values())) if total else None


def scorecard(trace: dict[str, Any], policy: AuditPolicy = AuditPolicy()) -> dict:
    """Calculate reproducible observations; the auditor interprets their science."""
    validate_trace(trace)
    steps, previous = trace["steps"], trace["previous_steps"]
    families = {c["id"]: c["method_family"] for c in trace["candidates"]}
    frontier = [a for a in trace["actions"] if a["feasible"] and a["status"] in {"ready", "running", "deferred"}]
    current_d, previous_d = effective_families(steps), effective_families(previous)
    comparable = bool(steps and previous) and (len(steps) == len(previous) or not policy.require_matched_windows)
    drop = previous_d - current_d if comparable else None
    counts = Counter(s["method_family"] for s in steps)
    dominant = sorted(counts, key=lambda key: (-counts[key], key))[0] if counts else None
    alternatives = [a for a in frontier if dominant is not None and families[a["candidate_id"]] != dominant]
    observed = set().union(*(set(s["new_evidence_ids"]) for s in steps)) if steps else set()
    gain = observed - set(trace["baseline_evidence_ids"])
    focus = trace["focus"]
    supported_focus = bool(focus["reason"].strip() and focus["supporting_evidence_ids"])
    contraction = len(steps) >= 2 and (
        (drop is not None and drop > policy.minimum_effective_family_drop + 1e-12)
        or (current_d is not None and current_d <= 1 + 1e-12))
    assessments = trace["assessments"]
    unsupported = [a for a in assessments if a.get("goal_narrowed") and not a.get("supporting_evidence_ids")]
    unactioned = [a for a in assessments if a.get("limitation_identified") and a.get("feasible_followup") and not a.get("followup_action_id")]
    cues = []
    if trace["termination_requested"] and frontier:
        cues.append("premature_research_closure")
    if contraction and alternatives and not gain and not supported_focus:
        cues.append("search_path_contraction")
    if unsupported:
        cues.append("scope_change_needs_scientific_basis")
    if unactioned:
        cues.append("feasible_followup_not_scheduled")
    return {
        "schema_version": 2,
        "review_window": trace["window_id"],
        "metrics": {
            "actionable_frontier": len(frontier),
            "current_effective_method_families": current_d,
            "previous_effective_method_families": previous_d,
            "comparable_windows": comparable,
            "effective_family_drop": drop,
            "current_substantive_steps": len(steps),
            "previous_substantive_steps": len(previous),
            "new_evidence_items": len(gain),
            "actionable_alternative_methods": len({families[a["candidate_id"]] for a in alternatives}),
            "evidence_supported_focus": supported_focus,
            "unsupported_scope_changes": len(unsupported),
            "unactioned_feasible_followups": len(unactioned),
        },
        "review_cues": cues,
        "action_ids": [a["id"] for a in frontier],
        "alternative_action_ids": [a["id"] for a in alternatives],
        "new_evidence_ids": sorted(gain),
        "assessment_ids": list(dict.fromkeys(a["id"] for a in unsupported + unactioned)),
        "decision": "review" if cues else "no_rule_trigger",
        "policy": {"minimum_effective_family_drop": policy.minimum_effective_family_drop,
                   "require_matched_windows": policy.require_matched_windows},
    }
