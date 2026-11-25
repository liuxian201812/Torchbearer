"""Durable control state and immutable scientific artifacts."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS agents (id TEXT PRIMARY KEY, spec TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY, body TEXT NOT NULL, hash TEXT NOT NULL,
            visibility TEXT NOT NULL, origin TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS grants (
            artifact_id TEXT REFERENCES artifacts(id), agent_id TEXT REFERENCES agents(id),
            PRIMARY KEY(artifact_id, agent_id));
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, spec TEXT NOT NULL, state TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0, result TEXT, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cases (
            id TEXT PRIMARY KEY, researcher TEXT NOT NULL, verifier TEXT NOT NULL,
            brief TEXT NOT NULL, original TEXT NOT NULL, state TEXT NOT NULL,
            frozen_artifact TEXT, frozen_hash TEXT, comparison TEXT,
            derivation_task TEXT, comparison_task TEXT, target_claim TEXT);
        CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL,
            kind TEXT NOT NULL, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS controls (
            key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS claims (
            id TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL,
            PRIMARY KEY(id, revision));
        CREATE TABLE IF NOT EXISTS graph_nodes (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS graph_edges (
            source TEXT REFERENCES graph_nodes(id), relation TEXT NOT NULL,
            target TEXT REFERENCES graph_nodes(id), PRIMARY KEY(source,relation,target));
        CREATE INDEX IF NOT EXISTS graph_reverse ON graph_edges(target,relation);
        CREATE TABLE IF NOT EXISTS human_reviews (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
            claim_id TEXT NOT NULL, revision INTEGER NOT NULL,
            reviewer_id TEXT NOT NULL, body TEXT NOT NULL,
            FOREIGN KEY(claim_id,revision) REFERENCES claims(id,revision));
        """)
        case_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(cases)")}
        for column in ("derivation_task", "comparison_task", "target_claim"):
            if column not in case_columns:
                self.db.execute(f"ALTER TABLE cases ADD COLUMN {column} TEXT")

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def event(self, kind: str, **body):
        self.db.execute("INSERT INTO events(time,kind,body) VALUES(?,?,?)",
                        (now(), kind, canonical(body)))

    def put_artifact(self, artifact_id: str, body: dict, *, visibility: str,
                     origin: str | None = None):
        if visibility not in {"shared", "restricted"}:
            raise ValueError("Use shared or restricted artifact visibility")
        payload, sha = canonical(body), digest(body)
        previous = self.db.execute("SELECT hash,visibility,origin FROM artifacts WHERE id=?",
                                   (artifact_id,)).fetchone()
        if previous:
            if tuple(previous) != (sha, visibility, origin):
                raise ValueError("Artifact identities are immutable; create a new revision")
            return sha
        self.db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?)",
                        (artifact_id, payload, sha, visibility, origin, now()))
        return sha

    def grant(self, artifact_id: str, agent_id: str):
        self.db.execute("INSERT OR IGNORE INTO grants VALUES(?,?)", (artifact_id, agent_id))

    def get_artifact(self, artifact_id: str) -> dict:
        row = self.db.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        if row is None:
            raise KeyError(artifact_id)
        return {"id": row["id"], "content": json.loads(row["body"]),
                "sha256": row["hash"], "visibility": row["visibility"], "origin": row["origin"]}

    def authorized(self, artifact_id: str, agent_id: str) -> bool:
        row = self.db.execute("""SELECT 1 FROM artifacts a WHERE a.id=? AND
            (a.visibility='shared' OR EXISTS(SELECT 1 FROM grants g
             WHERE g.artifact_id=a.id AND g.agent_id=?))""", (artifact_id, agent_id)).fetchone()
        return row is not None

    def events(self) -> list[dict]:
        return [{"seq": r["seq"], "time": r["time"], "kind": r["kind"],
                 "body": json.loads(r["body"])} for r in self.db.execute("SELECT * FROM events ORDER BY seq")]

    def close(self):
        self.db.close()
