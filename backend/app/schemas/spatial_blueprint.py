"""
Spatial Blueprint Schema for the Generalized Agentic Layout Engine.
Defines normalized architectural spatial layouts that dynamically scale
to any arbitrary plot dimensions without hardcoding.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class FunctionalZone(str, Enum):
    FRONT_PUBLIC = "front_public"        # Foyer, Living Room, Front Verandah, Guest Powder Room
    MIDDLE_CORE = "middle_core"          # Staircase, Dining, Kitchen, Central Hallway/Circulation
    REAR_PRIVATE = "rear_private"        # Master Bedroom, Bedrooms, Attached Baths, Dressers
    SERVICE = "service"                  # Utility, Wash Area, Storage, OTS Lightwell


class BlueprintRoomType(str, Enum):
    ENTRANCE = "Entrance"
    FOYER = "Foyer"
    LIVING = "Living Room"
    DINING = "Dining Room"
    KITCHEN = "Kitchen"
    BEDROOM = "Bedroom"
    MASTER_BEDROOM = "Master Bedroom"
    BATHROOM = "Bathroom"
    ATTACHED_BATHROOM = "Attached Bathroom"
    CORRIDOR = "Corridor"
    STAIRCASS = "Staircase"
    OTS = "OTS"
    BALCONY = "Balcony"
    POOJA = "Pooja Room"
    UTILITY = "Utility"
    STUDY = "Study Room"
    OTHER = "Other"


class NormalizedRoomBox(BaseModel):
    """
    Represents a room box in normalized unit coordinates [0.0, 1.0]
    relative to the net buildable envelope (u = X / Width, v = Y / Depth).
    u: 0.0 (Left edge) -> 1.0 (Right edge)
    v: 0.0 (Front Road facade) -> 1.0 (Rear boundary)
    """
    name: str = Field(..., description="Unique functional name of the space, e.g. 'Living Room', 'Master Bedroom', 'Kitchen', 'Attached Bath 1'.")
    room_type: BlueprintRoomType = Field(..., description="Standardized functional type of the room.")
    zone: FunctionalZone = Field(..., description="Architectural zone this space belongs to.")
    u_min: float = Field(..., ge=0.0, le=1.0, description="Normalized left X boundary (0.0 to 1.0).")
    v_min: float = Field(..., ge=0.0, le=1.0, description="Normalized bottom/front Y boundary (0.0 to 1.0).")
    u_max: float = Field(..., ge=0.0, le=1.0, description="Normalized right X boundary (0.0 to 1.0).")
    v_max: float = Field(..., ge=0.0, le=1.0, description="Normalized top/rear Y boundary (0.0 to 1.0).")
    floor_assignment: int = Field(1, ge=1, description="Floor level: 1 for Ground, 2 for First/Upper.")
    attached_to: Optional[str] = Field(None, description="If this room is an ensuite/attached space (e.g. 'Attached Bath' attached to 'Master Bedroom').")
    requires_natural_light: bool = Field(True, description="Whether this room requires an exterior window or OTS light shaft.")

    @field_validator("u_max")
    @classmethod
    def validate_u_span(cls, v: float, info) -> float:
        u_min = info.data.get("u_min", 0.0)
        if v <= u_min:
            raise ValueError(f"u_max ({v}) must be strictly greater than u_min ({u_min})")
        return round(min(1.0, max(0.0, v)), 4)

    @field_validator("v_max")
    @classmethod
    def validate_v_span(cls, v: float, info) -> float:
        v_min = info.data.get("v_min", 0.0)
        if v <= v_min:
            raise ValueError(f"v_max ({v}) must be strictly greater than v_min ({v_min})")
        return round(min(1.0, max(0.0, v)), 4)


class SpatialBlueprint(BaseModel):
    """
    Scale-invariant spatial blueprint representing the complete layout plan
    for any plot dimension.
    """
    title: str = Field(..., description="Architectural concept title, e.g. '2BHK Linear Courtyard Layout'.")
    concept_summary: str = Field(..., description="Brief architectural reasoning explaining the zoning and circulation logic.")
    envelope_aspect_ratio_type: str = Field(..., description="Aspect ratio classification: 'narrow_deep', 'square_balanced', 'wide_shallow'.")
    road_facing_edge: str = Field("bottom", description="Edge where the road is located: 'bottom' (default), 'top', 'left', 'right'.")
    rooms: List[NormalizedRoomBox] = Field(..., description="List of normalized room spaces composing the complete layout.")
    has_central_circulation: bool = Field(True, description="Whether a dedicated circulation spine connects the front to rear.")
