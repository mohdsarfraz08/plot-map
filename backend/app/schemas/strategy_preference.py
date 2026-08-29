"""
Declarative Strategy Preference & Scoring Catalog Schema for Stage 3B.5-2.

Defines Pydantic schemas for ranking criteria, weights, normalization rules,
thresholds, selection status thresholds, and deterministic tie-breaking.

STRICT NON-GEOMETRIC BOUNDARY:
MUST NOT contain Shapely objects, X/Y coordinates, bounding box tuples, polygon vertices,
or renderer/solver engine instances.
"""

import math
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.architectural_analysis import _is_serializable_value
from app.schemas.strategy_ranking import _verify_no_geometric_keys


class NormalizationConfig(BaseModel):
    """Configuration for raw criterion score normalization."""

    method: str = Field(default="min_max", description="Normalization method name.")
    min_value: float | None = Field(default=0.0, description="Minimum expected raw score value.")
    max_value: float | None = Field(default=1.0, description="Maximum expected raw score value.")
    invert: bool = Field(default=False, description="If True, lower raw values produce higher scores.")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Custom normalization parameters.")

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, v: Any) -> Any:
        if not _is_serializable_value(v):
            raise ValueError("Normalization parameters must be JSON-serializable")
        if not _verify_no_geometric_keys(v):
            raise ValueError("Normalization parameters must not contain prohibited geometric/CAD/mesh/solver keys")
        return v

    @model_validator(mode="after")
    def validate_range(self) -> "NormalizationConfig":
        if not self.method or not self.method.strip():
            raise ValueError("Normalization method cannot be an empty string")
        if self.min_value is not None and self.max_value is not None:
            if self.min_value > self.max_value:
                raise ValueError(
                    f"min_value ({self.min_value}) cannot be greater than max_value ({self.max_value})"
                )
        return self


class ThresholdConfig(BaseModel):
    """Threshold rules for a ranking criterion."""

    min_passing_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum score required to pass.")
    preferred_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Preferred score threshold for high ranking."
    )
    parameters: dict[str, Any] = Field(default_factory=dict, description="Custom threshold parameters.")

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, v: Any) -> Any:
        if not _is_serializable_value(v):
            raise ValueError("Threshold parameters must be JSON-serializable")
        if not _verify_no_geometric_keys(v):
            raise ValueError("Threshold parameters must not contain prohibited geometric/CAD/mesh/solver keys")
        return v

    @model_validator(mode="after")
    def validate_thresholds(self) -> "ThresholdConfig":
        if self.preferred_threshold is not None and self.min_passing_score > self.preferred_threshold:
            raise ValueError(
                f"min_passing_score ({self.min_passing_score}) cannot be greater than "
                f"preferred_threshold ({self.preferred_threshold})"
            )
        return self


class PreferenceCriterion(BaseModel):
    """Single declarative preference/scoring criterion model."""

    id: str = Field(..., description="Unique criterion identifier.")
    description: str = Field(..., description="Human-readable description of criterion.")
    weight: float = Field(..., ge=0.0, le=1.0, description="Criterion weight in range [0.0, 1.0].")
    normalization: NormalizationConfig = Field(
        default_factory=NormalizationConfig, description="Normalization rule configuration."
    )
    thresholds: ThresholdConfig | None = Field(default=None, description="Optional threshold configuration.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata.")

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: Any) -> Any:
        if not _is_serializable_value(v):
            raise ValueError("Criterion metadata must be JSON-serializable")
        if not _verify_no_geometric_keys(v):
            raise ValueError("Criterion metadata must not contain prohibited geometric/CAD/mesh/solver keys")
        return v

    @model_validator(mode="after")
    def validate_criterion(self) -> "PreferenceCriterion":
        if not self.id or not self.id.strip():
            raise ValueError("Criterion id cannot be an empty string")
        if not self.description or not self.description.strip():
            raise ValueError("Criterion description cannot be an empty string")
        return self


