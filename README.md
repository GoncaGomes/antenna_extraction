# Antenna Extraction

This repository extracts evidence-grounded antenna information from scientific
PDF papers and is being rebuilt around a small, sequential, VLM-first pipeline.

## Current implementation status

The current branch contains the cleaned minimal foundation, strict Pydantic
contracts and generated JSON Schemas, the evidence-grounded v2 acceptance
suite, and the direct full-document NuExtract3 extraction command.

The legacy Markdown, evidence parsing, retrieval, candidate extraction, and
canonicalization paths have been removed. The results publisher,
architecture-author call, global output-integrity layer, and end-to-end runner
are not implemented yet.

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

## Full-document extraction

After creating a run and rendering all pages, explicitly choose one thinking
mode for the single full-paper extraction call:

```powershell
uv run antenna-ingest extract-paper runs/<run_id> --thinking
uv run antenna-ingest extract-paper runs/<run_id> --no-thinking
```

Use `--force` only to replace a previous extraction attempt. The command sends
every rendered page once in source order, persists request metadata and the raw
response, validates the result against the `PaperExtraction` contract, and
writes the extraction and validation reports. It does not retry, batch pages,
publish final results, or generate architecture.

See [the implementation plan](docs/implementation_plan.md) for the planned
contracts, commit boundaries, acceptance gates, and deferred work.
