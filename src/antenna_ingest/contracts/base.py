from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ContractModel(BaseModel):
    """Strict base for versioned JSON boundary contracts."""

    model_config = ConfigDict(extra="forbid", strict=True)
