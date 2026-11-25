# Human scientific review and release

Torchbearer combines autonomous investigation with human verification and
physical interpretation. Agents select questions and methods, derive, compute
and compare arguments within supplied direction constraints. Humans provide
those constraints, examine mathematical correctness and interpret physical
significance. Ideas or corrections can enter through the coordinator during
work. Final human assessment determines which results are ready for disclosure.

## Assessment record

`HumanReviewGateway.submit` accepts a review of one exact current claim revision.
The input contains its identity, revision and SHA-256, together with:

- `correctness_assessment`: what the human checked and the resulting judgement;
- `physical_interpretation`: the physical meaning, conditions and significance;
- `decision`: `approve`, `revise` or `reject`;
- `release_authorized`: an explicit disclosure decision.

The host supplies the authenticated human identity. An immutable review node
links the assessment to its exact revision in the Scientific Memory Graph and
retains a non-secret authentication receipt. Credentials stay outside the
review record.

## Trusted host boundary

The host constructs the gateway with an authentication callback and a set of
authorized human reviewer identities. The callback validates the credential
with the deployment's identity provider and returns `id`, `kind="human"` and
`authentication_reference`. A registered agent identity is rejected even if a
request labels it as human. A model-generated approval in a claim record or
worker result never creates a human assessment.

Keep the authentication callback, reviewer allowlist and writable state database
outside worker permissions. Expose human submission through the deployment's
authenticated human interface.

## Release decision

`release_status(store, claim_ids)` checks the selected latest revisions and all
of their pinned scientific prerequisites. Release requires a human approval
and disclosure authorization for each exact revision. The most recent decision
from each reviewer is used; an unresolved `revise` or `reject` decision blocks
release. Each new revision requires fresh approval.

If a prerequisite is revised, dependent arguments keep the old link so their
original basis remains inspectable. Release is held until the dependent record
is updated and reviewed with its current prerequisites. Older records that
never specified a prerequisite revision retain an `unversioned_dependency`
relation and require a new, pinned revision before release.

`export_reviewed_claims` returns a packet containing the selected claims, their
prerequisite closure and applicable human review identities, and records its
digest. Publication uses a separate distribution step.
Internal retrieval, failed-attempt retention and agent research remain available
while human review is pending.

```bash
torchbearer release-status --state project.sqlite --claim result-a
torchbearer export-reviewed --state project.sqlite --claim result-a
```

Tests use synthetic claims and authentication fixtures to exercise review and
release rules.
