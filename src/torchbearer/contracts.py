"""Backend-independent task and agent contracts."""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["researcher", "verifier", "auditor"]


@dataclass(frozen=True)
class ModelIdentity:
    provider: str
    model: str
    parameter_id: str

    def __post_init__(self):
        values = (self.provider, self.model, self.parameter_id)
        if not all(isinstance(x, str) and x and x == x.strip() for x in values):
            raise ValueError("Declare canonical provider, model and parameter identities without surrounding whitespace")
        if self.parameter_id.lower() in {"unknown", "default", "unset"}:
            raise ValueError("The parameter identity must identify the deployed model")


@dataclass(frozen=True)
class Agent:
    id: str
    role: Role
    model: ModelIdentity

    def __post_init__(self):
        if not self.id or self.role not in {"researcher", "verifier", "auditor"}:
            raise ValueError("Invalid agent identity or role")


@dataclass(frozen=True)
class Task:
    id: str
    agent_id: str
    kind: str
    goal: str
    artifact_ids: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    max_attempts: int = 3
    case_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id or not self.goal or type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ValueError("Tasks need an identity, goal and positive attempt bound")


@dataclass(frozen=True)
class Result:
    """A retryable failure needs retry_basis and receipt in content.

    retry_basis is confirmed_not_executed or idempotent_operation. A generally
    known failure is not enough: an invocation may have had partial effects.
    """

    status: Literal["completed", "retryable_failure", "unknown"]
    content: dict[str, Any]


class AgentBackend(Protocol):
    """The host binds the agent identity; prompts cannot select another identity."""

    def run(self, agent: Agent, task: Task, materials: list[dict[str, Any]]) -> Result:
        """Run one task; supply receipt-backed retry safety or classify as unknown."""
        ...


def as_json(value: Any) -> dict[str, Any]:
    return asdict(value)


def verification_target(claim: dict, *, dependencies: list[dict] | None = None) -> dict:
    """Identify the exact scientific claim a verification case was assigned."""
    fields = ("id", "revision", "statement", "assumptions", "evidence_ids")
    if dependencies is None:
        dependencies = claim.get("resolved_dependencies", claim.get("depends_on", []))
    return {**{key: claim[key] for key in fields}, "depends_on": dependencies}
