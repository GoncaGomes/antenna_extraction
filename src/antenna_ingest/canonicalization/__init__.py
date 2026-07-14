"""Solver-independent canonical antenna architecture contracts."""

from antenna_ingest.canonicalization.canonicalize import (
    run_validated_canonicalization,
)
from antenna_ingest.canonicalization.schemas import (
    CanonicalDesignRecord,
    CanonicalFact,
)

__all__ = [
    "CanonicalDesignRecord",
    "CanonicalFact",
    "run_validated_canonicalization",
]
