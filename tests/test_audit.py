import json
from pathlib import Path
import unittest

from torchbearer.audit import AuditPolicy, scorecard

ROOT = Path(__file__).resolve().parents[1]


class AuditRulesTest(unittest.TestCase):
    def trace(self):
        trace = json.loads((ROOT / "examples/audit_trace.json").read_text())
        trace["assessments"] = []
        return trace

    def test_blocked_excluded_and_completed_work_do_not_block_closure(self):
        for status in ("blocked", "ruled_out", "completed"):
            trace = self.trace()
            trace["actions"][0]["status"] = status
            with self.subTest(status=status):
                self.assertEqual(scorecard(trace)["review_cues"], [])

    def test_deferred_feasible_work_remains_in_frontier(self):
        trace = self.trace()
        trace["actions"][0]["status"] = "deferred"
        self.assertIn("premature_research_closure", scorecard(trace)["review_cues"])

    def test_productive_concentration_does_not_trigger_contraction(self):
        trace = self.trace()
        trace["termination_requested"] = False
        trace["evidence"].append({"id": "fresh", "basis": "A new constraint follows from the calculation.", "source_ids": ["s3"]})
        trace["steps"][-1]["new_evidence_ids"] = ["fresh"]
        result = scorecard(trace)
        self.assertEqual(result["metrics"]["new_evidence_items"], 1)
        self.assertEqual(result["review_cues"], [])

    def test_supported_focus_is_distinct_from_arbitrary_repetition(self):
        trace = self.trace()
        trace["termination_requested"] = False
        trace["focus"] = {"reason": "The established starting result requires a longer recurrence calculation.",
                          "supporting_evidence_ids": ["e0"]}
        self.assertEqual(scorecard(trace)["review_cues"], [])
        trace["focus"]["supporting_evidence_ids"] = []
        self.assertEqual(scorecard(trace)["review_cues"], ["search_path_contraction"])

    def test_reused_baseline_evidence_is_not_counted_as_progress(self):
        trace = self.trace()
        trace["termination_requested"] = False
        for step in trace["steps"]:
            step["new_evidence_ids"] = ["e0"]
        result = scorecard(trace)
        self.assertEqual(result["metrics"]["new_evidence_items"], 0)
        self.assertEqual(result["review_cues"], ["search_path_contraction"])

    def test_without_an_actionable_alternative_concentration_is_not_flagged(self):
        trace = self.trace()
        trace["termination_requested"] = False
        trace["actions"][0]["candidate_id"] = "c1"
        result = scorecard(trace)
        self.assertEqual(result["metrics"]["actionable_alternative_methods"], 0)
        self.assertEqual(result["review_cues"], [])

    def test_empty_and_unequal_windows_do_not_report_a_diversity_drop(self):
        trace = self.trace()
        trace["previous_steps"] = trace["previous_steps"][:2]
        result = scorecard(trace)
        self.assertFalse(result["metrics"]["comparable_windows"])
        self.assertIsNone(result["metrics"]["effective_family_drop"])
        self.assertIn("search_path_contraction", result["review_cues"])
        trace["steps"] = []
        result = scorecard(trace)
        self.assertIsNone(result["metrics"]["current_effective_method_families"])
        self.assertNotIn("search_path_contraction", result["review_cues"])

    def test_scientific_reference_integrity(self):
        mutations = [
            lambda t: t["steps"][0].update(method_family="new-label"),
            lambda t: t["steps"][0].update(new_evidence_ids=["absent-evidence"]),
            lambda t: t.update(baseline_evidence_ids=[]),
            lambda t: t["actions"][0].update(source_ids=[]),
            lambda t: t["previous_steps"][0].update(id="s1"),
        ]
        for mutation in mutations:
            trace = self.trace()
            mutation(trace)
            with self.assertRaises(ValueError):
                scorecard(trace)

    def test_policy_requires_finite_numeric_threshold_and_boolean_window_rule(self):
        for value in (float("nan"), float("inf"), -1, True, "0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                AuditPolicy(minimum_effective_family_drop=value)
        with self.assertRaises(ValueError):
            AuditPolicy(require_matched_windows="true")


if __name__ == "__main__":
    unittest.main()
