# Reference implementation validation

## Recorded evidence

The review fixes were tested on 26 November 2026 (UTC+8) using a newly built
wheel in two fresh environments with Python 3.12.14:

| Installation | Result |
|---|---|
| Core wheel, tests launched from the repository root | 49 passed; the optional MCP test skipped |
| Wheel with MCP 1.30.0, tests launched outside the checkout | All 50 passed |
| Installed CLI and MCP end-to-end script | Demo, restart, graph, external worker and scoped stdio checks passed |

Nine new regressions cover verification-stage task assignment, exact claim and
prerequisite binding, faithful empty-result recovery, integer execution budgets
and migration of existing case tables. The stdio test additionally checks the
advertised search range and strict input types.

### Earlier CI and client checks

Before the review fixes, the
[isolated GitHub Actions workflow](https://github.com/liuxian201812/Torchbearer/actions/workflows/isolated-e2e.yml)
passed its initial 41 tests and installed CLI/MCP smoke test on 26 November 2026
(UTC+8), using Python 3.12.16 and MCP 1.30.0. A fresh hosted Linux runner built the
wheel, installed it non-editably in a separate virtual environment, and ran from
a copied test directory without `src/`. Python imported `torchbearer` from that
environment's `site-packages`.

Client discovery was checked separately using a newly installed wheel with
Python 3.12.14 and MCP 1.30.0. Real Codex CLI `0.172.0-alpha.2` app-server requests
confirmed:

- `skills/list` discovered all five repository Skills, enabled, with their
  `agents/openai.yaml` metadata and no discovery errors.
- `mcpServerStatus/list` connected to the installed server and discovered
  `search_records` and `read_record`, with no tool-discovery error.

These process-local checks covered Skill and MCP discovery without model
inference. Claude Code client execution remains untested in this review.
Subsequent CI runs appear in the
[workflow history](https://github.com/liuxian201812/Torchbearer/actions/workflows/isolated-e2e.yml).

## Test coverage

The suite covers task dependencies, material access, declared model identities,
independent derivation before disclosure to the same verifier, retained reports,
claim revisions, pause/resume, bounded retries and interruption recovery. Graph
and human-review tests exercise evidence tracing, exact prerequisite revisions,
review objections and release eligibility. Process tests cover nonzero exits,
timeouts, malformed responses and abrupt runtime-owner death; ambiguous outcomes
remain held for reconciliation.

The installed-package smoke test runs the synthetic research/verification demo,
checks restart behavior, traces evidence, rejects unreviewed release, traverses
the memory graph and dispatches an external JSON worker. Its real MCP stdio
session reads allowed records and rejects the hidden original argument.

The workflow tests the core-only installation from the repository root before
installing MCP. SDK detection checks the installed distribution to distinguish
it from the repository's `mcp/` directory. Protocol tests check the advertised
`limit` range of 1–50 and reject booleans, strings and out-of-range limits through
the actual stdio interface.

The tests exercise the protocol with synthetic scientific and human-review
fixtures. Live-model research performance remains a separate evaluation using
the deployment's model workers, persistent contexts, tool scopes and scientific
data.

## Reproduce both installation paths

Run these POSIX-shell commands from the repository root. Each environment is
new, and the full integration test runs outside the source checkout:

```bash
check_root="$(mktemp -d)"
python -m venv "$check_root/build-env"
"$check_root/build-env/bin/python" -m pip install build
"$check_root/build-env/bin/python" -m build --wheel --outdir "$check_root/wheels"

# Basic installation: run from the checkout, where mcp/ is present.
python -m venv "$check_root/core-env"
"$check_root/core-env/bin/python" -m pip install --no-deps "$check_root"/wheels/*.whl
unset PYTHONPATH
"$check_root/core-env/bin/python" -m unittest discover -s tests -v

# Integration installation: use the wheel and optional protocol dependencies.
python -m venv "$check_root/check-env"
"$check_root/check-env/bin/python" -m pip install "$check_root"/wheels/*.whl 'mcp>=1.12,<2' PyYAML
mkdir -p "$check_root/check-data"
cp -R tests examples .agents mcp "$check_root/check-data/"
cd "$check_root/check-data"
"$check_root/check-env/bin/python" -I -c 'import pathlib, sys, torchbearer; assert pathlib.Path(torchbearer.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix))'
"$check_root/check-env/bin/python" -I -m unittest discover -s tests -v
"$check_root/check-env/bin/python" -I tests/e2e_installed.py
```

The basic installation skips the optional MCP test. The integration installation
must execute it. See [command-backend.md](command-backend.md) and
[MCP setup](../mcp/README.md) for worker and client configuration.
