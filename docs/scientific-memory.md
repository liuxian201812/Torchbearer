# Scientific Memory Graph

Scientific Memory Graph connects scientific statements to the arguments,
calculations, independent checks and human assessments on which they depend.
The unit is an exact claim revision. A stable claim identity groups its successive
revisions; topics offer several ways to find the same record.

## Nodes and relations

| Node | Retained information |
|---|---|
| Claim | Stable scientific-statement identity |
| Claim revision | Statement, assumptions, outcome and exact prerequisite versions |
| Evidence | Immutable artifact identity, digest and origin |
| Verification | Independent-account digest, responsible agents and comparison |
| Topic | Research question or thematic view |
| Human review | Exact-version correctness assessment, physical interpretation and disclosure decision |

| Directed relation | Meaning |
|---|---|
| Revision → claim: `revision_of` | Identify the statement to which a revision belongs |
| New revision → older revision: `supersedes` | Retain the preceding statement and evidence |
| Revision → evidence: `supported_by` | Locate the basis of a scientific statement |
| Revision → prerequisite revision: `depends_on` | Record the exact scientific premise used |
| Revision → topic: `in_topic` | Make one record available through several topics |
| Revision → verification: `verified_by` | Attach the completed independent comparison |
| Verification → evidence | Distinguish `independent_account` from `original_argument` |
| Revision → human review: `reviewed_by` | Attach the final human scientific assessment |

Topic links support navigation; dependency links identify scientific premises.
Retained assumptions help an agent assess whether a relation applies to a new
problem.

[Literature contribution cards](contribution-cards.md) preserve the scientific
content and evidence of external papers, together with their relation to current
research. Cards remain source records with their own identities; internal claim
revisions record what the project derives from or adds to those sources.

## Write and revise

`record_claim` stores the claim and graph relations in one transaction. It
checks evidence artifacts, matches completed verification cases to their assigned
claim targets, resolves prerequisite identities to exact revisions, and appends
the next revision. Set `target_claim` when opening a case as described in
[independent verification](verification.md). A dependency may explicitly specify `{"id": "lemma", "revision": 2}`;
a bare identity is pinned to its current revision on insertion.

The `outcome` can represent a supported or conditional statement, a counterexample,
an informative failure, an unresolved question or a correction. A failed attempt
retains the conditions tested and the obstruction encountered. It remains
searchable alongside successful work. Each revision retains its dependency
links, preserving the basis of downstream arguments.

## Read the graph

`ScientificMemoryGraph` provides:

- `evidence_trace`: follow prerequisites, supporting evidence and checks from a
  specific statement, returning the actual records that support it;
- `affected_by`: follow dependencies in reverse to find arguments that may need
  reassessment after a prerequisite changes;
- `shared_claims`: find latest revisions indexed in two topics without storing
  separate copies;
- `traverse`: inspect typed relations within explicit depth and node bounds.

Traversal reports when bounds truncate its output. Typed node and edge tables
share the SQLite database with scientific records. Queries return provenance
for scientific assessment.

```bash
python examples/graph_demo.py --state .torchbearer/graph.sqlite
torchbearer graph --state .torchbearer/graph.sqlite
torchbearer trace --state .torchbearer/graph.sqlite --claim downstream-result
torchbearer impact --state .torchbearer/graph.sqlite --claim shared-lemma --revision 1
```

These commands are host/coordinator operations. Worker-facing graph access must
pass `allowed_node_ids` to `snapshot` or `traverse`; both nodes and edges are
filtered by that scope. The host must keep original arguments and linked
verification evidence outside a blinded verifier's node allowlist. The trusted
host owns human-review and graph state.

## Scientific release

Agent checks and human assessments are separate node types. Claims remain
available for internal investigation before human review. Public-result export
requires a human assessment of correctness, physical meaning and disclosure for
the exact claim revision and its prerequisite closure. See
[human-review.md](human-review.md). The formats are described in
`schemas/records.schema.json` and `schemas/memory-graph.schema.json`.
