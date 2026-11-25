"""Connect host-configured agent workers through a JSON stdin/stdout contract."""

from dataclasses import dataclass
import json
from math import isfinite
from pathlib import Path
import subprocess

from .contracts import Agent, Result, Task, as_json


@dataclass(frozen=True)
class WorkerCommand:
    argv: tuple[str, ...]
    timeout_seconds: float = 600
    cwd: str | None = None

    def __post_init__(self):
        if not isinstance(self.argv, (tuple, list)) or not self.argv or not all(isinstance(x, str) and x and "\x00" not in x for x in self.argv):
            raise ValueError("argv must contain nonempty command arguments")
        if (type(self.timeout_seconds) not in {int, float} or not isfinite(self.timeout_seconds)
                or self.timeout_seconds <= 0):
            raise ValueError("timeout_seconds must be positive and finite")
        if self.cwd is not None and not Path(self.cwd).is_dir():
            raise ValueError("The worker working directory must exist")


class CommandBackend:
    """Dispatch an agent to its host-owned command; task text never selects it."""

    def __init__(self, commands: dict[str, WorkerCommand]):
        if not isinstance(commands, dict) or not commands or not all(
                isinstance(k, str) and k and isinstance(v, WorkerCommand) for k, v in commands.items()):
            raise ValueError("Configure a worker command for each dispatchable agent")
        self.commands = dict(commands)

    @classmethod
    def from_file(cls, path: str | Path):
        path = Path(path).resolve()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != {"agents"} or not isinstance(data["agents"], dict):
            raise ValueError("Backend configuration must contain an agents mapping")
        commands = {}
        for agent_id, config in data["agents"].items():
            if (not isinstance(config, dict) or "argv" not in config
                    or set(config) - {"argv", "timeout_seconds", "cwd"}
                    or not isinstance(config["argv"], list)):
                raise ValueError("Each agent command needs argv and optional timeout_seconds/cwd")
            cwd = config.get("cwd")
            if cwd is not None:
                if not isinstance(cwd, str):
                    raise ValueError("cwd must be a directory path")
                cwd = str((path.parent / cwd).resolve())
            commands[agent_id] = WorkerCommand(tuple(config["argv"]), config.get("timeout_seconds", 600), cwd)
        return cls(commands)

    def run(self, agent: Agent, task: Task, materials: list[dict]) -> Result:
        if agent.id not in self.commands:
            # Configuration should be checked before dispatch; an unknown result
            # still prevents the runtime from replaying a potentially changed job.
            return Result("unknown", {"error": "worker_not_configured", "agent_id": agent.id})
        worker = self.commands[agent.id]
        request = {"protocol_version": 1, "agent": as_json(agent), "task": as_json(task), "materials": materials}
        try:
            process = subprocess.run(worker.argv, input=json.dumps(request), text=True,
                                     encoding="utf-8", capture_output=True, timeout=worker.timeout_seconds,
                                     cwd=worker.cwd, check=False, shell=False)
        except subprocess.TimeoutExpired:
            return Result("unknown", {"error": "worker_timeout", "timeout_seconds": worker.timeout_seconds})
        except OSError as exc:
            return Result("unknown", {"error": "worker_launch_failed", "exception": type(exc).__name__})
        if process.returncode:
            return Result("unknown", {"error": "worker_exit", "returncode": process.returncode})
        try:
            response = json.loads(process.stdout)
        except (json.JSONDecodeError, UnicodeError):
            return Result("unknown", {"error": "invalid_worker_json"})
        if (not isinstance(response, dict) or response.get("status") not in
                {"completed", "retryable_failure", "unknown"} or not isinstance(response.get("content"), dict)):
            return Result("unknown", {"error": "invalid_worker_response"})
        return Result(response["status"], response["content"])
