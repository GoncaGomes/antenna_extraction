# Model Assignment

Pipeline v2 has two model roles in its normal single-paper path. Calls are
synchronous, ordered, and executed with `parallelism=1`.

## Document extractor: NuExtract3

NuExtract3 receives all rendered PDF pages in source order in one multimodal
request. It produces `document_extraction.json`, which describes what the paper
contains and reports.

The extraction must preserve:

- candidate and reported designs and variants;
- exact values, symbols, units, and source-faithful text;
- materials, geometry observations, feeds, and excitations;
- simulated, measured, analytical, and other reported results as distinct
  observations;
- evidence references and page references;
- reproducible derivations, conflicts, ambiguity, and missing information;
- `geometry_relevant_pages` as an extraction result.

NuExtract3 does not select CST operations, invent missing dimensions, or
produce the final ACIR.

## Geometry compiler: Gemma4

Gemma4 receives:

- the structurally valid `document_extraction.json`;
- the deterministic evidence packet;
- the referenced rendered pages in source order.

The evidence packet is not limited to `geometry_relevant_pages`. It also
contains pages reached through NuExtract3 evidence and observation references,
with an inclusion reason for each page.

In one call, Gemma4 selects the relevant design and compiles a solver-neutral,
block-oriented ACIR. It must preserve variants, results, conflicts, and
unresolved information rather than treating compilation as a replacement for
document extraction.

Source-supported blocks, relationships, values, and reproducible derivations
belong to the source-grounded construction. Unsupported engineering hypotheses
belong only to `proposed_completions`, require confirmation, and are never
automatically applied.

Gemma4 must not emit CST commands.

## Oversized documents

The default is exactly one call per model. Sequential batching may be introduced
only when a verified endpoint or context limit prevents the normal request.
Batch boundaries are transport-driven, preserve source order, and never use
deterministic semantic page selection.

No fallback model, repair call, agent tool loop, RAG, embeddings, vector store,
or parallel model execution is part of the normal path.

## Example names

The example configuration assigns:

```yaml
models:
  document_extractor: nuextract3
  geometry_compiler: gemma4:26b
```

The example is documentation only and does not define runtime configuration
behavior.

