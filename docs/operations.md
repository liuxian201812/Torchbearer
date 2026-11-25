# Persistent operation and backend integration

The coordinator supervises researchers, verifiers and direction auditors, routing
their tasks and materials through the runtime. SQLite stores agent identities,
material grants, verification state, claim revisions and an event log. Each task
retains its identity, dependencies, attempt limit and result. Completed work
remains completed when the runtime is reopened.

## Dispatch and recovery

`Runtime.tick` selects an eligible task and records dispatch before invoking its
backend. On return, it records the outcome and next state in a transaction.
`Runtime.run(max_steps=...)` advances eligible work within an explicit dispatch
budget. An external host can invoke this loop repeatedly and supervise its
process to sustain research over longer periods.

| Backend result | Runtime action |
|---|---|
| `completed` | Retain the result and release dependent tasks |
| `retryable_failure` | Retry a confirmed non-execution or idempotent operation within the attempt limit |
| `unknown` | Hold the task for receipt-based reconciliation |

After confirming that an earlier owner has stopped, call
`recover_interrupted(confirmed_stopped=True)`. Running tasks become held until
their outcomes are resolved. Use `reconcile` with a returned result or evidence
of non-execution before continuing. The event log preserves the original
invocation and recovery.

A retryable result includes `retry_basis` (`confirmed_not_executed` or
`idempotent_operation`) and a `receipt` explaining that classification. An
ordinary failure can have partial effects; missing retry-safety evidence places
the task on hold. For idempotent operations, the adapter uses the stable task
identity as the operation key.

The example scheduler dispatches serially. A host may run multiple agent workers
behind the same coordinator; it should preserve the task identity, access scope,
state transitions and receipt semantics while adding worker leases and resource
limits appropriate to its infrastructure.

## Connect an agent environment

Use [CommandBackend](command-backend.md) for a host-owned worker process, or
implement `AgentBackend.run(agent, task, materials)` and return `Result`.

1. Bind the declared model deployment and its parameter identity.
2. Create or resume the assigned agent context, respecting verification stage.
3. Supply the task and permitted materials; configure matching tool scopes.
4. Execute the agent with the deployment's computation and resource budget.
5. Retain the returned scientific artifact and classify the invocation outcome.

Reuse a verifier's context for comparison after its independent account has been
retained. A new independent check uses an unexposed context. The adapter owns
timeouts, process isolation, cancellation and provider-specific receipts.

## Direction constraints and optional intervention

`Coordinator.guide` appends human guidance to the control record and can pause
new dispatches. The coordinator interprets the guidance and prepares subsequent
tasks. `resume` permits dispatch again. Scientific messages follow the same
material scopes as other task inputs. The agents continue scientific planning
and execution within the current direction and resource constraints. Final human
assessment governs scientific-result release; internal task dispatch proceeds
under the coordinator and runtime.

## Scientific sources

The coordinator requests source material through an acquisition adapter. Supply
open repositories, publisher access authorized for the deployment, institutional
services, or user-provided files. Retain DOI or canonical identity, publication
version, acquisition provenance and evidence locations. Metadata and abstracts
support discovery; technical claims should reference the relevant full text.

The included MCP service reads an already prepared corpus. Acquisition,
conversion and corpus publication are separate adapter responsibilities.

## Scientific graph and publication state

The same state database stores typed Scientific Memory Graph nodes and edges.
Use `torchbearer trace` to inspect evidence and `torchbearer impact` to identify
downstream claims connected to a revised premise. Human review is a separate
host operation; `torchbearer release-status` reports the exact prerequisites
still awaiting assessment, and `torchbearer export-reviewed` creates an eligible
scientific-result packet. See [scientific-memory.md](scientific-memory.md) and
[human-review.md](human-review.md).
