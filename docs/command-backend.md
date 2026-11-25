# Connect agent workers through commands

`CommandBackend` connects agent workers through JSON input/output. The host maps
agent identities to executable commands. Each command receives one JSON request
on standard input and returns one JSON result on standard output. Commands run
directly with `shell=False`.

## Exercise the complete process boundary

After installing the package, run this synthetic example from the repository:

```bash
python examples/prepare_command_demo.py --state .torchbearer/command.sqlite --backend-config .torchbearer/commands.json
torchbearer run --state .torchbearer/command.sqlite --backend-config .torchbearer/commands.json
torchbearer status --state .torchbearer/command.sqlite
```

The preparation script registers one example agent, stores a brief and queues a
task. It writes a configuration with absolute worker paths. The CLI dispatches
the task to a separate process, stores its result and preserves completion on
restart. The example worker produces a deterministic response that echoes
permitted material identities. The Python API supports the same process backend
for multiple researchers, verifiers and auditors.

## Host configuration

```json
{
  "agents": {
    "research-a": {
      "argv": ["/absolute/path/to/worker", "--deployment", "research"],
      "timeout_seconds": 600,
      "cwd": "/absolute/path/to/project"
    }
  }
}
```

`argv` is an argument list. `cwd` is optional; a relative directory is resolved
against the configuration file. The default timeout is 600 seconds. Keep this
configuration under host control and supply credentials through the host's
secret mechanism. Use placeholders in shared example files. The CLI checks that
all pending agents have configured workers before dispatch.

## Worker request and response

The request contains `protocol_version: 1`, the registered `agent` (including
model and parameter identities), the complete `task` and its permitted
`materials`. Task and agent IDs are stable keys for dispatch receipts and
persistent contexts. The worker should bind the declared model deployment,
select the assigned context, configure matching tool scopes and execute its
scientific work.

A successful response has this form:

```json
{"status": "completed", "content": {"statement": "...", "evidence_ids": ["..."]}}
```

Supported statuses are `completed`, `retryable_failure` and `unknown`; `content`
is an object. A retryable response must include a `retry_basis` and `receipt`,
as described in [operations](operations.md). Logs belong on standard error;
standard output must contain only the response JSON.

Timeouts, nonzero exits and malformed responses become `unknown`. The runtime
holds them for reconciliation because an external action may have occurred.
A worker exit may leave a remote invocation or computation running. Resolve
uncertain work with provider receipts and the stable task ID before retrying.

## Deployment responsibilities

The adapter provides process transport and material routing; the runtime retains
scheduling state. The host supplies inference, authenticated tools, resource
limits, persistent contexts and scientific procedures. It binds research and
verification agents to distinct deployed parameter sets; the framework validates
their declared identities.

Material scopes constrain the inputs delivered by the framework. Configure the
same restrictions in filesystem permissions, knowledge services and other tools
available to a worker. Each independent verification case starts in an unexposed
context, including when an agent ID is reused. Resume that same context for
comparison after disclosure.
