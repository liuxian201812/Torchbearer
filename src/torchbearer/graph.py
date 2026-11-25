"""Typed Scientific Memory Graph with immutable revision-specific evidence."""

from collections import deque
import json
from urllib.parse import quote
from .contracts import verification_target
from .store import Store, canonical, digest


def node_id(kind: str, identity: str, revision: int | None = None) -> str:
    result = kind + '/' + quote(identity, safe='')
    return result if revision is None else result + '/' + str(revision)


def claim_at(store: Store, identity: str, revision: int | None = None) -> dict:
    if revision is None:
        row = store.db.execute('SELECT body FROM claims WHERE id=? ORDER BY revision DESC LIMIT 1', (identity,)).fetchone()
    else:
        row = store.db.execute('SELECT body FROM claims WHERE id=? AND revision=?', (identity, revision)).fetchone()
    if row is None:
        raise KeyError((identity, revision))
    return json.loads(row['body'])


def resolve_dependencies(store: Store, dependencies: list) -> list[dict]:
    """Pin scientific prerequisites using the same rule for claims and checks."""
    resolved = []
    for dependency in dependencies:
        if isinstance(dependency, str):
            prior = claim_at(store, dependency)
        elif isinstance(dependency, dict) and set(dependency) == {"id", "revision"} and type(dependency["revision"]) is int:
            prior = claim_at(store, dependency['id'], dependency['revision'])
        else:
            raise ValueError("Dependencies identify a claim or an exact claim revision")
        ref = {'id': prior['id'], 'revision': prior['revision']}
        if ref in resolved:
            raise ValueError("Duplicate scientific dependency")
        resolved.append(ref)
    return resolved


def put_node(store: Store, identity: str, kind: str, data: dict):
    payload = canonical(data)
    prior = store.db.execute('SELECT kind,body FROM graph_nodes WHERE id=?', (identity,)).fetchone()
    if prior and tuple(prior) != (kind, payload):
        raise ValueError('Graph node identities are immutable')
    store.db.execute('INSERT OR IGNORE INTO graph_nodes VALUES(?,?,?)', (identity, kind, payload))


def put_edge(store: Store, source: str, relation: str, target: str):
    store.db.execute('INSERT OR IGNORE INTO graph_edges VALUES(?,?,?)', (source, relation, target))


def index_claim(store: Store, claim: dict):
    """Index one retained revision inside the caller's transaction."""
    cid, revision = claim['id'], claim['revision']
    stable = node_id('claim', cid)
    current = node_id('claim_revision', cid, revision)
    put_node(store, stable, 'claim', {'claim_id': cid})
    put_node(store, current, 'claim_revision', {'claim': claim, 'sha256': digest(claim)})
    put_edge(store, current, 'revision_of', stable)
    if revision > 1:
        put_edge(store, current, 'supersedes', node_id('claim_revision', cid, revision - 1))
    for topic in claim['topic_ids']:
        tid = node_id('topic', topic)
        put_node(store, tid, 'topic', {'topic_id': topic})
        put_edge(store, current, 'in_topic', tid)
    for aid in claim['evidence_ids']:
        index_artifact(store, aid)
        put_edge(store, current, 'supported_by', node_id('evidence', aid))
    for dependency in claim.get('resolved_dependencies', []):
        put_edge(store, current, 'depends_on', node_id('claim_revision', dependency['id'], dependency['revision']))
    if claim.get('depends_on') and 'resolved_dependencies' not in claim:
        # Legacy records did not pin prerequisite revisions. Preserve that fact.
        for dep in claim['depends_on']:
            identity = dep if isinstance(dep, str) else dep['id']
            put_node(store, node_id('claim', identity), 'claim', {'claim_id': identity})
            put_edge(store, current, 'unversioned_dependency', node_id('claim', identity))
    case_id = claim['verification'].get('agent')
    if case_id:
        row = store.db.execute('SELECT * FROM cases WHERE id=?', (case_id,)).fetchone()
        if row and row['state'] == 'complete' and row['target_claim'] == canonical(verification_target(claim)):
            vid = node_id('verification', case_id)
            put_node(store, vid, 'verification', {
                'case_id': case_id, 'researcher': row['researcher'], 'verifier': row['verifier'],
                'frozen_hash': row['frozen_hash'], 'comparison': json.loads(row['comparison']),
            })
            put_edge(store, current, 'verified_by', vid)
            for relation, aid in [('original_argument', row['original']), ('independent_account', row['frozen_artifact'])]:
                index_artifact(store, aid)
                put_edge(store, vid, relation, node_id('evidence', aid))


