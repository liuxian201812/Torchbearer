# Literature contribution cards

A contribution card records what a paper established, the evidence behind it
and the relation to a current research question. Researchers use the cards when
selecting a direction, interpreting an important result or assessing a
manuscript's contribution. The comparison makes the scientific addition to a
precedent explicit and keeps its attribution attached to the source.

## Four parts

| Part | Information to retain | Research use |
|---|---|---|
| Source and evidence | Paper identity, version, reading scope and precise passages, equations or figures used | Recover the evidence supporting the comparison |
| Problem and context | Scientific question, relevant model and the obstacle addressed | Compare works that answer the same question under compatible conditions |
| Contribution and value | What the paper establishes, its evidence and the assumptions that control its significance | Identify the achieved advance and preserve its attribution |
| Relation to the project | What the current work adds, which content it inherits and the evidence still needed | Calibrate the next research decision and explain the new contribution |

Read the relevant full text before making a technical comparison. Separate
established results from conjectures or proposed future uses. Compare the
actual model, assumptions and observables. Distinguish changes in parameter
range from new mechanisms or inferences.

## Identity and reuse

Use one stable card identity for a paper, resolved through its DOI, arXiv identity
or another verified source. Retain the version and reading scope for each
analysis. When another research line uses the same paper, append its comparison
to the existing card and keep the source of that assessment. Topic links provide
several routes to the same record.

The card describes an external paper. Internal claims retain their own identity,
evidence and verification history in the [Scientific Memory Graph](scientific-memory.md).
A comparison may link the two, while keeping the earlier contribution and the
project's added result explicit. The researcher uses the comparison to choose
subsequent work; the auditor can inspect it when evaluating the scientific reason
for continuing, changing approach or concluding.

## Public example and MCP access

The `toy:reference` record in [the synthetic corpus](../examples/corpus.json)
illustrates all four parts under `contribution_analysis` with an arithmetic
identity and synthetic source evidence.

The existing MCP `read_record` tool returns the complete source-card record,
including these fields. Search uses the record's title and concise text. A
deployment can retain longer analyses as linked material while keeping the same
identity and source references. Access follows the host's allowlist, as described
in [MCP setup](../mcp/README.md).

Research agents populate these fields through their configured backend.
