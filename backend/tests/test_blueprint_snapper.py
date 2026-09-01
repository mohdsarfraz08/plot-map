"""
Tests for Blueprint Snapper and Boundary Stitcher.
Verifies that floating-point hallucinations, micro-gaps, and wall overlaps
are completely crushed and normalized into airtight collinear coordinates.
"""

from app.schemas.spatial_blueprint import (
    BlueprintRoomType,
    FunctionalZone,
    NormalizedRoomBox,
    SpatialBlueprint,
)
from app.services.geometry.blueprint_snapper import (
    cleanse_and_stitch_blueprint,
    realize_blueprint_to_world_layout,
)


def test_micro_gap_crushing():
    """
    Test that an intentional 0.02 float gap between Living Room (u_max=0.58)
    and Kitchen (u_min=0.60) is stitched into an exact shared partition boundary.
    """
    raw_blueprint = SpatialBlueprint(
        title="Test Gap Layout",
        concept_summary="Test layout with intentional float gap",
        envelope_aspect_ratio_type="square_balanced",
        road_facing_edge="bottom",
        rooms=[
            NormalizedRoomBox(
                name="Living Room",
                room_type=BlueprintRoomType.LIVING,
                zone=FunctionalZone.FRONT_PUBLIC,
                u_min=0.0,
                v_min=0.0,
                u_max=0.58,  # Intentional gap: 0.58 vs 0.60
                v_max=0.40,
            ),
            NormalizedRoomBox(
                name="Kitchen",
                room_type=BlueprintRoomType.KITCHEN,
                zone=FunctionalZone.MIDDLE_CORE,
                u_min=0.60,  # Intentional gap
                v_min=0.0,
                u_max=1.0,
                v_max=0.40,
            ),
            NormalizedRoomBox(
                name="Master Bedroom",
                room_type=BlueprintRoomType.MASTER_BEDROOM,
                zone=FunctionalZone.REAR_PRIVATE,
                u_min=0.0,
                v_min=0.42,  # Intentional horizontal gap (0.40 vs 0.42)
                u_max=1.0,
                v_max=1.0,
            ),
        ],
    )

    stitched = cleanse_and_stitch_blueprint(raw_blueprint, stitch_threshold=0.05)

    living = next(r for r in stitched.rooms if r.name == "Living Room")
    kitchen = next(r for r in stitched.rooms if r.name == "Kitchen")
    bedroom = next(r for r in stitched.rooms if r.name == "Master Bedroom")

    # The vertical partition between Living and Kitchen MUST match exactly
    assert living.u_max == kitchen.u_min
    # The horizontal partition between front rooms and Master Bedroom MUST match exactly
    assert living.v_max == bedroom.v_min
    assert kitchen.v_max == bedroom.v_min


def test_realize_world_layout_and_adjacencies():
    """
    Verify real-world scaling on a 30x40 ft plot with setbacks
    yields clean 0.5 ft snapped coordinates and valid shared wall adjacencies.
    """
    blueprint = SpatialBlueprint(
        title="2BHK Plan",
        concept_summary="Clean 2BHK Plan",
        envelope_aspect_ratio_type="square_balanced",
        road_facing_edge="bottom",
        rooms=[
            NormalizedRoomBox(
                name="Living Room",
                room_type=BlueprintRoomType.LIVING,
                zone=FunctionalZone.FRONT_PUBLIC,
                u_min=0.0, v_min=0.0, u_max=0.55, v_max=0.40,
            ),
            NormalizedRoomBox(
                name="Kitchen",
                room_type=BlueprintRoomType.KITCHEN,
                zone=FunctionalZone.MIDDLE_CORE,
                u_min=0.55, v_min=0.0, u_max=1.0, v_max=0.40,
            ),
            NormalizedRoomBox(
                name="Circulation Corridor",
                room_type=BlueprintRoomType.CORRIDOR,
                zone=FunctionalZone.MIDDLE_CORE,
                u_min=0.0, v_min=0.40, u_max=1.0, v_max=0.60,
            ),
            NormalizedRoomBox(
                name="Master Bedroom",
                room_type=BlueprintRoomType.MASTER_BEDROOM,
                zone=FunctionalZone.REAR_PRIVATE,
                u_min=0.0, v_min=0.60, u_max=0.50, v_max=1.0,
            ),
            NormalizedRoomBox(
                name="Bedroom 2",
                room_type=BlueprintRoomType.BEDROOM,
                zone=FunctionalZone.REAR_PRIVATE,
                u_min=0.50, v_min=0.60, u_max=1.0, v_max=1.0,
            ),
        ],
    )

    result = realize_blueprint_to_world_layout(
        blueprint=blueprint,
        plot_width=30.0,
        plot_depth=40.0,
        setbacks={"left": 3.0, "right": 3.0, "bottom": 5.0, "top": 3.0},
        grid_snap_ft=0.5,
    )

    rooms = result["rooms"]
    adjacencies = result["adjacencies"]

    assert len(rooms) == 5
    assert len(adjacencies) >= 4

    # Check that living room and kitchen share a vertical wall
    assert ("Living Room", "Kitchen") in adjacencies or ("Kitchen", "Living Room") in adjacencies
    # Check that corridor touches front rooms and rear bedrooms
    assert any("Circulation Corridor" in pair for pair in adjacencies)

    # Check clean 0.5 ft grid alignment
    for r in rooms.values():
        assert r["x"] % 0.5 == 0.0
        assert r["y"] % 0.5 == 0.0
        assert r["width"] % 0.5 == 0.0
        assert r["height"] % 0.5 == 0.0
