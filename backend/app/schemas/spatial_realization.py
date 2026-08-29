"""
Spatial Realization Schema Contract for Stage 3B.4D-1.

Defines non-geometric, serializable Pydantic contracts at the boundary between
abstract DesignCandidate topology and downstream 2D spatial layout realization engines.

STRICT NON-GEOMETRIC BOUNDARY:
MUST NOT contain Shapely objects, X/Y coordinates, bounding box tuples, polygon vertices,
or renderer/solver engine instances.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class RealizationStatus(str, Enum):
    SUCCESS = "success"
    INVALID_CANDIDATE = "invalid_candidate"
    UNSUPPORTED_SPEC = "unsupported_spec"
    SPATIALLY_INFEASIBLE = "spatially_infeasible"
    SOLVER_TIMEOUT = "solver_timeout"
    SOLVER_ERROR = "solver_error"


class SpatialRoomSpec(BaseModel):
    """
    Specification for a single space/room to be placed by the 2D spatial layout solver.
    Non-geometric: specifies target areas and aspect constraints without X/Y coordinates.
    """

    id: str = Field(..., description="Unique room identifier within the layout plan.")
    name: str = Field(..., description="Human-readable room name.")
    room_type: str = Field(..., description="Categorical room type (e.g., living, bedroom, bathroom).")
    target_area: float = Field(..., gt=0.0, description="Target area in square feet/meters.")
    aspect_ratio_range: tuple[float, float] = Field(
        (0.5, 2.0), description="Allowed aspect ratio range (min_aspect, max_aspect)."
    )
    floor_assignment: int = Field(1, ge=1, description="1-indexed floor tier assignment.")
    unit_id: str | None = Field(None, description="Optional unit container ID.")
    min_width: float | None = Field(None, gt=0.0, description="Optional minimum width constraint.")
    min_depth: float | None = Field(None, gt=0.0, description="Optional minimum depth constraint.")

    @model_validator(mode="after")
    def validate_room_spec(self) -> "SpatialRoomSpec":
        if not self.id or not self.id.strip():
            raise ValueError("SpatialRoomSpec id must be a non-empty string")
        if self.aspect_ratio_range[0] <= 0 or self.aspect_ratio_range[1] <= 0:
            raise ValueError("Aspect ratio bounds must be positive numbers")
        if self.aspect_ratio_range[0] > self.aspect_ratio_range[1]:
            raise ValueError("Aspect ratio min bound cannot exceed max bound")
        return self


class SpatialAdjacencySpec(BaseModel):
    """
    Specification for an abstract topological adjacency/proximity relationship between two spaces.
    """

    source_space_id: str = Field(..., description="ID of source space.")
    target_space_id: str = Field(..., description="ID of target space.")
    strength: str = Field("hard", description="Adjacency strength ('hard' or 'soft').")
    weight: float = Field(1.0, ge=0.0, description="Relative priority weight for soft adjacencies.")

    @model_validator(mode="after")
    def validate_adjacency(self) -> "SpatialAdjacencySpec":
        if not self.source_space_id or not self.source_space_id.strip():
            raise ValueError("source_space_id must be a non-empty string")
        if not self.target_space_id or not self.target_space_id.strip():
            raise ValueError("target_space_id must be a non-empty string")
        if self.source_space_id == self.target_space_id:
            raise ValueError("Self-referential spatial adjacencies are prohibited")
        return self


class SpatialCoreSpec(BaseModel):
    """
    Specification for a vertical circulation stairwell or service core stack.
    """

    id: str = Field(..., description="Unique core identifier.")
    core_type: str = Field(..., description="Type of core (e.g. vertical_stairwell, plumbing_wet_core).")
    access_type: str = Field("shared", description="Access mode (e.g. shared, independent, hybrid).")
    floors: list[int] = Field(default_factory=list, description="Floors served by this core.")
    connected_space_ids: list[str] = Field(
        default_factory=list, description="Space or unit container IDs connected to this core."
    )

    @model_validator(mode="after")
    def validate_core(self) -> "SpatialCoreSpec":
        if not self.id or not self.id.strip():
            raise ValueError("SpatialCoreSpec id must be a non-empty string")
        return self


class SpatialLayoutPlan(BaseModel):
    """
    Intermediate, non-geometric spatial realization plan contract.
    Bridges abstract DesignCandidate topologies and downstream 2D layout optimization solvers.
    """

    id: str = Field(..., description="Unique layout plan identifier.")
    source_candidate_id: str = Field(..., description="Originating DesignCandidate ID.")
    source_strategy_id: str = Field(..., description="Originating DesignStrategy ID.")
    source_problem_id: str = Field(..., description="Originating DesignProblem ID.")
    source_problem_version: int = Field(..., ge=1, description="Originating DesignProblem version.")
    plot_width: float = Field(..., gt=0.0, description="Plot width dimension.")
    plot_depth: float = Field(..., gt=0.0, description="Plot depth dimension.")
    setbacks: dict[str, float] = Field(default_factory=dict, description="Site boundary setback distances.")
    floors: int = Field(1, ge=1, description="Total building floor count.")
    rooms: list[SpatialRoomSpec] = Field(default_factory=list, description="Spaces to be packed.")
    adjacencies: list[SpatialAdjacencySpec] = Field(default_factory=list, description="Spatial adjacencies.")
    cores: list[SpatialCoreSpec] = Field(default_factory=list, description="Circulation and service cores.")
    realization_parameters: dict[str, Any] = Field(
        default_factory=dict, description="Generic realization metadata & flexible parameters."
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict, description="Complete strategic lineage and generator metadata."
    )

    @model_validator(mode="after")
    def validate_layout_plan(self) -> "SpatialLayoutPlan":
        if not self.id or not self.id.strip():
            raise ValueError("SpatialLayoutPlan id must be a non-empty string")
        if not self.source_candidate_id or not self.source_candidate_id.strip():
            raise ValueError("source_candidate_id must be a non-empty string")

        room_ids = [r.id for r in self.rooms]
        if len(room_ids) != len(set(room_ids)):
            raise ValueError("Room IDs must be unique within a SpatialLayoutPlan")

        core_ids = [c.id for c in self.cores]
        if len(core_ids) != len(set(core_ids)):
            raise ValueError("Core IDs must be unique within a SpatialLayoutPlan")

        return self


class RealizationResult(BaseModel):
    """
    Result contract capturing 2D spatial realization output or structured infeasibility status.
    """

    status: RealizationStatus = Field(..., description="Categorical realization execution status.")
    success: bool = Field(..., description="True if a valid 2D layout was successfully solved.")
    candidate_id: str = Field(..., description="Originating DesignCandidate ID.")
    layout_plan: SpatialLayoutPlan | None = Field(None, description="Plan used for realization.")
    realized_geometry: dict[str, Any] | None = Field(
        None, description="Downstream 2D geometric payload output (if successful)."
    )
    error_message: str | None = Field(None, description="Human-readable error explanation if realization failed.")
    infeasible_constraints: list[str] = Field(
        default_factory=list, description="List of conflicting constraint IDs causing infeasibility."
    )
    provenance: dict[str, Any] = Field(default_factory=dict, description="Execution metadata.")

    @model_validator(mode="after")
    def validate_result(self) -> "RealizationResult":
        if not self.candidate_id or not self.candidate_id.strip():
            raise ValueError("candidate_id must be a non-empty string")
        return self
