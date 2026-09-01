"""
Tests for SpatialBlueprint schema and Spatial Planner (Agent 1).
Validates scale-invariance across diverse plot dimensions and room requirements.
"""

import pytest
from app.schemas.intent import CompilerIntent, RoomCategory, RoomIntent
from app.schemas.spatial_blueprint import (
    BlueprintRoomType,
    FunctionalZone,
    NormalizedRoomBox,
    SpatialBlueprint,
)
from app.services.ai.spatial_planner import (
    _classify_aspect_ratio,
    generate_algorithmic_blueprint,
    plan_spatial_blueprint,
)


def test_normalized_room_box_validation():
    """Verify NormalizedRoomBox validates bounds within [0.0, 1.0]."""
    room = NormalizedRoomBox(
        name="Living Room",
        room_type=BlueprintRoomType.LIVING,
        zone=FunctionalZone.FRONT_PUBLIC,
        u_min=0.0,
        v_min=0.0,
        u_max=0.6,
        v_max=0.4,
    )
    assert room.u_min == 0.0
    assert room.u_max == 0.6
    assert room.v_min == 0.0
    assert room.v_max == 0.4


def test_aspect_ratio_classification():
    """Verify aspect ratio classification for various plot geometries."""
    assert _classify_aspect_ratio(20.0, 40.0) == "narrow_deep"     # AR = 2.0
    assert _classify_aspect_ratio(30.0, 30.0) == "square_balanced"  # AR = 1.0
    assert _classify_aspect_ratio(50.0, 30.0) == "wide_shallow"     # AR = 0.6


@pytest.mark.parametrize(
    "width,depth,num_beds",
    [
        (20.0, 50.0, 2),  # Narrow Rowhouse
        (30.0, 40.0, 2),  # Standard 1200 sqft Plot
        (40.0, 40.0, 3),  # Square Plot
        (60.0, 35.0, 3),  # Wide Plot / Villa
        (50.0, 80.0, 4),  # Large Luxury Estate
    ],
)
def test_spatial_planner_any_dimensions(width: float, depth: float, num_beds: int):
    """
    Verify spatial planner generates clean, complete blueprints
    for any arbitrary plot dimensions without crashing or hardcoding.
    """
    rooms = [RoomIntent(room_type=RoomCategory.LIVING), RoomIntent(room_type=RoomCategory.KITCHEN)]
    for _ in range(num_beds):
        rooms.append(RoomIntent(room_type=RoomCategory.BEDROOM))

    intent = CompilerIntent(
        plot_width=width,
        plot_depth=depth,
        floors=1,
        front_road_setback=5.0,
        rooms=rooms,
    )

    blueprint = plan_spatial_blueprint(
        prompt=f"House on {width}x{depth} plot with {num_beds} bedrooms",
        intent=intent,
        buildable_width=width - 6.0,
        buildable_depth=depth - 8.0,
        road_edge="bottom",
        client=None,  # Tests algorithmic fallback
    )

    assert isinstance(blueprint, SpatialBlueprint)
    assert len(blueprint.rooms) >= 4
    assert blueprint.has_central_circulation is True

    # Verify all normalized coordinates are strictly within [0.0, 1.0]
    for r in blueprint.rooms:
        assert 0.0 <= r.u_min < r.u_max <= 1.0
        assert 0.0 <= r.v_min < r.v_max <= 1.0

    # Verify key zones exist
    zones = {r.zone for r in blueprint.rooms}
    assert FunctionalZone.FRONT_PUBLIC in zones
    assert FunctionalZone.MIDDLE_CORE in zones
    assert FunctionalZone.REAR_PRIVATE in zones


def test_spatial_planner_with_staircase():
    """Verify staircase is allocated for multi-floor intent."""
    intent = CompilerIntent(
        plot_width=40.0,
        plot_depth=40.0,
        floors=2,
        rooms=[
            RoomIntent(room_type=RoomCategory.BEDROOM),
            RoomIntent(room_type=RoomCategory.LIVING),
            RoomIntent(room_type=RoomCategory.KITCHEN),
        ],
    )

    blueprint = plan_spatial_blueprint(
        prompt="G+1 house with stairs",
        intent=intent,
        buildable_width=34.0,
        buildable_depth=32.0,
        client=None,
    )

    room_types = [r.room_type for r in blueprint.rooms]
    assert BlueprintRoomType.STAIRCASS in room_types
