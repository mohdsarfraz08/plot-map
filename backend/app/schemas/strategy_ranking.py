"""
Strategy Ranking & Selection Schema Contract for Stage 3B.5-1.

Defines deterministic, non-geometric Pydantic contracts for scoring, ranking,
ordering, and selecting architectural strategies and design candidates.

STRICT NON-GEOMETRIC BOUNDARY:
MUST NOT contain Shapely objects, X/Y coordinates, bounding box tuples, polygon vertices,
or renderer/solver engine instances.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.architectural_analysis import _is_serializable_value

_PROHIBITED_GEOMETRIC_KEYS = {
    "coordinates",
    "polygon",
    "polygons",
    "rectangle",
    "rectangles",
    "bounding_box",
    "x",
    "y",
    "z",
    "wall",
    "walls",
    "door",
    "doors",
    "window",
    "windows",
    "cad",
    "mesh",
    "tbm",
    "pulp",
    "cbc",
    "geometry",
}


def _verify_no_geometric_keys(val: Any) -> bool:
    """Helper to ensure no prohibited geometric keys exist in data structures."""
    if isinstance(val, dict):
        for k, v in val.items():
            if isinstance(k, str) and k.lower() in _PROHIBITED_GEOMETRIC_KEYS:
                return False
            if not _verify_no_geometric_keys(v):
                return False
    elif isinstance(val, (list, tuple)):
        for item in val:
            if not _verify_no_geometric_keys(item):
                return False
    return True


class SelectionStatus(str, Enum):
    SELECTED = "selected"
    VIABLE = "viable"
    MARGINAL = "marginal"
    REJECTED = "rejected"


class CriterionScore(BaseModel):
    """
    Representation of one deterministic evaluation criterion score.
    """

    criterion_id: str = Field(..., description="Unique criterion identifier.")
    score: float = Field(..., ge=0.0, le=1.0, description="Normalized score in range [0.0, 1.0].")
    weight: float = Field(..., ge=0.0, le=1.0, description="Criterion weight in range [0.0, 1.0].")
    weighted_score: float = Field(..., ge=0.0, description="Product of score and weight.")
    explanation: str = Field(..., description="Deterministic explanation of score evaluation.")
    source_ids: list[str] = Field(default_factory=list, description="Source requirement or dimension IDs.")

    @model_validator(mode="after")
    def validate_criterion_score(self) -> "CriterionScore":
        if not self.criterion_id or not self.criterion_id.strip():
            raise ValueError("criterion_id cannot be an empty string")
        if not self.explanation or not self.explanation.strip():
            raise ValueError("explanation cannot be an empty string")
        if not _is_serializable_value(self.source_ids):
            raise ValueError("source_ids must contain JSON-serializable strings")
        return self


class ScoreBreakdown(BaseModel):
    """
    Complete breakdown of weighted evaluation criteria and total score.
    """

    criteria: list[CriterionScore] = Field(default_factory=list, description="Collection of criterion scores.")
    total_score: float = Field(..., ge=0.0, le=1.0, description="Total normalized score in range [0.0, 1.0].")
    scoring_version: str = Field(..., description="Version of the scoring catalog or engine used.")

    @model_validator(mode="after")
    def validate_score_breakdown(self) -> "ScoreBreakdown":
        if not self.scoring_version or not self.scoring_version.strip():
            raise ValueError("scoring_version cannot be an empty string")

        criterion_ids = [c.criterion_id for c in self.criteria]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("Criterion IDs must be unique within a ScoreBreakdown")

        return self


class RankedCandidate(BaseModel):
    """
    Ranking and selection result for a single DesignCandidate.
    """

    candidate_id: str = Field(..., description="Target DesignCandidate ID.")
    strategy_id: str = Field(..., description="Originating DesignStrategy ID.")
    rank: int = Field(..., ge=1, description="1-indexed rank order (1 = highest rank).")
    score_breakdown: ScoreBreakdown = Field(..., description="Multi-criteria score breakdown.")
    selection_status: SelectionStatus = Field(..., description="Categorical selection status.")
    rejection_reasons: list[str] = Field(default_factory=list, description="List of reasons if rejected.")
    tie_break_key: list[Any] = Field(default_factory=list, description="Deterministic tie-breaking metadata.")
    provenance: dict[str, Any] = Field(default_factory=dict, description="Lineage metadata.")

    @field_validator("provenance", "tie_break_key")
    @classmethod
    def validate_serializable_and_non_geometric(cls, v: Any) -> Any:
        if not _is_serializable_value(v):
            raise ValueError("Must contain JSON-serializable primitives, lists, or dicts")
        if not _verify_no_geometric_keys(v):
            raise ValueError("Must not contain prohibited geometric/CAD/mesh/solver keys")
        return v

    @model_validator(mode="after")
    def validate_ranked_candidate(self) -> "RankedCandidate":
        if not self.candidate_id or not self.candidate_id.strip():
            raise ValueError("candidate_id cannot be an empty string")
        if not self.strategy_id or not self.strategy_id.strip():
            raise ValueError("strategy_id cannot be an empty string")

        if self.selection_status == SelectionStatus.REJECTED and not self.rejection_reasons:
            raise ValueError("RankedCandidate with REJECTED status must contain non-empty rejection_reasons")

        return self


class RankingResult(BaseModel):
    """
    Complete result contract for a ranking and candidate selection operation.
    """

    id: str = Field(..., description="Unique ranking execution ID.")
    source_problem_id: str = Field(..., description="Originating DesignProblem ID.")
    source_problem_version: int = Field(..., ge=1, description="Originating DesignProblem version.")
    ranked_candidates: list[RankedCandidate] = Field(default_factory=list, description="Ordered candidate ranks.")
    selected_candidate_ids: list[str] = Field(default_factory=list, description="Selected candidate IDs.")
    ranking_version: str = Field(..., description="Version of ranking engine used.")
    provenance: dict[str, Any] = Field(default_factory=dict, description="Execution provenance metadata.")

    @field_validator("provenance")
    @classmethod
    def validate_serializable_and_non_geometric(cls, v: Any) -> Any:
        if not _is_serializable_value(v):
            raise ValueError("Provenance must contain JSON-serializable primitives, lists, or dicts")
        if not _verify_no_geometric_keys(v):
            raise ValueError("Provenance must not contain prohibited geometric/CAD/mesh/solver keys")
        return v

    @model_validator(mode="after")
    def validate_ranking_result(self) -> "RankingResult":
        if not self.id or not self.id.strip():
            raise ValueError("RankingResult id cannot be an empty string")
        if not self.source_problem_id or not self.source_problem_id.strip():
            raise ValueError("source_problem_id cannot be an empty string")
        if not self.ranking_version or not self.ranking_version.strip():
            raise ValueError("ranking_version cannot be an empty string")

        cand_ids = [c.candidate_id for c in self.ranked_candidates]
        if len(cand_ids) != len(set(cand_ids)):
            raise ValueError("Candidate IDs must be unique within ranked_candidates")

        if len(self.selected_candidate_ids) != len(set(self.selected_candidate_ids)):
            raise ValueError("selected_candidate_ids must contain unique IDs")

        ranked_cand_id_set = set(cand_ids)
        for sel_id in self.selected_candidate_ids:
            if sel_id not in ranked_cand_id_set:
                raise ValueError(f"Selected candidate_id '{sel_id}' must exist in ranked_candidates")

        return self
