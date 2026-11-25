"""End-to-end smoke test of a wheel installed outside its checkout."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
BIN = Path(sys.executable).parent

def cli(*args, cwd):
    p = subprocess.run([str(BIN / "torchbearer"), *args], cwd=cwd,
                       text=True, capture_output=True, check=True)
    return json.loads(p.stdout)

async def check_mcp():
    params = StdioServerParameters(command=str(BIN / "torchbearer-mcp"),
        args=["--corpus", str(ROOT / "examples/corpus.json"),
              "--scope", str(ROOT / "examples/verifier_scope.json")])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            assert {t.name for t in (await client.list_tools()).tools} == {"search_records", "read_record"}
            for identity in ("toy:brief", "toy:reference"):
                result = await client.call_tool("read_record", {"record_id": identity})
                assert not result.isError, identity
                if identity == "toy:reference":
                    assert "contribution_analysis" in json.dumps(result.model_dump())
            assert (await client.call_tool("read_record", {"record_id": "toy:original"})).isError
            result = await client.call_tool("search_records", {"query": "", "limit": 50})
            assert not result.isError and "toy:original" not in json.dumps(result.model_dump())
    print("PASS: installed MCP entry point, handshake, tools, source card and allowlist")

def check_skills():
    folders = sorted((ROOT / ".agents/skills").iterdir())
    assert len(folders) == 5
    for folder in folders:
        text = (folder / "SKILL.md").read_text()
        front = yaml.safe_load(text.split("---", 2)[1])
        assert front["name"] == folder.name and 0 < len(front["description"]) <= 1024
        ui = yaml.safe_load((folder / "agents/openai.yaml").read_text())["interface"]
        assert "$" + folder.name in ui["default_prompt"]
        import re
        for link in re.findall(r"\]\((references/[^)]+)\)", text):
            assert (folder / link).is_file()
    cfg = tomllib.loads((ROOT / "mcp/codex.example.toml").read_text())["mcp_servers"]["torchbearer"]
    claude = json.loads((ROOT / "mcp/claude.example.json").read_text())["mcpServers"]["torchbearer"]
    assert cfg["command"] == claude["command"] and cfg["args"] == claude["args"]
    print("PASS: five Skill manifests, local references and client configuration templates")

def main():
    assert "PYTHONPATH" not in os.environ
    check_skills()
    with tempfile.TemporaryDirectory() as directory:
        cwd = Path(directory)
        first = cli("demo", "--state", "demo.sqlite", cwd=cwd)
        assert first["agents"] == 5 and len(first["tasks"]) == 4
        assert all(t["state"] == "completed" for t in first["tasks"])
        assert first["claim_revisions"] == 2
        assert first["verification_cases"][0]["state"] == "complete"
        assert first["verification_cases"][0]["frozen_hash"]
        second = cli("demo", "--state", "demo.sqlite", cwd=cwd)
        assert first["tasks"] == second["tasks"]
        assert first["claim_revisions"] == second["claim_revisions"]
        assert first["verification_cases"] == second["verification_cases"]
        trace = cli("trace", "--state", "demo.sqlite", "--claim", "toy-claim", cwd=cwd)
        assert "toy-check:independent-account" in json.dumps(trace)
        cli("audit", "--trace", str(ROOT / "examples/audit_trace.json"), cwd=cwd)
        denied = subprocess.run([str(BIN / "torchbearer"), "export-reviewed", "--state",
                                 "demo.sqlite", "--claim", "toy-claim"], cwd=cwd,
                                 text=True, capture_output=True)
        assert denied.returncode != 0
        print("PASS: autonomous protocol demo, frozen verification, restart, trace and release gate")
        graph = subprocess.run([sys.executable, "-I", str(ROOT / "examples/graph_demo.py"),
                                "--state", "graph.sqlite"], cwd=cwd, text=True,
                               capture_output=True, check=True)
        graph = json.loads(graph.stdout)
        assert "shared-lemma" in json.dumps(graph["shared_claims"])
        assert "downstream-result" in json.dumps(graph["affected_by_lemma"])
        subprocess.run([sys.executable, "-I", str(ROOT / "examples/prepare_command_demo.py"),
                        "--state", "worker.sqlite", "--backend-config", "worker.json"],
                       cwd=cwd, check=True)
        run = cli("run", "--state", "worker.sqlite", "--backend-config", "worker.json", cwd=cwd)
        assert run["dispatched"] == 1 and run["tasks"][0]["state"] == "completed"
        assert cli("run", "--state", "worker.sqlite", "--backend-config", "worker.json",
                   cwd=cwd)["dispatched"] == 0
        print("PASS: graph reuse and dependency impact, external JSON worker and restart")
    asyncio.run(check_mcp())

if __name__ == "__main__":
    main()
