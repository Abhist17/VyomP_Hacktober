"""Output records. `voucher_type` is validated against the 27 exact label strings."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from viveka.labels import LABEL_INDEX

SCHEMA_VERSION = "1"


class Alternative(BaseModel):
    voucher_type: str
    probability: float


class EvidenceItem(BaseModel):
    signal: str
    value: bool | str | float | None
    fields: list[str] = Field(default_factory=list)


class Prediction(BaseModel):
    schema_version: str = SCHEMA_VERSION
    row_id: int
    invoice_number: str | None = None
    voucher_type: str
    confidence: float
    prediction_set: list[str] = Field(default_factory=list)
    alternatives: list[Alternative] = Field(default_factory=list)
    needs_review: bool = False
    explanation: str = ""
    evidence: list[EvidenceItem] = Field(default_factory=list)
    decided_by: str = ""
    model_version: str = ""
    policy_version: str = ""

    @field_validator("voucher_type")
    @classmethod
    def _known_label(cls, value: str) -> str:
        if value not in LABEL_INDEX:
            raise ValueError(f"Unknown voucher type: {value!r}")
        return value

    def minimal(self) -> dict[str, str | None]:
        """The exact format of the problem statement's example."""
        return {"invoice_number": self.invoice_number, "voucher_type": self.voucher_type}
