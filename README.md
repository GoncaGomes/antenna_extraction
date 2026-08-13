# Antenna Extraction

This repository extracts evidence-grounded antenna information from scientific
PDF papers and is being rebuilt around a small, sequential, VLM-first pipeline.

## Current implementation status

The current branch contains the cleaned minimal foundation plus strict Pydantic
contracts and generated JSON Schemas for `paper_extraction`, `antenna_results`,
and the solver-neutral `antenna_architecture` block representation.

The legacy Markdown, evidence parsing, retrieval, candidate extraction, and
canonicalization paths have been removed. No extraction model call, results
publisher, architecture-author call, global output-integrity layer, or
end-to-end runner is implemented yet.

## Planned NewPipeline

```text
Scientific PDF
  -> run creation and ordered page rendering
  -> NuExtract3 full-document extraction
  -> validated paper_extraction.json
       -> deterministic antenna_results.json publication
       -> architecture-author input preparation
  -> one selected architecture author
  -> antenna_architecture.json
  -> objective structural validation
```

`paper_extraction.json` is an internal, auditable artifact. The only final
consumer-facing outputs are:

```text
outputs/antenna_results.json
outputs/antenna_architecture.json
```

Normal execution is synchronous and sequential, with a model-call budget of
two: one NuExtract3 extraction call and one call to a benchmark-selected
architecture author. Publishing `antenna_results.json` is deterministic and
does not require a model call.

The initial normal path has no RAG, retrieval, parallelism, fallback model,
automatic retry, repair call, or agent tool loop.

## Implementation status and next step

The Commit 3 extraction/results contracts and Commit 4 architecture contract
are implemented. Their Pydantic models and generated JSON Schemas are the
executable contract source of truth. The next planned work is Commit 5, which
defines the evidence-grounded v2 acceptance suite without adding model calls.

See [the implementation plan](docs/implementation_plan.md) for the planned
contracts, commit boundaries, acceptance gates, and deferred work.
