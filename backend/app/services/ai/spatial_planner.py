"""
LLM Spatial Space Planner (Agent 1).
Translates user requirements and envelope geometry into a scale-invariant,
macro-zoned SpatialBlueprint using structured LLM reasoning and dynamic algorithmic fallback.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.schemas.intent import CompilerIntent, RoomCategory
from app.schemas.spatial_blueprint import (
    BlueprintRoomType,
    FunctionalZone,
    NormalizedRoomBox,
    SpatialBlueprint,
)

logger = logging.getLogger(__name__)

SPATIAL_PLANNER_SYSTEM_PROMPT = """You are an expert Senior Residential Architect and Space Planner.
Your task is to organize an optimal, functional residential floor plan layout for ANY given plot dimensions and room program.

CRITICAL ARCHITECTURAL RULES:
1. NORMALIZED COORDINATE SYSTEM [0.0 to 1.0]:
   - u is the X-axis: 0.0 (Left edge) to 1.0 (Right edge).
   - v is the Y-axis: 0.0 (Front Road facade) to 1.0 (Rear boundary).
   - All room boundaries must fall strictly within [0.0, 1.0].
   - Rooms must fit together like puzzle pieces with shared straight boundary lines.

2. FUNCTIONAL MACRO-ZONING:
   - Front Zone (v: 0.0 to 0.35): Entrance Foyer, Verandah, Living Room, Guest Powder Room.
   - Middle Zone (v: 0.30 to 0.65): Staircase (if multi-floor), Dining Room, Kitchen, Central Hallway / Circulation Spine.
   - Rear Zone (v: 0.60 to 1.0): Master Bedroom, Secondary Bedrooms, Attached Bathrooms, OTS Lightwells.

3. MANDATORY CIRCULATION SPINE:
   - You MUST include a dedicated 'Circulation Spine' or 'Central Hallway' (room_type: Corridor) connecting the Front/Foyer directly to the rear bedrooms and bathrooms.
   - No bedroom should ever require walking through another bedroom or through the kitchen.

4. REALISTIC PROPORTIONS:
   - Living Room: Generous front area (e.g. u span 0.0 to 0.6 or 0.7, v span 0.0 to 0.35).
   - Kitchen: Located adjacent to Dining or near Front/Middle side edge for ventilation (e.g. u span 0.6 to 1.0, v span 0.0 to 0.35 or 0.35 to 0.65).
   - Bedrooms: Positioned in quiet rear zone with exterior boundary touch for natural light.
   - Bathrooms: Attached baths placed adjacent to their respective bedrooms or in central service corridor.
