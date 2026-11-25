"""Human scientific assessment and revision-specific public-result release."""

import json
from typing import Callable
from .graph import ScientificMemoryGraph, claim_at, node_id, put_edge, put_node
from .store import Store, canonical, digest, now


class HumanReviewGateway:
    """Host-only input boundary, backed by the deployment's human authentication.

    resolve_identity validates a credential outside model workers and returns
    an id, kind='human', and a non-secret authentication_reference. The host
    supplies an allowlist of reviewers. Neither callback nor state database
    belongs in worker tool scopes. This API does not implement an identity provider.
    """

    def __init__(self, store: Store, resolve_identity: Callable, authorized_reviewers: set[str]):
        if not callable(resolve_identity) or not authorized_reviewers:
            raise ValueError('Supply host authentication and authorized human reviewers')
        self.store, self.resolve_identity, self.authorized_reviewers = store, resolve_identity, authorized_reviewers

    def submit(self, review: dict, *, credential) -> str:
        principal = self.resolve_identity(credential)
        if not isinstance(principal, dict) or principal.get('kind') != 'human' or principal.get('id') not in self.authorized_reviewers:
            raise PermissionError('Human review requires an authenticated authorized human')
        if self.store.db.execute('SELECT 1 FROM agents WHERE id=?', (principal['id'],)).fetchone():
            raise PermissionError('An agent identity cannot act as a human reviewer')
        if not isinstance(principal.get('authentication_reference'), str) or not principal['authentication_reference'].strip():
            raise PermissionError('Retain a non-secret reference to the authenticated human session')
        required = {'id', 'claim_id', 'revision', 'claim_sha256', 'decision',
                    'correctness_assessment', 'physical_interpretation', 'release_authorized'}
        if not isinstance(review, dict) or set(review) != required:
            raise ValueError('Provide the exact revision, its digest, scientific assessment and disclosure decision')
        for key in required - {'revision', 'release_authorized'}:
            if not isinstance(review[key], str) or not review[key].strip():
                raise ValueError('Human review text fields must be nonempty')
        if type(review['revision']) is not int or review['revision'] < 1 or type(review['release_authorized']) is not bool:
            raise ValueError('Use an integer revision and a boolean release decision')
        if review['decision'] not in {'approve', 'revise', 'reject'}:
            raise ValueError('Use approve, revise or reject')
        if review['decision'] != 'approve' and review['release_authorized']:
            raise ValueError('Only an approving scientific assessment can authorize release')
        ScientificMemoryGraph(self.store)
        with self.store.transaction():
            claim = claim_at(self.store, review['claim_id'])
            if claim['revision'] != review['revision'] or digest(claim) != review['claim_sha256']:
                raise ValueError('The human assessment must identify the current exact claim revision')
            stored = {**review, 'reviewer_id': principal['id'],
                      'authentication_reference': principal['authentication_reference'], 'recorded_at': now()}
            self.store.db.execute('INSERT INTO human_reviews(id,claim_id,revision,reviewer_id,body) VALUES(?,?,?,?,?)',
                (stored['id'], stored['claim_id'], stored['revision'], stored['reviewer_id'], canonical(stored)))
            rid = node_id('human_review', stored['id'])
            put_node(self.store, rid, 'human_review', stored)
            put_edge(self.store, node_id('claim_revision', stored['claim_id'], stored['revision']), 'reviewed_by', rid)
            self.store.event('human.scientific_review', review_id=stored['id'], claim_id=stored['claim_id'],
                             revision=stored['revision'], reviewer_id=stored['reviewer_id'], decision=stored['decision'])
        return stored['id']


def _closure(store: Store, claim_ids: list[str]) -> list[dict]:
    if not claim_ids or any(not isinstance(x, str) for x in claim_ids):
        raise ValueError('Select at least one scientific claim')
    pending = [claim_at(store, identity) for identity in claim_ids]
    found = {}
    while pending:
        claim = pending.pop()
        key = (claim['id'], claim['revision'])
        if key in found:
            continue
        if len(found) >= 10000:
            raise ValueError('Scientific dependency closure exceeds the release bound')
        found[key] = claim
        for dep in claim.get('resolved_dependencies', []):
            pending.append(claim_at(store, dep['id'], dep['revision']))
    return [found[key] for key in sorted(found)]


def release_status(store: Store, claim_ids: list[str]) -> dict:
    """Check selected latest revisions and all of their pinned prerequisites."""
    issues, approved, claims = [], {}, _closure(store, claim_ids)
    for claim in claims:
        identity, revision = claim['id'], claim['revision']
        ref = {'id': identity, 'revision': revision}
        if claim_at(store, identity)['revision'] != revision:
            issues.append({**ref, 'reason': 'prerequisite_revision_changed'})
        if claim.get('depends_on') and 'resolved_dependencies' not in claim:
            issues.append({**ref, 'reason': 'unversioned_legacy_dependency'})
        latest_by_reviewer = {}
        for row in store.db.execute('SELECT body FROM human_reviews WHERE claim_id=? AND revision=? ORDER BY seq', (identity, revision)):
            report = json.loads(row['body'])
            latest_by_reviewer[report['reviewer_id']] = report
        reviews = list(latest_by_reviewer.values())
        if not reviews:
            issues.append({**ref, 'reason': 'human_review_required'})
        elif any(r['decision'] != 'approve' for r in reviews):
            issues.append({**ref, 'reason': 'human_revision_or_rejection_unresolved'})
        elif not any(r['release_authorized'] and r['claim_sha256'] == digest(claim) for r in reviews):
            issues.append({**ref, 'reason': 'human_release_authorization_required'})
        else:
            approved[(identity, revision)] = reviews
    return {'eligible': not issues, 'issues': issues,
            'claims': [{'id': c['id'], 'revision': c['revision']} for c in claims],
            'human_review_ids': sorted(r['id'] for reports in approved.values() for r in reports)}


def export_reviewed_claims(store: Store, claim_ids: list[str]) -> dict:
    """Build a release packet; internal graph access never requires publication approval."""
    with store.transaction():
        status = release_status(store, claim_ids)
        if not status['eligible']:
            raise PermissionError('Scientific-result release is blocked: ' + canonical(status['issues']))
        packet = {'schema_version': 1, 'purpose': 'human_reviewed_scientific_results',
                  'claims': _closure(store, claim_ids), 'human_review_ids': status['human_review_ids'],
                  'created_at': now()}
        packet['sha256'] = digest(packet)
        store.event('publication.packet', claim_ids=claim_ids, sha256=packet['sha256'],
                    human_review_ids=status['human_review_ids'])
        return packet
