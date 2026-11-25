# Architecture and collaboration

Torchbearer extends an existing agent environment through three connected parts.

| Part | Responsibility | Public entry |
|---|---|---|
| Skills | Research procedures, role behavior and expected evidence | `.agents/skills/` |
| MCP knowledge services | Scoped access to scientific records and source material | `mcp/` |
| Project workflow contracts | Task identity, collaboration, memory, verification and recovery | `docs/`, `schemas/` |

The reference runtime supplies task, memory and verification interfaces. Host
adapters supply model inference, computation and external source acquisition.
Agents are identified by role, task context and model deployment. Researchers
select questions, methods and subsequent actions within the supplied direction
and resource constraints.

## One coordinator, three peer agent roles

One coordinator supervises three peer agent roles: researchers, verifiers and
direction auditors. It maintains the shared goal and dependency-aware work
queue, assigns tasks and access, and routes materials and feedback among the
agents. Researchers drive investigation; verifiers and direction auditors
support it through checks and recommendations routed by the coordinator.

Research continues throughout this collaboration. The lead researcher sends
material requests, intermediate findings and proposed next actions to the
coordinator; the coordinator returns sources, computation results and supporting
work. Each exchange helps the researcher refine the question or advance the
argument.

Independent verification branches from this ongoing work when an important
question or a mature claim is selected for checking. The researcher continues
the investigation while the verifier derives and compares an independent
account. The coordinator returns corrections, additional conditions and
follow-up questions to the researcher. The Scientific Memory Graph retains
research records and links checked claims to their exact verification evidence
for later reuse.

| Role | Scientific responsibility | Coordinator interaction |
|---|---|---|
| Researcher | Drive investigation: select questions and methods, derive or compute, interpret evidence and choose next steps | Request resources, share findings, submit claims and verification requests |
| Verifier | Support research by independently deriving and then comparing selected claims | Receive a scoped brief and staged disclosure; return the frozen account and comparison |
| Direction auditor | Support research by assessing progress, exploration and the basis for continuation or scope changes | Receive a trace and supporting sources; return evidence-linked recommendations |

Material requests are first-class coordination tasks: a researcher can identify
a missing source, a computation dependency or an artifact needed by several
agents. The coordinator assigns acquisition or preparation to an appropriate
service, records its provenance and distributes the resulting material to its
authorized recipients. Scientific next-step decisions remain with the responsible
researcher, informed by the received evidence and audit feedback.

Researchers use [contribution cards](contribution-cards.md) to compare the
question, evidence and scientific advance of relevant precedents with their
own work. The coordinator makes these shared source records available to the
appropriate research and audit contexts.

## Access follows the task

Shared research context and independent verification context have different
scopes. A common artifact can be granted to several collaborators. During an
independent derivation, the verifier receives only the approved scientific brief
and initial evidence. Coordination includes preserving that separation across
messages, linked records and tool results.

The host runs each agent in a distinct context. Its tool broker enforces the
assigned allowlist across knowledge retrieval, linked records and other tools.

## Direction constraints, intervention and scientific assessment

Humans provide direction constraints and may submit an idea or correction
through the coordinator at any stage. The coordinator translates that input into
revised tasks and access scopes while the agents plan and execute the research.
A human can also pause the workflow. The runtime checks pause
state before each dispatch; cancellation of an active backend call is handled
by that backend's host interface.

Human scientists also perform the final scientific assessment: they examine
mathematical correctness, assess physical meaning and authorize which exact
results may be disclosed. AI derivations and agent comparisons remain internal
research records until that assessment is recorded. The publication gateway
checks the selected claim revision and its prerequisite versions. Every new
revision requires its own approval. See
[human-review.md](human-review.md) for the authenticated host boundary.

## Backend integration

`AgentBackend.run(agent, task, materials)` is the inference adapter. It returns a
completed result, a definite retryable failure, or an unknown outcome. The host
records the actual model parameter identity, invocation and resource policy.
The included deterministic backend exercises these interfaces. A deployment
connects the same contracts to its agent runtime and scientific tools.