"""


def _classify_aspect_ratio(buildable_width: float, buildable_depth: float) -> str:
    """Classifies the envelope aspect ratio."""
    if buildable_width <= 0 or buildable_depth <= 0:
        return "square_balanced"
    ar = buildable_depth / buildable_width
    if ar > 1.25:
        return "narrow_deep"
    elif ar < 0.80:
        return "wide_shallow"
    return "square_balanced"


def generate_algorithmic_blueprint(
    intent: CompilerIntent,
    buildable_width: float,
    buildable_depth: float,
    road_edge: str = "bottom",
) -> SpatialBlueprint:
    """
    Generalized programmatic fallback that dynamically generates a clean,
    architecturally sound normalized spatial blueprint for ANY plot dimensions and room program.
    """
    ar_type = _classify_aspect_ratio(buildable_width, buildable_depth)
    
    # Extract requested room types from intent
    has_stair = intent.floors > 1 or (intent.vertical_circulation is not None and intent.vertical_circulation != "none")
    num_beds = sum(1 for r in intent.rooms if r.room_type == RoomCategory.BEDROOM) or 2
    num_baths = sum(1 for r in intent.rooms if r.room_type == RoomCategory.BATHROOM) or max(1, num_beds - 1)
    has_pooja = any(r.room_type == RoomCategory.POOJA for r in intent.rooms)

    rooms: List[NormalizedRoomBox] = []

    # =========================================================================
    # 1. NARROW DEEP LAYOUT (Linear Spine Topology)
    # =========================================================================
    if ar_type == "narrow_deep":
        # Front Zone: Foyer (left/center) + Living Room (spans front)
        rooms.append(NormalizedRoomBox(
            name="Living Room",
            room_type=BlueprintRoomType.LIVING,
            zone=FunctionalZone.FRONT_PUBLIC,
            u_min=0.0, v_min=0.0, u_max=1.0, v_max=0.30,
            floor_assignment=1,
            requires_natural_light=True
        ))

        # Middle Zone Left: Kitchen & Dining; Middle Zone Center/Right: Circulation Spine + Stair
        stair_u_min = 0.70 if has_stair else 1.0
        
        # Central Circulation Spine
        rooms.append(NormalizedRoomBox(
            name="Circulation Spine",
            room_type=BlueprintRoomType.CORRIDOR,
            zone=FunctionalZone.MIDDLE_CORE,
            u_min=0.45, v_min=0.30, u_max=0.70, v_max=0.68,
            floor_assignment=1,
            requires_natural_light=False
        ))

        # Kitchen & Dining
        rooms.append(NormalizedRoomBox(
            name="Kitchen",
            room_type=BlueprintRoomType.KITCHEN,
            zone=FunctionalZone.MIDDLE_CORE,
            u_min=0.0, v_min=0.30, u_max=0.45, v_max=0.50,
            floor_assignment=1,
            requires_natural_light=True
        ))
        rooms.append(NormalizedRoomBox(
            name="Dining Room",
            room_type=BlueprintRoomType.DINING,
            zone=FunctionalZone.MIDDLE_CORE,
            u_min=0.0, v_min=0.50, u_max=0.45, v_max=0.68,
            floor_assignment=1,
            requires_natural_light=True
        ))

        if has_stair:
            rooms.append(NormalizedRoomBox(
                name="Staircase",
                room_type=BlueprintRoomType.STAIRCASS,
                zone=FunctionalZone.MIDDLE_CORE,
                u_min=0.70, v_min=0.30, u_max=1.0, v_max=0.50,
                floor_assignment=1,
                requires_natural_light=False
            ))
            # Common Bathroom below or next to stair
            rooms.append(NormalizedRoomBox(
                name="Common Bathroom",
                room_type=BlueprintRoomType.BATHROOM,
                zone=FunctionalZone.SERVICE,
                u_min=0.70, v_min=0.50, u_max=1.0, v_max=0.68,
                floor_assignment=1,
                requires_natural_light=False
            ))
        else:
            rooms.append(NormalizedRoomBox(
                name="Common Bathroom",
                room_type=BlueprintRoomType.BATHROOM,
                zone=FunctionalZone.SERVICE,
                u_min=0.70, v_min=0.30, u_max=1.0, v_max=0.50,
                floor_assignment=1,
                requires_natural_light=False
            ))

        # Rear Zone: Bedrooms
        if num_beds == 1:
            rooms.append(NormalizedRoomBox(
                name="Master Bedroom",
                room_type=BlueprintRoomType.MASTER_BEDROOM,
                zone=FunctionalZone.REAR_PRIVATE,
                u_min=0.0, v_min=0.68, u_max=1.0, v_max=1.0,
                floor_assignment=1,
                requires_natural_light=True
            ))
        else:
            if buildable_width < 18.0:
                # Tandem / Staggered Layout for narrow rowhouses (< 18ft buildable width)
                rooms.append(NormalizedRoomBox(
                    name="Bedroom 2",
                    room_type=BlueprintRoomType.BEDROOM,
                    zone=FunctionalZone.MIDDLE_CORE,
                    u_min=0.0, v_min=0.50, u_max=0.65, v_max=0.72,
                    floor_assignment=1,
                    requires_natural_light=True
                ))
                rooms.append(NormalizedRoomBox(
                    name="Master Bedroom",
                    room_type=BlueprintRoomType.MASTER_BEDROOM,
                    zone=FunctionalZone.REAR_PRIVATE,
                    u_min=0.0, v_min=0.72, u_max=1.0, v_max=1.0,
                    floor_assignment=1,
                    requires_natural_light=True
                ))
            else:
                # 2 Rear Bedrooms side by side for wider plots
                rooms.append(NormalizedRoomBox(
                    name="Master Bedroom",
                    room_type=BlueprintRoomType.MASTER_BEDROOM,
                    zone=FunctionalZone.REAR_PRIVATE,
                    u_min=0.0, v_min=0.68, u_max=0.55, v_max=1.0,
                    floor_assignment=1,
                    requires_natural_light=True
                ))
                rooms.append(NormalizedRoomBox(
                    name="Bedroom 2",
                    room_type=BlueprintRoomType.BEDROOM,
                    zone=FunctionalZone.REAR_PRIVATE,
                    u_min=0.55, v_min=0.68, u_max=1.0, v_max=1.0,
                    floor_assignment=1,
                    requires_natural_light=True
                ))


    # =========================================================================
    # 2. WIDE SHALLOW LAYOUT (Lateral Dual-Wing Topology)
    # =========================================================================
    elif ar_type == "wide_shallow":
        # Left Wing: Living (Front) + Master Bed (Rear)
        # Center Core: Foyer & Corridor (Front) + Common Bathroom (Middle) + OTS / Utility (Rear)
        # Right Wing: Kitchen & Dining (Front) + Bedroom 2 (Rear)
        rooms.append(NormalizedRoomBox(
            name="Living Room",
            room_type=BlueprintRoomType.LIVING,
            zone=FunctionalZone.FRONT_PUBLIC,
            u_min=0.0, v_min=0.0, u_max=0.42, v_max=0.50,
            floor_assignment=1,
            requires_natural_light=True
        ))
        rooms.append(NormalizedRoomBox(
            name="Foyer & Corridor",
            room_type=BlueprintRoomType.CORRIDOR,
            zone=FunctionalZone.FRONT_PUBLIC,
            u_min=0.42, v_min=0.0, u_max=0.58, v_max=0.50,
            floor_assignment=1,
            requires_natural_light=False
        ))
        rooms.append(NormalizedRoomBox(
            name="Kitchen & Dining",
            room_type=BlueprintRoomType.KITCHEN,
            zone=FunctionalZone.MIDDLE_CORE,
            u_min=0.58, v_min=0.0, u_max=1.0, v_max=0.50,
            floor_assignment=1,
            requires_natural_light=True
        ))
        rooms.append(NormalizedRoomBox(
            name="Master Bedroom",
            room_type=BlueprintRoomType.MASTER_BEDROOM,
            zone=FunctionalZone.REAR_PRIVATE,
            u_min=0.0, v_min=0.50, u_max=0.42, v_max=1.0,
            floor_assignment=1,
            requires_natural_light=True
        ))
        rooms.append(NormalizedRoomBox(
            name="Common Bathroom",
            room_type=BlueprintRoomType.BATHROOM,
            zone=FunctionalZone.SERVICE,
            u_min=0.42, v_min=0.50, u_max=0.58, v_max=0.75,
            floor_assignment=1,
            requires_natural_light=False
        ))
        rooms.append(NormalizedRoomBox(
            name="OTS Shaft",
            room_type=BlueprintRoomType.OTS,
            zone=FunctionalZone.SERVICE,
            u_min=0.42, v_min=0.75, u_max=0.58, v_max=1.0,
            floor_assignment=1,
            requires_natural_light=True
        ))
        rooms.append(NormalizedRoomBox(
            name="Bedroom 2",
            room_type=BlueprintRoomType.BEDROOM,
            zone=FunctionalZone.REAR_PRIVATE,
            u_min=0.58, v_min=0.50, u_max=1.0, v_max=1.0,
            floor_assignment=1,
            requires_natural_light=True
        ))


    # =========================================================================
    # 3. SQUARE BALANCED LAYOUT (Quad-Zone Modern Residential Topology)
    # =========================================================================
    else:
        if num_beds == 1:
            # 1BHK Compact Suite with Dedicated OTS Shaft or Staircase
            rooms.append(NormalizedRoomBox(
                name="Living Room",
                room_type=BlueprintRoomType.LIVING,
                zone=FunctionalZone.FRONT_PUBLIC,
                u_min=0.0, v_min=0.0, u_max=0.60, v_max=0.40,
                floor_assignment=1,
                requires_natural_light=True
            ))
            rooms.append(NormalizedRoomBox(
                name="Kitchen",
                room_type=BlueprintRoomType.KITCHEN,
                zone=FunctionalZone.MIDDLE_CORE,
                u_min=0.60, v_min=0.0, u_max=1.0, v_max=0.40,
                floor_assignment=1,
                requires_natural_light=True
            ))
            rooms.append(NormalizedRoomBox(
                name="Circulation Corridor",
                room_type=BlueprintRoomType.CORRIDOR,
                zone=FunctionalZone.MIDDLE_CORE,
                u_min=0.0, v_min=0.40, u_max=0.40, v_max=0.58,
                floor_assignment=1,
                requires_natural_light=False
            ))
            rooms.append(NormalizedRoomBox(
                name="Bathroom",
                room_type=BlueprintRoomType.BATHROOM,
                zone=FunctionalZone.SERVICE,
                u_min=0.40, v_min=0.40, u_max=0.75, v_max=0.58,
                floor_assignment=1,
                requires_natural_light=False
            ))
            if has_stair:
                rooms.append(NormalizedRoomBox(
                    name="Staircase",
                    room_type=BlueprintRoomType.STAIRCASS,
                    zone=FunctionalZone.SERVICE,
                    u_min=0.75, v_min=0.40, u_max=1.0, v_max=0.58,
                    floor_assignment=1,
                    requires_natural_light=False
                ))
            else:
                rooms.append(NormalizedRoomBox(
                    name="OTS Shaft",
                    room_type=BlueprintRoomType.OTS,
                    zone=FunctionalZone.SERVICE,
                    u_min=0.75, v_min=0.40, u_max=1.0, v_max=0.58,
                    floor_assignment=1,
                    requires_natural_light=True
                ))
            rooms.append(NormalizedRoomBox(
                name="Master Bedroom",
                room_type=BlueprintRoomType.MASTER_BEDROOM,
                zone=FunctionalZone.REAR_PRIVATE,
                u_min=0.0, v_min=0.58, u_max=1.0, v_max=1.0,
                floor_assignment=1,
                requires_natural_light=True
            ))


        else:
            # Front Left: Living Room; Front Right: Foyer / Kitchen
            rooms.append(NormalizedRoomBox(
                name="Living Room",
                room_type=BlueprintRoomType.LIVING,
                zone=FunctionalZone.FRONT_PUBLIC,
                u_min=0.0, v_min=0.0, u_max=0.58, v_max=0.42,
                floor_assignment=1,
                requires_natural_light=True
            ))
            rooms.append(NormalizedRoomBox(
                name="Kitchen",
                room_type=BlueprintRoomType.KITCHEN,
                zone=FunctionalZone.MIDDLE_CORE,
                u_min=0.58, v_min=0.0, u_max=1.0, v_max=0.42,
                floor_assignment=1,
                requires_natural_light=True
            ))

            # Center: Circulation Hallway & Dining
            rooms.append(NormalizedRoomBox(
                name="Dining & Hallway",
                room_type=BlueprintRoomType.CORRIDOR,
                zone=FunctionalZone.MIDDLE_CORE,
                u_min=0.35, v_min=0.42, u_max=0.65, v_max=0.68,
                floor_assignment=1,
                requires_natural_light=False
            ))

            if has_stair:
                rooms.append(NormalizedRoomBox(
                    name="Staircase",
                    room_type=BlueprintRoomType.STAIRCASS,
                    zone=FunctionalZone.MIDDLE_CORE,
                    u_min=0.0, v_min=0.42, u_max=0.35, v_max=0.68,
                    floor_assignment=1,
                    requires_natural_light=False
                ))
            else:
                rooms.append(NormalizedRoomBox(
                    name="Common Bathroom",
                    room_type=BlueprintRoomType.BATHROOM,
                    zone=FunctionalZone.SERVICE,
                    u_min=0.0, v_min=0.42, u_max=0.35, v_max=0.68,
                    floor_assignment=1,
                    requires_natural_light=False
                ))

            rooms.append(NormalizedRoomBox(
                name="Bathroom 2",
                room_type=BlueprintRoomType.BATHROOM,
                zone=FunctionalZone.SERVICE,
                u_min=0.65, v_min=0.42, u_max=1.0, v_max=0.68,
                floor_assignment=1,
                requires_natural_light=False
            ))

            # Rear: Master Bedroom & Bedroom 2
            rooms.append(NormalizedRoomBox(
                name="Master Bedroom",
                room_type=BlueprintRoomType.MASTER_BEDROOM,
                zone=FunctionalZone.REAR_PRIVATE,
                u_min=0.0, v_min=0.68, u_max=0.52, v_max=1.0,
                floor_assignment=1,
                requires_natural_light=True
            ))
            rooms.append(NormalizedRoomBox(
                name="Bedroom 2",
                room_type=BlueprintRoomType.BEDROOM,
                zone=FunctionalZone.REAR_PRIVATE,
                u_min=0.52, v_min=0.68, u_max=1.0, v_max=1.0,
                floor_assignment=1,
                requires_natural_light=True
            ))


    return SpatialBlueprint(
        title=f"Architectural Blueprint ({ar_type.replace('_', ' ').title()})",
        concept_summary=f"Scale-invariant macro-zoned plan tailored for {buildable_width:.1f}' x {buildable_depth:.1f}' buildable envelope with central circulation.",
        envelope_aspect_ratio_type=ar_type,
        road_facing_edge=road_edge,
        rooms=rooms,
        has_central_circulation=True
    )


def plan_spatial_blueprint(
    prompt: str,
    intent: CompilerIntent,
    buildable_width: float,
    buildable_depth: float,
    road_edge: str = "bottom",
    client: Any = None,
) -> SpatialBlueprint:
    """
    Main Spatial Planner Entrypoint (Agent 1).
    Attempts structured architectural reasoning with Gemini Flash,
    falling back to deterministic algorithmic zoning on failure.
    """
    ar_type = _classify_aspect_ratio(buildable_width, buildable_depth)
    
    if client is not None:
        try:
            user_msg = (
                f"User Request: {prompt}\n"
                f"Plot Dimensions: Buildable Width = {buildable_width:.1f} ft, Buildable Depth = {buildable_depth:.1f} ft\n"
                f"Aspect Ratio Classification: {ar_type}\n"
                f"Road Facade Edge: {road_edge}\n"
                f"Floors: {intent.floors}\n"
                f"Extracted Rooms: {[r.room_type.value for r in intent.rooms]}\n"
                "Generate a normalized, collision-free SpatialBlueprint where all u and v values are within [0.0, 1.0]."
            )
            
            blueprint: SpatialBlueprint = client.create(
                model="gemini-2.5-flash",
                response_model=SpatialBlueprint,
                max_retries=1,
                strict=False,
                messages=[
                    {"role": "system", "content": SPATIAL_PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg}
                ]
            )
            
            # Quick sanity validation
            if blueprint.rooms and len(blueprint.rooms) >= 3:
                return blueprint
                
        except Exception as exc:
            logger.warning(f"[Spatial Planner Agent] LLM reasoning fallback triggered: {exc}")

    # Fallback to algorithmic generator
    return generate_algorithmic_blueprint(
        intent=intent,
        buildable_width=buildable_width,
        buildable_depth=buildable_depth,
        road_edge=road_edge
    )
