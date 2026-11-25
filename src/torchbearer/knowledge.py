"""Read-only knowledge access with a host-supplied record allowlist."""

import json
from pathlib import Path


class ReadOnlyKnowledge:
    def __init__(self, corpus_path: str | Path, allowed_ids: list[str]):
        corpus = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
        self.records = {r["id"]: r for r in corpus["records"]}
        if len(self.records) != len(corpus["records"]):
            raise ValueError("Corpus IDs must be unique")
        self.allowed = frozenset(allowed_ids)
        if self.allowed - self.records.keys():
            raise ValueError("The scope refers to unknown records")

    def search(self, query: str, limit: int = 10) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("Use an integer limit from 1 to 50")
        words = query.casefold().split()
        output = []
        for key in sorted(self.allowed):
            row = self.records[key]
            searchable = (row.get("title", "") + " " + row.get("text", "")).casefold()
            if all(word in searchable for word in words):
                output.append({"id": key, "title": row.get("title", ""), "kind": row["kind"]})
        return output[:limit]

    def read(self, record_id: str) -> dict:
        if record_id not in self.allowed:
            raise PermissionError("Record is outside this agent's supplied scope")
        return self.records[record_id].copy()
