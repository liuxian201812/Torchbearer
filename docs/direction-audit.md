# Research direction review

Direction auditors are peers of researchers and verifiers under one coordinator.
They support research by examining **premature research closure** and
**search-path contraction**. The scorecard calculates observations from a
referenced trace; the auditor sends recommendations to the coordinator, which
routes feedback and supporting work to the researcher.

## Prepare the review window

Before a review, declare the scientific objective, candidate approaches and
method-family labels. Count substantive derivations, calculations and tests
that can change a scientific decision, excluding administrative calls and
repeated text. Use the same definition and equal numbers of steps in the current
and preceding windows. Record the window identity and preserve its trace.

Each candidate retains its method-family label throughout both windows. Record
in-scope pending actions, whether they are feasible with available resources,
their current status and the source supporting that assessment. A completed,
blocked or scientifically excluded action is not part of the actionable
frontier. A feasible action that has merely been deferred remains unfinished.

Evidence records identify scientific changes and point to the calculations,
arguments or measurements that establish them. The baseline lists all evidence
known before the current window. Count evidence IDs absent from that baseline
as new evidence. These annotations require scientific judgement; the scorecard
makes their consequences explicit and reproducible.

Researchers record the steps, candidate methods, feasibility assessments and
evidence links. The auditor checks their scientific meaning and can correct a
classification or assessment before interpreting the scorecard. The runtime
validates these records, calculates indicators and returns review cues.

## Indicators and review cues

For the current window, the implementation calculates:

- **Actionable frontier, F:** the number of feasible actions with status `ready`,
  `running` or `deferred`.
- **Effective method families, D_eff:** `exp(-sum(p_m * log(p_m)))`, where `p_m`
  is the proportion of substantive steps assigned to method family `m`. It is
  one for a single method and equals the family count when steps are distributed
  equally. The change is measured against the preceding window.
- **New evidence, G:** the number of distinct evidence IDs produced in the
  current window after removing every ID in the baseline.

A request to conclude with `F > 0` produces a `premature_research_closure` cue.
The auditor checks whether the remaining work is necessary for the declared
objective and feasible under the stated resource constraints.

A `search_path_contraction` cue requires all of the following:

1. At least two substantive steps have been recorded, and effective method
   diversity has fallen or all steps use one method family.
2. At least one actionable method family differs from the most-used family.
3. No new evidence was recorded in the current window (`G = 0`).
4. No scientific reason with supporting evidence justifies continued focus.

The policy can require a minimum drop in effective diversity; its default is any
positive drop, with a tolerance for floating-point rounding. An empty window
has undefined diversity, represented as `null`. The default policy compares
diversity only across equal-length windows; the single-family rule can still be
evaluated from the current window.

The trace can also link scope changes to their supporting evidence and limitations
to feasible follow-up actions. Missing links produce supplementary review cues.
Every cue identifies the action, evidence or assessment records for scientific
examination. The auditor assesses their significance.

## Worked example

In the supplied synthetic trace, the previous three steps use recurrence,
symbolic and geometric methods once each. Their proportions are
`p = (1/3, 1/3, 1/3)`, so `D_eff = 3`. The current three steps all use recurrence,
giving `D_eff = 1`. One feasible symbolic action remains (`F = 1`), no evidence
has been added (`G = 0`), and no supported reason for continued concentration
is recorded. The scorecard requests a search-path review. Because the trace
also requests termination, it separately flags premature closure.

Adding a new evidence record, or documenting a scientific reason supported by
existing evidence, removes the search-path cue. The auditor examines whether
that evidence warrants the decision and checks source identities so reused
evidence retains its original identity.

## Run and interpret the scorecard

```bash
torchbearer audit --trace examples/audit_trace.json --policy config/audit.example.json
```

The version-2 trace and policy are defined in `schemas/audit-trace.schema.json`
and `config/audit.example.json`. The runtime additionally checks cross-references,
fixed method families, duplicate IDs and baseline membership.

The auditor returns a recommendation with the scientific reason and supporting
record IDs. The coordinator incorporates it into subsequent tasks. Preserve the
window, policy and decision with the research record so later reviews can use
the same definitions.
