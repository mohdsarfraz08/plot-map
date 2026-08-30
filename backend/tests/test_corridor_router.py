"""
Unit tests for DiscreteGridMatrix, DoorwayAnchorExtractor, AStarCorridorPathfinder,
and CorridorPolygonGenerator (Stage 3B.4D / Phase 2).
"""

import pytest
from shapely.geometry import Polygon, box

from app.services.realization.corridor_router import (
    AStarCorridorPathfinder,
    CorridorPolygonGenerator,
    DiscreteGridMatrix,
    DoorwayAnchorExtractor,
)


def test_grid_matrix_initialization():
    """Verify grid bounds, resolution, and legal envelope walkability."""
    grid = DiscreteGridMatrix(
        plot_width=40.0,
        plot_depth=40.0,
        setbacks={"left": 3.0, "right": 3.0, "bottom": 5.0, "top": 3.0},
        resolution=0.5,
    )
    assert grid.cols == 80
    assert grid.rows == 80

    # Outside setbacks should be unwalkable (0)
    r_out, c_out = grid.world_to_grid(1.0, 1.0)
    assert not grid.is_walkable(r_out, c_out)

    # Inside legal envelope should be walkable (1)
    r_in, c_in = grid.world_to_grid(20.0, 20.0)
    assert grid.is_walkable(r_in, c_in)


def test_room_obstacle_masking():
    """Verify room bounding boxes are marked unwalkable (0)."""
    grid = DiscreteGridMatrix(
        plot_width=40.0,
        plot_depth=40.0,
        setbacks={"left": 0.0, "right": 0.0, "bottom": 0.0, "top": 0.0},
        resolution=0.5,
    )
    # Mask a 10x10 room at (10, 10) to (20, 20)
    grid.mask_room_obstacle(10.0, 10.0, 20.0, 20.0)

    # Room interior should now be unwalkable
    r_inside, c_inside = grid.world_to_grid(15.0, 15.0)
    assert not grid.is_walkable(r_inside, c_inside)

    # Negative space outside room should remain walkable
    r_outside, c_outside = grid.world_to_grid(5.0, 5.0)
    assert grid.is_walkable(r_outside, c_outside)


def test_doorway_anchor_extractor_perimeter_scan():
    """
    Verify DoorwayAnchorExtractor scans the perimeter and identifies valid walkable cells
    avoiding blocked walls (The Midpoint Trap test).
    """
    grid = DiscreteGridMatrix(
        plot_width=40.0,
        plot_depth=40.0,
        setbacks={"left": 0.0, "right": 0.0, "bottom": 0.0, "top": 0.0},
        resolution=0.5,
    )
    # Room 1 at (0, 0) to (10, 10) - flush against left/bottom boundary
    # Room 2 at (10, 0) to (20, 10) - touching Room 1 on its right
    grid.mask_room_obstacle(0.0, 0.0, 10.0, 10.0)
    grid.mask_room_obstacle(10.0, 0.0, 20.0, 10.0)

    room_bounds = {
        "room_1": (0.0, 0.0, 10.0, 10.0),
        "room_2": (10.0, 0.0, 20.0, 10.0),
    }

    thresholds = DoorwayAnchorExtractor.extract_thresholds(
        grid, room_bounds, origin_xy=(20.0, 20.0)
    )

    assert "room_1" in thresholds
    assert "room_2" in thresholds

    # The threshold for room 1 must be adjacent to walkable space (e.g. top edge y >= 10.0)
    t1 = thresholds["room_1"]
    assert grid.is_walkable(t1.grid_row, t1.grid_col)
    assert t1.world_y >= 9.5


