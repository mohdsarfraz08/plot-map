from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.architectural_analysis import DecisionRecord, _is_serializable_value
from app.schemas.design_strategy import FeasibilityExpectation, StrategyRisk

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
    """Helper to recursively ensure no geometric keys or prohibited objects exist in raw data structures."""
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


class AbstractCirculationNode(BaseModel):
    id: str
    type: str
    connected_space_ids: list[str] = Field(default_factory=list)
    access_type: str = "shared"

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("AbstractCirculationNode id cannot be empty")
        return v


class AbstractServiceStack(BaseModel):
    id: str
    service_type: str
    assigned_space_ids: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("AbstractServiceStack id cannot be empty")
        return v


class DesignCandidate(BaseModel):
    id: str
    source_strategy_id: str
    source_analysis_id: str
    source_problem_id: str
    source_problem_version: int = Field(..., ge=1)
    candidate_version: int = Field(1, ge=1)
    name: str
    selected_decisions: list[DecisionRecord] = Field(default_factory=list)
    floor_organization: dict[str, list[str]] = Field(default_factory=dict)
    unit_organization: dict[str, list[str]] = Field(default_factory=dict)
    circulation_intent: list[AbstractCirculationNode] = Field(default_factory=list)
    service_organization: list[AbstractServiceStack] = Field(default_factory=list)
    unresolved_decisions: list[DecisionRecord] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[StrategyRisk] = Field(default_factory=list)
    feasibility_expectation: FeasibilityExpectation = FeasibilityExpectation.NOT_EVALUATED
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "source_strategy_id", "source_analysis_id", "source_problem_id")
    @classmethod
    def validate_non_empty_ids(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Candidate and source IDs cannot be empty")
        return v

    @field_validator("floor_organization", "unit_organization", "provenance")
    @classmethod
    def validate_serializable_and_non_geometric(cls, v: Any) -> Any:
        if not _is_serializable_value(v):
            raise ValueError("Must contain JSON-serializable primitives and dicts/lists")
        if not _verify_no_geometric_keys(v):
            raise ValueError("Schema strictly forbids geometric/CAD/mesh/solver attributes")
        return v

    @model_validator(mode="after")
    def validate_candidate_collections(self) -> "DesignCandidate":
        collections = (
            ("selected_decisions", self.selected_decisions),
            ("circulation_intent", self.circulation_intent),
            ("service_organization", self.service_organization),
            ("unresolved_decisions", self.unresolved_decisions),
            ("risks", self.risks),
        )
        for name, collection in collections:
            ids = [item.id for item in collection]
            if len(ids) != len(set(ids)):
                raise ValueError(f"IDs must be unique within candidate collection '{name}'")
        return self
