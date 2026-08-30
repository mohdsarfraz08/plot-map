from enum import Enum

from pydantic import BaseModel, Field, model_validator


class RoomCategory(str, Enum):
    BEDROOM = "bedroom"
    LIVING = "living"
    KITCHEN = "kitchen"
    BATHROOM = "bathroom"
    CORRIDOR = "corridor"
    POOJA = "pooja"

class RoomIntent(BaseModel):
    """
    Represents the user's intent for a single room, capturing its type and minimum area.
    """
    room_type: RoomCategory = Field(
        ...,
        description="The type category of the room (bedroom, living, kitchen, bathroom, corridor, pooja)."
    )
    min_area_sqft: int | None = Field(
        None,
        description="Minimum area of the room in square feet. If missing, default to standard Indian minimums (Bedroom: 100, Living Room: 150, Kitchen: 60, Bathroom: 30, others: 50)."
    )

    @model_validator(mode='after')
    def apply_indian_minimums(self) -> 'RoomIntent':
        """
        Ensures standard Indian minimum sizes are enforced if no area is specified.
        """
        if self.min_area_sqft is None or self.min_area_sqft <= 0:
            if self.room_type == RoomCategory.BEDROOM:
                self.min_area_sqft = 100
            elif self.room_type == RoomCategory.LIVING:
                self.min_area_sqft = 150
            elif self.room_type == RoomCategory.KITCHEN:
                self.min_area_sqft = 60
            elif self.room_type == RoomCategory.BATHROOM:
                self.min_area_sqft = 30
            else:
                self.min_area_sqft = 50
        return self

class CompilerIntent(BaseModel):
    """
    The main schema containing all extracted parameters required by the architectural constraint engine.
    """
    plot_width: float = Field(
        ...,
        description="Width of the plot in feet."
    )
    plot_depth: float = Field(
        ...,
        description="Depth of the plot in feet."
    )
    floors: int = Field(
        1,
        description="Total number of floors. Defaults to 1. Note: G+1 = 2 floors, G+2 = 3 floors, etc."
    )
    front_road_setback: float = Field(
        5.0,
        description="Front road setback distance in feet. Defaults to 5.0."
    )
    confidence_score: float = Field(
        1.0,
        description="Confidence score of the extraction (0.0 to 1.0). Fallback parser defaults to 0.5."
    )
    rooms: list[RoomIntent] = Field(
        default_factory=list,
        description="List of rooms to pack into the floor layout."
    )
    vertical_circulation: str | None = Field(
        None,
        description="Staircase / circulation strategy: 'shared', 'independent' (separate/private), or 'hybrid'."
    )
    floor_allocation: str | None = Field(
        None,
        description="Floor distribution strategy: 'ground_floor_only' (all families/units on ground floor) or 'distributed' (distributed across floors)."
    )
    families_count: int = Field(
        1,
        description="Number of families or units requested (e.g. 2 families). Defaults to 1."
    )
    unit_organization: str | None = Field(
        None,
        description="Unit organization strategy: 'grouped', 'distributed', or 'stacked'."
    )
    entrance_strategy: str | None = Field(
        None,
        description="Entrance strategy: 'shared', 'independent', or 'controlled_shared'."
    )