def test_astar_pathfinding_and_corridor_buffering():
    """Verify A* path is found through negative space and buffered to 3.5ft corridor."""
    grid = DiscreteGridMatrix(
        plot_width=40.0,
        plot_depth=40.0,
        setbacks={"left": 0.0, "right": 0.0, "bottom": 0.0, "top": 0.0},
        resolution=0.5,
    )
    # Obstacle in center: (10, 10) to (30, 30)
    grid.mask_room_obstacle(10.0, 10.0, 30.0, 30.0)

    start_rc = grid.world_to_grid(5.0, 5.0)
    goal_rc = grid.world_to_grid(35.0, 35.0)

    path = AStarCorridorPathfinder.find_path(grid, start_rc, goal_rc)
    assert len(path) > 0

    # Ensure path goes around the obstacle without penetrating it
    for r, c in path:
        assert grid.is_walkable(r, c)

    # Convert to world coords and buffer into 2D corridor
    path_xy = [grid.grid_to_world(r, c) for r, c in path]
    legal_envelope = box(0.0, 0.0, 40.0, 40.0)
    room_polygon = box(10.0, 10.0, 30.0, 30.0)

    corridor_poly = CorridorPolygonGenerator.generate_corridor_polygons(
        paths=[path_xy],
        corridor_width=3.5,
        legal_envelope=legal_envelope,
        room_polygons=[room_polygon],
    )

    assert corridor_poly is not None
    assert not corridor_poly.is_empty
    # Corridor must not overlap room polygon interior
    assert not corridor_poly.intersects(room_polygon.buffer(-0.1))


def test_sanitization_empty_difference():
    """1. Empty difference -> None"""
    from shapely.geometry import box
    from app.services.realization.corridor_router import extract_valid_corridor_polygons

    empty_poly = Polygon()
    assert extract_valid_corridor_polygons(empty_poly, min_area=0.1) == []
    assert extract_valid_corridor_polygons(None, min_area=0.1) == []

    # Path completely covered by room polygon
    path = [(5.0, 5.0), (15.0, 5.0)]
    room = box(0.0, 0.0, 20.0, 20.0)
    res = CorridorPolygonGenerator.generate_corridor_polygons(
        paths=[path],
        corridor_width=3.5,
        legal_envelope=box(0.0, 0.0, 40.0, 40.0),
        room_polygons=[room],
    )
    assert res is None


def test_sanitization_normal_polygon_above_threshold():
    """2. Normal Polygon above threshold -> preserved"""
    from shapely.geometry import box
    from app.services.realization.corridor_router import extract_valid_corridor_polygons

    poly = box(0.0, 0.0, 10.0, 10.0)  # Area = 100.0 >= 0.1
    extracted = extract_valid_corridor_polygons(poly, min_area=0.1)
    assert len(extracted) == 1
    assert extracted[0].area == 100.0


def test_sanitization_polygon_below_threshold():
    """3. Polygon below threshold -> None / filtered out"""
    from shapely.geometry import box
    from app.services.realization.corridor_router import extract_valid_corridor_polygons

    tiny_poly = box(0.0, 0.0, 0.2, 0.2)  # Area = 0.04 < 0.1
    extracted = extract_valid_corridor_polygons(tiny_poly, min_area=0.1)
    assert len(extracted) == 0


def test_sanitization_multipolygon_one_tiny_component_removed():
    """4. MultiPolygon with one tiny component -> tiny component removed, valid preserved"""
    from shapely.geometry import MultiPolygon, box
    from app.services.realization.corridor_router import extract_valid_corridor_polygons

    poly_a = box(0.0, 0.0, 5.0, 4.0)      # Area = 20.0 (valid)
    poly_b = box(10.0, 10.0, 10.1, 10.2)  # Area = 0.02 (tiny sliver < 0.1)
    poly_c = box(20.0, 20.0, 25.0, 23.0)  # Area = 15.0 (valid)

    multi = MultiPolygon([poly_a, poly_b, poly_c])
    extracted = extract_valid_corridor_polygons(multi, min_area=0.1)

    assert len(extracted) == 2
    assert poly_a in extracted
    assert poly_c in extracted
    assert poly_b not in extracted


def test_sanitization_multipolygon_all_tiny_components():
    """5. MultiPolygon with all tiny components -> None"""
    from shapely.geometry import MultiPolygon, box
    from app.services.realization.corridor_router import extract_valid_corridor_polygons

    poly_b1 = box(10.0, 10.0, 10.1, 10.2)  # Area = 0.02
    poly_b2 = box(20.0, 20.0, 20.2, 20.2)  # Area = 0.04

    multi = MultiPolygon([poly_b1, poly_b2])
    extracted = extract_valid_corridor_polygons(multi, min_area=0.1)
    assert len(extracted) == 0


