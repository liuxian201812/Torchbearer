"""Synthetic worker illustrating the JSON process contract; no LLM is called."""

import json
import sys


request = json.load(sys.stdin)
if request.get("protocol_version") != 1:
    raise ValueError("Unsupported request protocol")
print(json.dumps({"status": "completed", "content": {
    "example_type": "synthetic_protocol_example",
    "task_id": request["task"]["id"],
    "agent_id": request["agent"]["id"],
    "received_artifact_ids": [item["id"] for item in request["materials"]],
    "statement": "The worker received the supplied synthetic brief."
}}))
