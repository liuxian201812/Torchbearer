# Scoped knowledge through MCP

The example server exposes two read-only tools over a prepared corpus:
`search_records` and `read_record`. A record may be a claim, literature card or
scientific brief. The host sets the allowed record IDs when it starts the
server; both tools use this configured scope.

```bash
python -m pip install '.[mcp]'
torchbearer-mcp --corpus examples/corpus.json --scope examples/verifier_scope.json
```

The server module and entry point are included in the installed package. Use
absolute corpus and scope paths when the agent host runs from another directory.
`python -m torchbearer.mcp_server` is an equivalent entry point.

Connect this command as a stdio MCP server in the agent host. For independent
verification, derive the scope from the coordinator's approved brief. Keep the
same restrictions on external knowledge tools and filesystem access.

The example uses the official Python SDK's v1 API, pinned to `mcp<2` in the
optional dependency. Its implementation follows the
[versioned official SDK documentation](https://py.sdk.modelcontextprotocol.io/v1/).
Tool contracts are listed in `tool_contracts.json`.

## Codex setup (recommended)

Open a trusted clone of the repository in Codex. Its project-level Skill directory
is `.agents/skills/`, with one self-contained folder per role. Codex discovers
the `SKILL.md` front matter; optional `agents/openai.yaml` files provide
display metadata. The five Skills use the open Agent Skills format. Invoke
`$torchbearer-coordinate`, `$torchbearer-research`,
`$torchbearer-paper-research`, `$torchbearer-verify` or
`$torchbearer-audit` in the appropriate context.

Register the local MCP server from the repository root after
installing the package. POSIX shell example (replace the interpreter with the
installed virtual environment's absolute Python path if necessary):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install '.[mcp]'
codex mcp add torchbearer -- "$PWD/.venv/bin/python" -m torchbearer.mcp_server --corpus "$PWD/examples/corpus.json" --scope "$PWD/examples/verifier_scope.json"
codex mcp list
```

In Codex use `/mcp` to inspect the connection. Alternatively merge
[`codex.example.toml`](codex.example.toml) into your user
`~/.codex/config.toml` or trusted project `.codex/config.toml` after replacing
all absolute-path placeholders.
On Windows use the absolute virtual-environment `Scripts/python.exe` path
and absolute corpus/scope paths.

## Claude Code setup (optional)

From the repository root, copy the portable Skill directories into the
Claude Code project discovery directory (POSIX shell):

```bash
mkdir -p .claude/skills
cp -R .agents/skills/torchbearer-* .claude/skills/
```

On Windows, copy those same directories into `.claude/skills/` with your
file manager or PowerShell. Claude Code uses the `SKILL.md` files; the
Codex-specific UI metadata can be left in place. Invoke the role, for example
`/torchbearer-research`. The generated copies are ignored by Git; refresh them
after updating the repository. The canonical source remains `.agents/skills/`.

After installing the same Python package, register the server:

```bash
claude mcp add --transport stdio --scope local torchbearer -- "$PWD/.venv/bin/python" -m torchbearer.mcp_server --corpus "$PWD/examples/corpus.json" --scope "$PWD/examples/verifier_scope.json"
claude mcp list
```

Alternatively merge [`claude.example.json`](claude.example.json) into a local
project `.mcp.json` after replacing the placeholders and approve the connection
in Claude Code. Use `/mcp` to inspect it.

## Verification scope

The examples use a **synthetic**, read-only corpus and a verifier allowlist.
Keep deployment corpus paths, scope files, credentials and settings in local
configuration outside version control.

Create a separate scoped server and context for each independent verifier.
Configure the host to enforce the approved brief across MCP, filesystem access
and other tools. After the independent account is retained, the host releases the
original argument by updating the scoped server or delivering the comparison
packet to the **same verifier context**.

A smoke check should list exactly `search_records` and `read_record`, read
`toy:brief` and `toy:reference`, reject `toy:original`, and exclude it from
search results. The optional SDK-backed test in `tests/test_framework.py`
exercises the stdio connection and scope.

Official references: [Codex Skills](https://developers.openai.com/codex/skills),
[Codex MCP](https://developers.openai.com/codex/mcp),
[Agent Skills specification](https://agentskills.io/specification),
[Claude Code Skills](https://code.claude.com/docs/en/skills) and
[Claude Code MCP](https://code.claude.com/docs/en/mcp).

## Data contract

Every record has an identity, kind, title and text, with optional provenance
and scientific conditions. Search results reveal
only records within the configured scope. Reading a record outside that scope
is rejected. The server reads the local corpus; the host handles source acquisition.

For a deployment corpus, keep stable record identities and explicit source
versions. Publish validated scientific records through the coordinator's memory
workflow, then expose the appropriate read views to agent contexts.