def test_sanitization_geometrycollection_mixed_types():
    """6. GeometryCollection containing Polygon, LineString, Point -> only valid Polygon retained"""
    from shapely.geometry import GeometryCollection, LineString, Point, box
    from app.services.realization.corridor_router import extract_valid_corridor_polygons

    poly_valid = box(0.0, 0.0, 4.0, 4.0)  # Area = 16.0
    poly_tiny = box(10.0, 10.0, 10.1, 10.2)  # Area = 0.02
    line_sliver = LineString([(0.0, 0.0), (5.0, 5.0)])
    point_sliver = Point(2.0, 2.0)

    gc = GeometryCollection([poly_valid, poly_tiny, line_sliver, point_sliver])
    extracted = extract_valid_corridor_polygons(gc, min_area=0.1)

    assert len(extracted) == 1
    assert extracted[0] == poly_valid


def test_sanitization_geometrycollection_only_0d_1d():
    """7. GeometryCollection containing only 0D/1D geometries -> None"""
    from shapely.geometry import GeometryCollection, LineString, MultiLineString, Point
    from app.services.realization.corridor_router import extract_valid_corridor_polygons

    gc = GeometryCollection([
        Point(1.0, 1.0),
        LineString([(0.0, 0.0), (10.0, 10.0)]),
        MultiLineString([[(1.0, 1.0), (2.0, 2.0)], [(3.0, 3.0), (4.0, 4.0)]]),
    ])
    extracted = extract_valid_corridor_polygons(gc, min_area=0.1)
    assert len(extracted) == 0


def test_sanitization_deterministic_repeated_execution():
    """8. Deterministic repeated execution"""
    from shapely.geometry import MultiPolygon, box
    from app.services.realization.corridor_router import extract_valid_corridor_polygons

    poly_a = box(0.0, 0.0, 5.0, 4.0)
    poly_b = box(10.0, 10.0, 10.1, 10.2)
    poly_c = box(20.0, 20.0, 25.0, 23.0)
    multi = MultiPolygon([poly_a, poly_b, poly_c])

    res1 = extract_valid_corridor_polygons(multi, min_area=0.1)
    res2 = extract_valid_corridor_polygons(multi, min_area=0.1)

    assert len(res1) == len(res2)
    assert [p.bounds for p in res1] == [p.bounds for p in res2]


def test_sanitization_existing_corridor_regression_fixture():
    """9. Existing corridor-routing regression fixture remains unchanged"""
    grid = DiscreteGridMatrix(
        plot_width=40.0,
        plot_depth=40.0,
        setbacks={"left": 0.0, "right": 0.0, "bottom": 0.0, "top": 0.0},
        resolution=0.5,
    )
    grid.mask_room_obstacle(10.0, 10.0, 30.0, 30.0)

    start_rc = grid.world_to_grid(5.0, 5.0)
    goal_rc = grid.world_to_grid(35.0, 35.0)
    path = AStarCorridorPathfinder.find_path(grid, start_rc, goal_rc)
    path_xy = [grid.grid_to_world(r, c) for r, c in path]

    poly = CorridorPolygonGenerator.generate_corridor_polygons(
        paths=[path_xy],
        corridor_width=3.5,
        legal_envelope=box(0.0, 0.0, 40.0, 40.0),
        room_polygons=[box(10.0, 10.0, 30.0, 30.0)],
    )
    assert poly is not None
    assert poly.area > 50.0  # Real corridor area is non-trivial


def test_sanitization_door_corridor_integration():
    """10. Existing door/corridor integration remains unchanged"""
    grid = DiscreteGridMatrix(
        plot_width=30.0,
        plot_depth=30.0,
        setbacks={"left": 2.0, "right": 2.0, "bottom": 2.0, "top": 2.0},
        resolution=0.5,
    )
    grid.mask_room_obstacle(5.0, 5.0, 15.0, 15.0)
    thresholds = DoorwayAnchorExtractor.extract_thresholds(
        grid, {"room_1": (5.0, 5.0, 15.0, 15.0)}, origin_xy=(2.0, 2.0)
    )
    paths = AStarCorridorPathfinder.route_circulation_tree(grid, (2.0, 2.0), thresholds)
    assert len(paths) == 1

    corridor = CorridorPolygonGenerator.generate_corridor_polygons(
        paths=paths,
        corridor_width=3.5,
        legal_envelope=box(2.0, 2.0, 28.0, 28.0),
        room_polygons=[box(5.0, 5.0, 15.0, 15.0)],
    )
    assert corridor is not None
    assert corridor.area >= CorridorPolygonGenerator.MIN_AREA_THRESHOLD

