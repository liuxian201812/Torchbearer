"""A deterministic backend for exercising the public protocol."""

from .contracts import Agent, Result, Task


class DemonstrationBackend:
    """Synthetic task outputs; no model credentials or network calls are needed."""

    def run(self, agent: Agent, task: Task, materials: list[dict]) -> Result:
        common = {"example_type": "synthetic_protocol_example", "agent_id": agent.id,
                  "parameter_id": agent.model.parameter_id,
                  "received_artifact_ids": [a["id"] for a in materials]}
        if task.kind == "blind_derivation":
            return Result("completed", {**common, "statement": "The sum of the first n positive odd integers is n squared.",
                          "assumptions": ["n is a nonnegative integer"],
                          "argument": "The induction step adds 2n+1 to n squared, producing (n+1) squared.",
                          "scope": "The supplied toy problem."})
        if task.kind == "comparison":
            return Result("completed", {**common, "agreement": "Both arguments yield the same identity.",
                          "discrepancies": [], "conditions": ["n is a nonnegative integer"],
                          "unresolved": [], "verification_type": "independent_then_comparison"})
        return Result("completed", {**common, "statement": "Toy sequence investigated.",
                      "evidence": "The expression agrees with direct evaluation for n=0,1,2.",
                      "next_action": "Compare the independently retained argument."})
