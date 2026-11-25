"""Protocol checks on synthetic statements, not research-quality benchmarks."""

import json
import sqlite3
import tempfile
from pathlib import Path
import unittest
from torchbearer.contracts import Agent, ModelIdentity
from torchbearer.coordinator import Coordinator
from torchbearer.graph import ScientificMemoryGraph, claim_at, node_id
from torchbearer.memory import record_claim
from torchbearer.release import HumanReviewGateway, export_reviewed_claims, release_status
from torchbearer.store import Store, canonical, digest


class MemoryGraphTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.directory.name) / 'state.sqlite')
        self.store.put_artifact('calculation', {'argument': 'Synthetic exact calculation'}, visibility='restricted')
        self.store.put_artifact('failure', {'argument': 'Synthetic failed approximation'}, visibility='restricted')
        record_claim(self.store, self.claim('base', topics=['topic-a', 'topic-b']))
        record_claim(self.store, self.claim('derived', dependencies=['base']))
        record_claim(self.store, self.claim('downstream', dependencies=['derived']))
        self.graph = ScientificMemoryGraph(self.store)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def claim(self, identity, revision=1, *, topics=None, dependencies=None, evidence='calculation'):
        return {'id': identity, 'revision': revision, 'statement': 'Synthetic statement ' + identity,
                'assumptions': ['Specified synthetic inputs'], 'outcome': 'supported',
                'evidence_ids': [evidence], 'topic_ids': topics or ['topic-a'],
                'depends_on': dependencies or [], 'verification': {'agent': None, 'human': None}}

    def gateway(self, kind='human', identity='physicist'):
        def authenticate(credential):
            if credential != 'synthetic-authenticated-session':
                raise PermissionError('Invalid fixture credential')
            return {'id': identity, 'kind': kind, 'authentication_reference': 'synthetic-session-receipt'}
        return HumanReviewGateway(self.store, authenticate, {identity})

    def review(self, identity, *, decision='approve', release=True, suffix='1'):
        claim = claim_at(self.store, identity)
        return {'id': identity + '-review-' + suffix, 'claim_id': identity, 'revision': claim['revision'],
                'claim_sha256': digest(claim), 'decision': decision,
                'correctness_assessment': 'Synthetic fixture assessment of the exact stored statement.',
                'physical_interpretation': 'Synthetic fixture interpretation; no scientific discovery is asserted.',
                'release_authorized': release}

    def approve(self, identity, **options):
        review = self.review(identity, **options)
        self.gateway().submit(review, credential='synthetic-authenticated-session')
        return review

    def test_typed_graph_preserves_shared_identity_and_exact_dependencies(self):
        graph = self.graph.snapshot()
        base = node_id('claim_revision', 'base', 1)
        memberships = [e for e in graph['edges'] if e['source'] == base and e['relation'] == 'in_topic']
        self.assertEqual(len(memberships), 2)
        self.assertEqual(len([n for n in graph['nodes'] if n['id'] == base]), 1)
        self.assertEqual(self.graph.shared_claims('topic-a', 'topic-b')[0]['id'], 'base')
        self.assertEqual(claim_at(self.store, 'derived')['resolved_dependencies'], [{'id': 'base', 'revision': 1}])

    def test_trace_retains_old_prerequisite_after_revision(self):
        record_claim(self.store, self.claim('base', 2, evidence='failure'))
        trace = self.graph.evidence_trace('downstream', max_depth=6)
        ids = {n['id'] for n in trace['nodes']}
        self.assertIn(node_id('claim_revision', 'base', 1), ids)
        self.assertNotIn(node_id('claim_revision', 'base', 2), ids)
        self.assertIn(node_id('evidence', 'calculation'), ids)
        self.assertNotIn(node_id('evidence', 'failure'), ids)

    def test_reverse_dependency_query_finds_affected_results(self):
        impact = self.graph.affected_by('base', 1)
        self.assertEqual({n['data']['claim']['id'] for n in impact['nodes']}, {'base', 'derived', 'downstream'})
        bounded = self.graph.affected_by('base', 1, max_depth=1)
        self.assertTrue(bounded['truncated'])
        self.assertEqual(len(bounded['nodes']), 2)

    def test_scope_applies_to_nodes_and_edges_during_traversal(self):
        seed = node_id('claim_revision', 'downstream', 1)
        trace = self.graph.traverse(seed, max_depth=10, allowed_node_ids={seed})
        self.assertEqual(len(trace['nodes']), 1)
        self.assertEqual(trace['edges'], [])
        with self.assertRaises(PermissionError):
            self.graph.traverse(seed, allowed_node_ids=set())

    def test_agent_or_inline_human_claim_does_not_authorize_release(self):
        claim = self.claim('spoof')
        claim['verification']['human'] = {'approved': True}
        with self.assertRaises(ValueError):
            record_claim(self.store, claim)
        with self.assertRaises(PermissionError):
            self.gateway(kind='agent').submit(self.review('base'), credential='synthetic-authenticated-session')
        Coordinator(self.store).register(Agent('physicist', 'researcher', ModelIdentity('synthetic', 'a', 'weights-a')))
        with self.assertRaises(PermissionError):
            self.gateway().submit(self.review('base'), credential='synthetic-authenticated-session')
        self.assertFalse(release_status(self.store, ['base'])['eligible'])

    def test_human_identity_exact_digest_and_interpretation_are_required(self):
        with self.assertRaises(PermissionError):
            self.gateway().submit(self.review('base'), credential='unauthenticated')
        for key, value in [('claim_sha256', 'wrong-digest'), ('physical_interpretation', ''), ('revision', True)]:
            report = self.review('base'); report[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.gateway().submit(report, credential='synthetic-authenticated-session')

    def test_release_requires_human_review_of_dependency_closure(self):
        self.approve('downstream')
        self.assertFalse(release_status(self.store, ['downstream'])['eligible'])
        self.approve('base'); self.approve('derived')
        packet = export_reviewed_claims(self.store, ['downstream'])
        self.assertEqual({c['id'] for c in packet['claims']}, {'base', 'derived', 'downstream'})
        self.assertEqual(len(packet['human_review_ids']), 3)
        self.assertEqual(len(packet['sha256']), 64)

    def test_new_revision_requires_fresh_review(self):
        self.approve('base')
        record_claim(self.store, self.claim('base', 2))
        self.assertFalse(release_status(self.store, ['base'])['eligible'])
        with self.assertRaises(PermissionError):
            export_reviewed_claims(self.store, ['base'])
        self.approve('base', suffix='2')
        self.assertTrue(release_status(self.store, ['base'])['eligible'])

    def test_changed_prerequisite_cannot_be_silently_reused(self):
        for identity in ['base', 'derived', 'downstream']:
            self.approve(identity)
        record_claim(self.store, self.claim('base', 2))
        status = release_status(self.store, ['downstream'])
        self.assertIn('prerequisite_revision_changed', {x['reason'] for x in status['issues']})
        self.approve('base', suffix='2')
        self.assertFalse(release_status(self.store, ['downstream'])['eligible'])
        record_claim(self.store, self.claim('derived', 2, dependencies=['base']))
        record_claim(self.store, self.claim('downstream', 2, dependencies=['derived']))
        self.approve('derived', suffix='2'); self.approve('downstream', suffix='2')
        self.assertTrue(release_status(self.store, ['downstream'])['eligible'])

    def test_human_rejection_and_disclosure_withholding_block_release(self):
        self.approve('base', release=False)
        self.assertFalse(release_status(self.store, ['base'])['eligible'])
        self.approve('base', suffix='2')
        self.assertTrue(release_status(self.store, ['base'])['eligible'])
        self.approve('base', decision='revise', release=False, suffix='3')
        self.assertFalse(release_status(self.store, ['base'])['eligible'])
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM human_reviews').fetchone()[0], 3)

    def test_review_nodes_are_immutable_and_survive_reopening(self):
        review = self.approve('base')
        with self.assertRaises(sqlite3.IntegrityError):
            self.gateway().submit(review, credential='synthetic-authenticated-session')
        path = self.store.path
        self.store.close(); self.store = Store(path)
        graph = ScientificMemoryGraph(self.store).snapshot()
        self.assertIn(node_id('human_review', review['id']), {n['id'] for n in graph['nodes']})
        self.assertTrue(release_status(self.store, ['base'])['eligible'])

    def test_missing_dependency_cannot_create_a_dangling_claim(self):
        with self.assertRaises(KeyError):
            record_claim(self.store, self.claim('broken', dependencies=['not-present']))
        with self.assertRaises(KeyError):
            claim_at(self.store, 'broken')

    def test_legacy_unversioned_dependencies_are_preserved_without_inventing_versions(self):
        old = self.claim('legacy', dependencies=['base'])
        self.store.db.execute('INSERT INTO claims VALUES(?,?,?)', ('legacy', 1, canonical(old)))
        self.store.db.execute("DELETE FROM controls WHERE key='memory_graph_schema'")
        graph = ScientificMemoryGraph(self.store).snapshot()
        self.assertTrue(any(e['relation'] == 'unversioned_dependency' for e in graph['edges']))
        self.approve('legacy')
        status = release_status(self.store, ['legacy'])
        self.assertIn('unversioned_legacy_dependency', {x['reason'] for x in status['issues']})


if __name__ == '__main__':
    unittest.main()
