# Claim-Layer Decision

Pipeline v2 does not introduce a separate claim schema. A duplicate claim layer
would repeat information already required by the main contracts and create
another place where evidence, values, and design associations could diverge.

Instead:

- `document_extraction.json` contains evidence, observations, designs,
  variants, derivations, conflicts, and unresolved information;
- the evidence packet resolves and packages references without semantic
  reinterpretation;
- the geometry compilation contains the selected design's source-grounded ACIR
  and evidence links;
- `antenna_design.json` composes those contracts without information loss.

## Source-grounded statements

An extracted observation records what the paper contains and cites evidence.
A reproducible derivation records its expression, inputs, result, and supporting
evidence. A source-grounded ACIR element links to the observations or evidence
that support it.

These records may remain ambiguous or conflicting. Composition must preserve
that state rather than manufacturing a single claim.

## Proposed completions

An unsupported engineering hypothesis is not a claim extracted from the paper.
It belongs only to `proposed_completions` and must:

- state that it is proposed rather than reported;
- explain the missing information it addresses;
- identify affected ACIR elements;
- retain its rationale;
- require explicit confirmation before use.

Proposed completions are never inserted automatically into source-grounded
construction. Confirming one is a downstream engineering decision and does not
retroactively make it a paper-grounded fact.

The eventual executable schemas and their generated JSON Schema are
authoritative. This document records ownership and scientific-integrity rules,
not a second hand-maintained schema.

