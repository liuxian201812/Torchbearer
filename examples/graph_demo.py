"""Show Scientific Memory Graph relations with synthetic arithmetic claims."""

import argparse
import json
from torchbearer.graph import ScientificMemoryGraph
from torchbearer.memory import record_claim
from torchbearer.release import release_status
from torchbearer.store import Store


def populate(store):
    store.put_artifact('synthetic-calculation', {'argument': 'Known arithmetic identities for a protocol example.'}, visibility='restricted')
    for identity, topics, dependencies in [
        ('shared-lemma', ['topic-a', 'topic-b'], []),
        ('derived-result', ['topic-b'], ['shared-lemma']),
        ('downstream-result', ['topic-c'], ['derived-result']),
    ]:
        if not store.db.execute('SELECT 1 FROM claims WHERE id=?', (identity,)).fetchone():
            record_claim(store, {'id': identity, 'revision': 1,
                'statement': 'Synthetic arithmetic record: ' + identity,
                'assumptions': ['Toy fixture inputs'], 'outcome': 'supported',
                'evidence_ids': ['synthetic-calculation'], 'topic_ids': topics,
                'depends_on': dependencies, 'verification': {'agent': None, 'human': None},
                'example_type': 'synthetic_protocol_example'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', default='.torchbearer/graph-demo.sqlite')
    args = parser.parse_args()
    store = Store(args.state)
    try:
        populate(store)
        graph = ScientificMemoryGraph(store)
        print(json.dumps({'example_type': 'synthetic_protocol_example',
            'shared_claims': graph.shared_claims('topic-a', 'topic-b'),
            'evidence_trace': graph.evidence_trace('downstream-result', max_depth=6),
            'affected_by_lemma': graph.affected_by('shared-lemma', 1),
            'release_status': release_status(store, ['downstream-result'])}, indent=2))
    finally:
        store.close()


if __name__ == '__main__':
    main()
