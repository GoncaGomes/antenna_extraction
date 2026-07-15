"""Solver-independent canonical antenna architecture contracts."""

from antenna_ingest.canonicalization.canonicalize import (
    canonicalize_run,
    run_validated_canonicalization,
)
from antenna_ingest.canonicalization.schemas import (
    CanonicalDesignRecord,
    CanonicalFact,
)

__all__ = [
    "CanonicalDesignRecord",
    "CanonicalFact",
    "canonicalize_run",
    "run_validated_canonicalization",
]
