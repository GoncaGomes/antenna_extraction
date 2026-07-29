# Antenna Extraction

This repository extracts evidence-grounded antenna information from scientific
PDF papers and is being rebuilt around a small, sequential, VLM-first pipeline.

## Current implementation status

The current branch contains the cleaned minimal foundation: run creation,
source fingerprinting, ordered page rendering, atomic JSON persistence, failure
records, and generic OpenAI-compatible endpoint configuration.

The legacy Markdown, evidence parsing, retrieval, candidate extraction, and
canonicalization paths have been removed. The planned two-output NewPipeline
is not implemented yet.

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

The cleanup foundation is complete. The next planned work is Commit 3, which
defines the extraction and results contracts without implementing model calls.

See [the implementation plan](docs/implementation_plan.md) for the planned
contracts, commit boundaries, acceptance gates, and deferred work.
