from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.design_problem import (
    Constraint,
    Objective,
    Preference,
    Requirement,
    RequirementSource,
)


class DecisionStatus(str, Enum):
    FIXED = "fixed"
    FLEXIBLE = "flexible"
    PARTIALLY_FIXED = "partially_fixed"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"
    DERIVED = "derived"
    UNRESOLVED = "unresolved"


class ConflictStatus(str, Enum):
    DETECTED = "detected"
    RESOLVABLE_BY_PRIORITY = "resolvable_by_priority"
    REQUIRES_CLARIFICATION = "requires_clarification"
    ACCEPTED_TRADEOFF = "accepted_tradeoff"
    RESOLVED = "resolved"


class UncertaintyMateriality(str, Enum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MATERIAL = "material"
    BLOCKING = "blocking"


class AnalysisSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKING = "blocking"


class RelationshipImpact(str, Enum):
    IMPROVES = "improves"
    REDUCES = "reduces"
    CONSTRAINS = "constrains"
    DEPENDS_ON = "depends_on"


class DecisionDimension(str, Enum):
    SITE_RESPONSE = "site_response"
    PROGRAM_DEFINITION = "program_definition"
    SPACE_QUANTITY = "space_quantity"
    SPACE_OWNERSHIP = "space_ownership"
    FLOOR_ALLOCATION = "floor_allocation"
    UNIT_ORGANIZATION = "unit_organization"
    CIRCULATION = "circulation"
    VERTICAL_CIRCULATION = "vertical_circulation"
    ENTRANCE_STRATEGY = "entrance_strategy"
    SHARED_PRIVATE_STRATEGY = "shared_private_strategy"
    SERVICE_CORE_STRATEGY = "service_core_strategy"
    ORIENTATION = "orientation"
    ZONING = "zoning"
    ACCESSIBILITY = "accessibility"
    PRIVACY = "privacy"
    ENVIRONMENTAL_RESPONSE = "environmental_response"
    STRUCTURAL_STRATEGY = "structural_strategy"
    REGULATORY_STRATEGY = "regulatory_strategy"
    COST_STRATEGY = "cost_strategy"


def _is_serializable_value(val: Any) -> bool:
    """Helper to verify if a value consists of JSON-serializable primitives and dicts/lists."""
    if val is None or isinstance(val, (str, int, float, bool)):
        return True
    if isinstance(val, (list, tuple)):
        return all(_is_serializable_value(item) for item in val)
    if isinstance(val, dict):
        return all(isinstance(k, str) and _is_serializable_value(v) for k, v in val.items())
    return False


class DecisionRecord(BaseModel):
    id: str
    dimension: DecisionDimension | str
    subject: str
    value: Any = None
    alternatives: list[Any] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    status: DecisionStatus
    rationale: str | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("DecisionRecord id cannot be empty")
        return v

    @field_validator("value", "alternatives")
    @classmethod
    def validate_serializable(cls, v: Any) -> Any:
        if not _is_serializable_value(v):
            raise ValueError("DecisionRecord value and alternatives must be JSON-serializable types")
        return v


class IncompatibilityRule(BaseModel):
    id: str
    dimension_a: DecisionDimension | str
    value_a: Any
    dimension_b: DecisionDimension | str
    value_b: Any
    explanation: str
    source_ids: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("IncompatibilityRule id cannot be empty")
        return v

    @field_validator("value_a", "value_b")
    @classmethod
    def validate_serializable(cls, v: Any) -> Any:
        if not _is_serializable_value(v):
            raise ValueError("IncompatibilityRule values must be JSON-serializable types")
        return v


class DimensionRelationship(BaseModel):
    id: str
    source_dimension: DecisionDimension | str
    source_value: Any
    target: str
    impact: RelationshipImpact
    explanation: str
    severity: AnalysisSeverity = AnalysisSeverity.INFO
    source_ids: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("DimensionRelationship id cannot be empty")
        return v

    @field_validator("source_value")
    @classmethod
    def validate_serializable(cls, v: Any) -> Any:
        if not _is_serializable_value(v):
            raise ValueError("DimensionRelationship source_value must be JSON-serializable types")
        return v


class ConflictRecord(BaseModel):
    id: str
    source_ids: list[str] = Field(default_factory=list)
    type: str
    severity: AnalysisSeverity
    status: ConflictStatus
    explanation: str
    affected_dimensions: list[DecisionDimension | str] = Field(default_factory=list)
    resolution_options: list[str] = Field(default_factory=list)
    clarification_question: str | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ConflictRecord id cannot be empty")
        return v


class UncertaintyRecord(BaseModel):
    id: str
    topic: str
    description: str
    materiality: UncertaintyMateriality
    affected_dimensions: list[DecisionDimension | str] = Field(default_factory=list)
    required_for_strategy: bool = False
    clarification_question: str | None = None
    source: RequirementSource = RequirementSource.SYSTEM

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("UncertaintyRecord id cannot be empty")
        return v


class DependencyRecord(BaseModel):
    id: str
    source_dimension: DecisionDimension | str
    affected_dimensions: list[DecisionDimension | str] = Field(default_factory=list)
    relationship: str
    explanation: str

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("DependencyRecord id cannot be empty")
        return v


class FeasibilityConcern(BaseModel):
    id: str
    dimension: DecisionDimension | str
    description: str
    severity: AnalysisSeverity
    source_ids: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("FeasibilityConcern id cannot be empty")
        return v


class OrganizationAction(str, Enum):
    GROUP_BY_ATTRIBUTE = "group_by_attribute"
    ASSIGN_FLOOR_TIER = "assign_floor_tier"
    CREATE_CIRCULATION_NODE = "create_circulation_node"
    CREATE_SERVICE_STACK = "create_service_stack"


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


class OrganizationRule(BaseModel):
    id: str
    trigger_dimension: DecisionDimension | str
    trigger_value: Any
    action: OrganizationAction
    target_collection: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    explanation: str
    source_ids: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("OrganizationRule id cannot be empty")
        return v

    @field_validator("trigger_dimension", "target_collection", "explanation")
    @classmethod
    def validate_non_empty_str(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("OrganizationRule string fields cannot be empty")
        return v

    @field_validator("trigger_value", "parameters")
    @classmethod
    def validate_serializable_and_non_geometric(cls, v: Any) -> Any:
        if not _is_serializable_value(v):
            raise ValueError("OrganizationRule trigger_value and parameters must be JSON-serializable types")
        if not _verify_no_geometric_keys(v):
            raise ValueError("OrganizationRule strictly forbids geometric/CAD/mesh/solver attributes")
        return v


class ArchitecturalAnalysis(BaseModel):
    problem_id: str
    problem_version: int = Field(..., ge=1)
    summary: str
    fixed_decisions: list[DecisionRecord] = Field(default_factory=list)
    flexible_decisions: list[DecisionRecord] = Field(default_factory=list)
    hard_constraints: list[Constraint | Requirement] = Field(default_factory=list)
    soft_preferences: list[Preference | Requirement] = Field(default_factory=list)
    objectives: list[Objective] = Field(default_factory=list)
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    uncertainties: list[UncertaintyRecord] = Field(default_factory=list)
    decision_dimensions: list[DecisionDimension | str] = Field(default_factory=list)
    dependencies: list[DependencyRecord] = Field(default_factory=list)
    feasibility_concerns: list[FeasibilityConcern] = Field(default_factory=list)
    incompatibilities: list[IncompatibilityRule] = Field(default_factory=list)
    relationships: list[DimensionRelationship] = Field(default_factory=list)
    organization_rules: list[OrganizationRule] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_collection_ids(self) -> "ArchitecturalAnalysis":
        collections = (
            self.fixed_decisions,
            self.flexible_decisions,
            self.conflicts,
            self.uncertainties,
            self.dependencies,
            self.feasibility_concerns,
            self.incompatibilities,
            self.relationships,
            self.organization_rules,
        )
        for collection in collections:
            ids = [item.id for item in collection]
            if len(ids) != len(set(ids)):
                raise ValueError("IDs must be unique within each ArchitecturalAnalysis collection")
        return self