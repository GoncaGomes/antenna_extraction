# Antenna Extraction

This repository extracts evidence-grounded antenna information from scientific
PDF papers and is being rebuilt around a small, sequential, VLM-first pipeline.

## Current implementation status

The current branch still contains the legacy implementation. Its active paths
include page-to-Markdown conversion, deterministic evidence and table parsing,
lexical retrieval, candidate extraction, tool-using canonicalization, and the
existing multi-phase orchestration.

Those modules describe current repository behavior, not the planned
NewPipeline. The planned two-output pipeline is not implemented yet.

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

The two-output pipeline is planned but not yet implemented. The next
implementation commit is a controlled cleanup of incompatible legacy code
while retaining the reusable run, rendering, persistence, client, and failure
handling foundation.

See [the implementation plan](docs/implementation_plan.md) for the planned
contracts, commit boundaries, acceptance gates, and deferred work.
