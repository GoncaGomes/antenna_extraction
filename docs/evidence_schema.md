# Evidence Contracts

Pipeline v2 keeps evidence in its main data contracts. This document describes
conceptual responsibilities; executable Pydantic models and generated JSON
Schema will become authoritative when the schemas are implemented.

## Document extraction evidence

`document_extraction.json` is the source-oriented record produced by
NuExtract3. Evidence may represent text, a table, figure, caption, equation, or
other visible paper content. Each evidence record needs a stable identifier,
one-based page reference, source type, source-faithful content, and any required
visual reference.

Observations reference evidence IDs rather than duplicating evidence text.
Exact reported values, symbols, and units remain available alongside any
normalised representation. Simulated, measured, and analytical observations
remain distinct. Variants, conflicts, ambiguity, and unresolved information
must not be discarded.

## Deterministic evidence packet

The evidence packet is built after structural validation of
`document_extraction.json`. Python may resolve existing references, collect
pages, deduplicate them, restore source order, and record inclusion reasons. It
must not infer antenna meaning or perform semantic page selection.

Page sources include:

- `geometry_relevant_pages`;
- pages referenced by NuExtract3 design records and candidates;
- pages referenced by geometry, material, parameter, feed, excitation, and
  result observations;
- pages required to preserve conflicts, derivations, and unresolved
  information;
- pages reached through explicit evidence references.

`geometry_relevant_pages` is therefore one source, not an exclusive filter.
Every included page records the reference or extraction field that caused its
inclusion.

## Evidence in the ACIR

Source-grounded ACIR elements and reproducible derivations link back to
evidence IDs. Composition preserves these links without deciding whether the
scientific interpretation is correct.

Unsupported engineering assumptions are not evidence. They belong only to
`proposed_completions`, where they remain unconfirmed and separate from
paper-grounded construction.

Structural and coverage checks can establish that references exist and required
evidence links are present. They cannot establish scientific, geometric, or
electromagnetic correctness.
