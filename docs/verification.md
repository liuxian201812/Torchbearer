# Independent derivation and comparison

Verifiers are peers of researchers and direction auditors under one coordinator.
They support ongoing research by checking important questions and mature claims
selected for scientific memory. The coordinator assigns a verifier whose
declared model parameter identity differs from that of the researcher.
Separate contexts and model parameters support an independent account. The
coordinator returns the comparison's corrections, additional conditions and
new questions to the researcher, who continues the investigation.

## Scientific starting conditions

The brief contains the model, definitions, assumptions, complete problem or
proposition, and admissible initial evidence. It can include the proposition
being tested. The originating proof, intermediate lemmas, code, self-checks,
research dialogue and originating assessment remain outside this scope.

The host applies the same scope to source links and every knowledge service
available to the verifier.

## Two stages, one verifier

1. **Independent derivation.** The verifier constructs its own argument, performs
   relevant checks and records resolved and unresolved parts. The account is
   retained as an immutable artifact with a content hash.
2. **Comparison.** After the account is frozen, the coordinator releases the
   originating argument to the same verifier. The comparison identifies
   agreement, discrepancies, additional assumptions, corrections and the scope
   actually checked.

The independent account is retained alongside the comparison. A verifier that
has already seen the originating argument performs a direct or nonblinded
review, recorded under that identity. Contributions made while jointly building
an argument are also recorded separately from independent verification.

## Reference implementation

`Coordinator.begin_verification` checks role and model identities, brief
membership and prior access to the original artifact. Each case binds its
derivation and comparison tasks to their respective stages. While the case is
`deriving`, material routing and task dispatch enforce its allowlist. `freeze`
retains the assigned task's completed account; `comparison_task` releases the
original and assigns the comparison in one transaction. `close_comparison`
accepts that assigned comparison after it completes.

To associate the check with a scientific claim, pass the intended claim as
`target_claim` when opening the case:

```python
coordinator.begin_verification(
    case_id, researcher_id, verifier_id, brief_ids, original_id,
    target_claim=claim,
)
```

The target fixes the claim's identity, revision, statement, assumptions, evidence
IDs and prerequisite revisions. `record_claim` matches those fields before
creating a `verified_by` relation. The claim may name the independent account
that this case will produce as `<case_id>:independent-account`. Cases used only
to exercise the protocol can omit `target_claim`; recording a scientific
verification association requires it. Agent checks and human assessments retain
their separate records.

The deployment adapter supplies a stable `parameter_id`, including the model
revision or checkpoint where available. Aliases, prompt changes and random seeds
retain that deployment's parameter identity.

## Source

Kim, E. M., Garg, A., Peng, K. & Garg, N. *Correlated Errors in Large Language Models*. Proceedings of ICML
2025, PMLR 267, 30038–30066. https://proceedings.mlr.press/v267/kim25e.html

The framework uses model diversity as a selection rule; error correlations must
be measured for any empirical claim about improved verification accuracy.

## Human scientific review

Human researchers assess the final argument and its physical interpretation
using the independent comparison, then record an exact-version assessment and
disclosure decision through the host gateway. See
[human-review.md](human-review.md).