class TieBreakConfig(BaseModel):
    """Deterministic tie-breaking priority configuration."""

    priority_criteria: list[str] = Field(
        default_factory=list, description="Ordered list of criterion IDs for tie breaking."
    )
    fallback_strategy: str = Field(
        default="candidate_id", description="Fallback sorting key attribute (e.g. candidate_id)."
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Tie-break metadata.")

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: Any) -> Any:
        if not _is_serializable_value(v):
            raise ValueError("TieBreak metadata must be JSON-serializable")
        if not _verify_no_geometric_keys(v):
            raise ValueError("TieBreak metadata must not contain prohibited geometric/CAD/mesh/solver keys")
        return v

    @model_validator(mode="after")
    def validate_tie_break(self) -> "TieBreakConfig":
        if not self.fallback_strategy or not self.fallback_strategy.strip():
            raise ValueError("fallback_strategy cannot be an empty string")
        for item in self.priority_criteria:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("priority_criteria must contain non-empty string criterion IDs")
        return self


class SelectionThresholdConfig(BaseModel):
    """Threshold configuration for mapping overall scores to SelectionStatus."""

    selected_min_score: float = Field(default=0.8, ge=0.0, le=1.0, description="Score threshold for SELECTED status.")
    viable_min_score: float = Field(default=0.6, ge=0.0, le=1.0, description="Score threshold for VIABLE status.")
    marginal_min_score: float = Field(default=0.4, ge=0.0, le=1.0, description="Score threshold for MARGINAL status.")
    rejected_max_score: float = Field(default=0.4, ge=0.0, le=1.0, description="Max score threshold for REJECTED status.")

    @model_validator(mode="after")
    def validate_selection_threshold_ordering(self) -> "SelectionThresholdConfig":
        if not (
            self.selected_min_score >= self.viable_min_score >= self.marginal_min_score >= self.rejected_max_score
        ):
            raise ValueError(
                "Selection thresholds must follow ordering: "
                "selected_min_score >= viable_min_score >= marginal_min_score >= rejected_max_score"
            )
        return self


class PreferenceCatalog(BaseModel):
    """Root declarative preference catalog schema contract."""

    version: str = Field(..., description="Version of the preference catalog.")
    criteria: list[PreferenceCriterion] = Field(..., description="List of ranking criteria.")
    deterministic_precision: int = Field(
        default=6, ge=1, le=12, description="Rounding precision digits for deterministic score comparison."
    )
    tie_break: TieBreakConfig = Field(default_factory=TieBreakConfig, description="Tie-break priority rules.")
    selection_thresholds: SelectionThresholdConfig = Field(
        default_factory=SelectionThresholdConfig, description="Selection status threshold configuration."
    )
    provenance: dict[str, Any] = Field(default_factory=dict, description="Catalog provenance metadata.")

    @field_validator("provenance")
    @classmethod
    def validate_provenance(cls, v: Any) -> Any:
        if not _is_serializable_value(v):
            raise ValueError("Catalog provenance must be JSON-serializable")
        if not _verify_no_geometric_keys(v):
            raise ValueError("Catalog provenance must not contain prohibited geometric/CAD/mesh/solver keys")
        return v

    @model_validator(mode="after")
    def validate_preference_catalog(self) -> "PreferenceCatalog":
        if not self.version or not self.version.strip():
            raise ValueError("PreferenceCatalog version cannot be an empty string")
        if not self.criteria:
            raise ValueError("PreferenceCatalog must contain at least one PreferenceCriterion")

        criterion_ids = [c.id for c in self.criteria]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("Criterion IDs must be unique within PreferenceCatalog")

        total_weight = sum(c.weight for c in self.criteria)
        if not math.isclose(total_weight, 1.0, abs_tol=1e-5):
            raise ValueError(
                f"Total criterion weight must equal 1.0, got {total_weight:.6f}"
            )

        known_ids = set(criterion_ids)
        for tb_id in self.tie_break.priority_criteria:
            if tb_id not in known_ids:
                raise ValueError(
                    f"Tie-break criterion ID '{tb_id}' does not exist in catalog criteria"
                )

        return self