def index_artifact(store: Store, artifact_id: str):
    artifact = store.get_artifact(artifact_id)
    put_node(store, node_id('evidence', artifact_id), 'evidence', {
        'artifact_id': artifact_id, 'sha256': artifact['sha256'], 'origin': artifact['origin'],
    })


class ScientificMemoryGraph:
    """Host-side graph API; worker access requires an explicit node allowlist."""

    def __init__(self, store: Store):
        self.store = store
        marker = store.db.execute("SELECT value FROM controls WHERE key='memory_graph_schema'").fetchone()
        if marker is None:
            with store.transaction():
                for row in store.db.execute('SELECT body FROM claims ORDER BY rowid').fetchall():
                    index_claim(store, json.loads(row['body']))
                store.db.execute("INSERT INTO controls VALUES('memory_graph_schema','1')")

    def snapshot(self, *, allowed_node_ids: set[str] | None = None) -> dict:
        nodes = [dict(id=r['id'], type=r['kind'], data=json.loads(r['body']))
                 for r in self.store.db.execute('SELECT * FROM graph_nodes ORDER BY id')
                 if allowed_node_ids is None or r['id'] in allowed_node_ids]
        visible = {n['id'] for n in nodes}
        edges = [dict(source=r['source'], relation=r['relation'], target=r['target'])
                 for r in self.store.db.execute('SELECT * FROM graph_edges ORDER BY source,relation,target')
                 if r['source'] in visible and r['target'] in visible]
        return {'schema_version': 1, 'nodes': nodes, 'edges': edges}

    def traverse(self, seed: str, *, direction: str = 'out', relations: set[str] | None = None,
                 max_depth: int = 4, max_nodes: int = 1000,
                 allowed_node_ids: set[str] | None = None) -> dict:
        if direction not in {'out', 'in', 'both'} or type(max_depth) is not int or not 0 <= max_depth <= 100:
            raise ValueError('Use out, in or both traversal with depth from 0 to 100')
        if type(max_nodes) is not int or not 1 <= max_nodes <= 10000:
            raise ValueError('Use a node limit from 1 to 10000')
        if allowed_node_ids is not None and seed not in allowed_node_ids:
            raise PermissionError('Seed is outside the assigned graph scope')
        graph = self.snapshot(allowed_node_ids=allowed_node_ids)
        known = {n['id'] for n in graph['nodes']}
        if seed not in known:
            raise KeyError(seed)
        adjacency = {n: [] for n in known}
        for edge in graph['edges']:
            if relations is not None and edge['relation'] not in relations:
                continue
            if direction in {'out', 'both'}:
                adjacency[edge['source']].append(edge['target'])
            if direction in {'in', 'both'}:
                adjacency[edge['target']].append(edge['source'])
        found, queue, truncated = {seed}, deque([(seed, 0)]), False
        while queue:
            current, depth = queue.popleft()
            for target in sorted(adjacency[current]):
                if target in found:
                    continue
                if depth == max_depth or len(found) == max_nodes:
                    truncated = True
                    continue
                found.add(target)
                queue.append((target, depth + 1))
        return {'schema_version': 1, 'nodes': [n for n in graph['nodes'] if n['id'] in found],
                'edges': [e for e in graph['edges'] if e['source'] in found and e['target'] in found
                          and (relations is None or e['relation'] in relations)], 'truncated': truncated}

    def evidence_trace(self, claim_id: str, revision: int | None = None, **limits) -> dict:
        claim = claim_at(self.store, claim_id, revision)
        return self.traverse(node_id('claim_revision', claim_id, claim['revision']),
            relations={'depends_on', 'supported_by', 'verified_by', 'original_argument',
                       'independent_account', 'reviewed_by'}, **limits)

    def affected_by(self, claim_id: str, revision: int, **limits) -> dict:
        claim_at(self.store, claim_id, revision)
        return self.traverse(node_id('claim_revision', claim_id, revision),
                             direction='in', relations={'depends_on'}, **limits)

    def shared_claims(self, topic_a: str, topic_b: str) -> list[dict]:
        """Return latest revisions indexed in both topics, without duplicate copies."""
        result = []
        rows = self.store.db.execute('''SELECT n.body FROM graph_nodes n
            JOIN graph_edges a ON a.source=n.id AND a.relation='in_topic'
            JOIN graph_edges b ON b.source=n.id AND b.relation='in_topic'
            WHERE n.kind='claim_revision' AND a.target=? AND b.target=?''',
            (node_id('topic', topic_a), node_id('topic', topic_b)))
        for row in rows:
            claim = json.loads(row['body'])['claim']
            if claim_at(self.store, claim['id'])['revision'] == claim['revision']:
                result.append({'id': claim['id'], 'revision': claim['revision'], 'statement': claim['statement']})
        return sorted(result, key=lambda item: item['id'])
