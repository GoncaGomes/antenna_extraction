# Antenna Ingestion v1 Baseline

This benchmark records the baseline behavior of the v1 ingestion pipeline so
later pipeline changes can be compared against the same local papers and runs.

PDFs are not copied into or committed with this benchmark. Each entry records
the source filename and `input_sha256`; use that checksum to verify that the
local PDF is the exact document used by the recorded run.

The captured outputs describe pipeline behavior at the time of freezing. They
are not scientifically reviewed gold annotations and must not be treated as
ground truth.

Create a local benchmark manifest with:

```powershell
uv run python scripts/freeze_benchmark.py runs/run_001 runs/run_002 --output benchmarks/v1/benchmark_manifest.json
```
