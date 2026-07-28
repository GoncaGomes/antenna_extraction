# Testing Strategy

Pipeline v2 testing separates deterministic correctness, endpoint capability,
scientific review, and future solver integration.

## Local automated tests

Unit and integration tests remain independent of remote model endpoints. As v2
is implemented, they should cover:

- ordered page rendering and page-reference integrity;
- strict parsing of model contracts using fake responses;
- deterministic evidence collection, deduplication, ordering, and inclusion
  reasons;
- lossless composition of extraction and geometry compilation;
- identifier, reference, expression, unit, dependency, and evidence checks;
- preview generation from the same ACIR stored in the final output;
- sequential orchestration with `parallelism=1`;
- the normal call budget of one NuExtract3 call and one Gemma4 call.

The existing local command is:

```text
uv run pytest -q
```

## Validation meanings

Tests and reports must keep three statuses separate:

- `structural_status`: `valid | invalid`;
- `reconstruction_status`:
  `complete | requires_confirmed_completions | incomplete`;
- `scientific_review_status`: `not_reviewed | passed | failed`.

Structural tests establish only schema, graph, reference, and coverage
invariants. Passing them does not prove scientific, geometric,
electromagnetic, fabrication, or simulation correctness.

Tests must also verify that `proposed_completions` remain separate from
source-grounded construction and are never applied without confirmation.

## Remote capability checks

Remote endpoint checks are opt-in. They may verify image-count, payload,
context, structured-output, and timeout limits. Sequential batching is added
only after such a check demonstrates a real limit, and batching tests must
prove that source order is preserved without semantic page selection.

## Development benchmark

The five current reference papers form a development benchmark. They are used
to review exact values, design and variant preservation, topology, evidence,
results, unresolved information, ACIR previews, and final statuses. Success on
five papers is not evidence of generalization to the antenna literature.

Scientific review records human assessment separately from structural results.

## Future CST vertical slice

The complete CST agent is outside pipeline v2 documentation and implementation.
A future integration test should begin with an already known ACIR:

```text
known ACIR -> minimal adapter -> Hermes/CST -> constructed geometry
```

This vertical slice tests whether the solver-neutral contract is consumable. It
must not add CST-specific commands to the ACIR or use CST execution as proof
that extraction from a paper was scientifically correct.

