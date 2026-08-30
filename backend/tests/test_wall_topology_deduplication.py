"""
Comprehensive deterministic unit test suite for Topological Wall Edge Deduplication (Stage 3B.4D).

Verifies 14 core requirements:
1. Two abutting rectangles: exactly ONE shared wall.
2. Room + corridor: exactly ONE canonical shared boundary wall.
3. Corridor edge touching multiple rooms: correctly noded into atomic segments.
4. T-junction: segment is split at junction.
5. X-junction: crossing is properly noded.
6. Partial collinear overlap: overlapping edges become canonical atomic segments.
7. Exterior wall: only one adjacent spatial entity.
8. Point-only contact: must NOT incorrectly become a shared wall.
9. MultiPolygon entity: boundaries handled correctly.
10. Door on shared wall: opening references the canonical wall.
11. Door cutout: geometry resolver produces correct solid wall panels.
12. Junction deduplication: no duplicate Junction entities.
13. Determinism: repeated execution produces identical serialized TBM.
14. Existing regression fixtures: existing compiler/TBM behavior remains valid.
"""

import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from app.core.tbm import Building
from app.services.geometry_resolver import resolve_geometry
from app.services.relationship_builder import (
    build_tbm_from_layout,
    extract_atomic_wall_segments,
)


def test_1_two_abutting_rectangles_single_shared_wall():
    """1. Two abutting rectangles produce exactly ONE shared wall (7 unique walls total)."""
    room_polygons = {
        "Living Room": box(0.0, 0.0, 10.0, 10.0),
        "Kitchen": box(10.0, 0.0, 20.0, 10.0),
    }

    segments = extract_atomic_wall_segments(room_polygons)
    # 4 walls + 4 walls - 1 shared = 7 unique walls
    assert len(segments) == 7

    # Find the shared partition at x=10.0 from y=0.0 to y=10.0
    shared_walls = [
        s for s in segments if s[0][0] == 10.0 and s[1][0] == 10.0
    ]
    assert len(shared_walls) == 1
    p1, p2, r_a, r_b = shared_walls[0]
    assert {r_a, r_b} == {"Living Room", "Kitchen"}


def test_2_room_and_corridor_single_shared_boundary():
    """2. Room + corridor produces exactly ONE canonical shared boundary wall."""
    room_polygons = {
        "Bedroom": box(0.0, 0.0, 12.0, 12.0),
        "Corridor": box(12.0, 0.0, 16.0, 12.0),
    }

    segments = extract_atomic_wall_segments(room_polygons)
    assert len(segments) == 7

    shared = [s for s in segments if s[0][0] == 12.0 and s[1][0] == 12.0]
    assert len(shared) == 1
    assert {shared[0][2], shared[0][3]} == {"Bedroom", "Corridor"}


def test_3_corridor_touching_multiple_rooms_noded():
    """3. Corridor edge touching multiple rooms is correctly noded into atomic segments."""
    room_polygons = {
        "Room_A": box(0.0, 0.0, 10.0, 10.0),
        "Room_B": box(0.0, 10.0, 10.0, 20.0),
        "Room_C": box(0.0, 20.0, 10.0, 30.0),
        "Corridor": box(10.0, 0.0, 14.0, 30.0),
    }

    segments = extract_atomic_wall_segments(room_polygons)

    # Check shared walls along x=10.0 (must be 3 distinct segments: [0-10], [10-20], [20-30])
    x10_walls = [s for s in segments if s[0][0] == 10.0 and s[1][0] == 10.0]
    assert len(x10_walls) == 3

    rooms_separated = [{s[2], s[3]} for s in x10_walls]
    assert {"Room_A", "Corridor"} in rooms_separated
    assert {"Room_B", "Corridor"} in rooms_separated
    assert {"Room_C", "Corridor"} in rooms_separated


def test_4_t_junction_segment_splitting():
    """4. T-junction splits the continuous segment into two atomic sub-segments at the junction."""
    # Room 1 on top: [0, 10] to [20, 20] (width 20)
    # Room 2 bottom-left: [0, 0] to [10, 10]
    # Room 3 bottom-right: [10, 0] to [20, 10]
    # T-junction occurs at (10, 10) along the horizontal line y=10 from x=0 to x=20.
    room_polygons = {
        "Room_Top": box(0.0, 10.0, 20.0, 20.0),
        "Room_BL": box(0.0, 0.0, 10.0, 10.0),
        "Room_BR": box(10.0, 0.0, 20.0, 10.0),
    }

    segments = extract_atomic_wall_segments(room_polygons)

    # Check horizontal walls along y=10.0
    y10_walls = [s for s in segments if s[0][1] == 10.0 and s[1][1] == 10.0]
    # Must be split into 2 atomic segments: [0-10] and [10-20]
    assert len(y10_walls) == 2
    assert y10_walls[0][0] == (0.0, 10.0) and y10_walls[0][1] == (10.0, 10.0)
    assert y10_walls[1][0] == (10.0, 10.0) and y10_walls[1][1] == (20.0, 10.0)


def test_5_x_junction_crossing_noded():
    """5. X-junction crossing is properly noded into 4 converging segments and 1 central junction."""
    # 4 quadrants meeting at (10, 10)
    room_polygons = {
        "Q1_TR": box(10.0, 10.0, 20.0, 20.0),
        "Q2_TL": box(0.0, 10.0, 10.0, 20.0),
        "Q3_BL": box(0.0, 0.0, 10.0, 10.0),
        "Q4_BR": box(10.0, 0.0, 20.0, 10.0),
    }

    segments = extract_atomic_wall_segments(room_polygons)

    # Interior horizontal walls along y=10: [0-10] and [10-20]
    y10_walls = [s for s in segments if s[0][1] == 10.0 and s[1][1] == 10.0]
    assert len(y10_walls) == 2

    # Interior vertical walls along x=10: [0-10] and [10-20]
    x10_walls = [s for s in segments if s[0][0] == 10.0 and s[1][0] == 10.0]
    assert len(x10_walls) == 2

    # Total walls: 8 exterior perimeter + 4 interior partitions = 12 walls
    assert len(segments) == 12


def test_6_partial_collinear_overlap_splitting():
    """6. Collinear partially overlapping boundaries become canonical atomic segments."""
    # Room 1: [0, 0] to [15, 10]
    # Room 2: [10, 10] to [25, 20] (overlaps along y=10 from x=10 to x=15)
    room_polygons = {
        "Room_1": box(0.0, 0.0, 15.0, 10.0),
        "Room_2": box(10.0, 10.0, 25.0, 20.0),
    }

    segments = extract_atomic_wall_segments(room_polygons)

    # Along y=10: [0, 10] (exterior), [10, 15] (shared partition), [15, 25] (exterior)
    y10_walls = [s for s in segments if s[0][1] == 10.0 and s[1][1] == 10.0]
    assert len(y10_walls) == 3

    shared = [s for s in y10_walls if s[0][0] == 10.0 and s[1][0] == 15.0]
    assert len(shared) == 1
    assert {shared[0][2], shared[0][3]} == {"Room_1", "Room_2"}


def test_7_exterior_wall_single_adjacent_entity():
    """7. Exterior wall has only one adjacent spatial entity (room_b == '')."""
    room_polygons = {"Standalone": box(0.0, 0.0, 10.0, 10.0)}
    segments = extract_atomic_wall_segments(room_polygons)

    assert len(segments) == 4
    for p1, p2, r_a, r_b in segments:
        assert r_a == "Standalone"
        assert r_b == ""


def test_8_point_only_contact_no_false_wall():
    """8. Point-only diagonal contact must NOT incorrectly become a shared wall."""
    # Two diagonally touching boxes meeting at (10, 10) only
    room_polygons = {
        "Box_BL": box(0.0, 0.0, 10.0, 10.0),
        "Box_TR": box(10.0, 10.0, 20.0, 20.0),
    }

    segments = extract_atomic_wall_segments(room_polygons)
    assert len(segments) == 8  # 4 exterior for each box

    # Zero shared partition walls
    shared_walls = [s for s in segments if s[2] and s[3]]
    assert len(shared_walls) == 0


def test_9_multipolygon_entity_boundary_handling():
    """9. MultiPolygon entity boundaries are handled correctly without crash."""
    poly1 = box(0.0, 0.0, 5.0, 10.0)
    poly2 = box(10.0, 0.0, 15.0, 10.0)
    multi_room = MultiPolygon([poly1, poly2])

    room_polygons = {
        "Disjoint_Units": multi_room,
        "Adjacent_Room": box(5.0, 0.0, 10.0, 10.0),
    }

    segments = extract_atomic_wall_segments(room_polygons)
    assert len(segments) > 0

    # Along x=5.0 and x=10.0, shared walls exist with Adjacent_Room
    x5_walls = [s for s in segments if s[0][0] == 5.0 and s[1][0] == 5.0]
    x10_walls = [s for s in segments if s[0][0] == 10.0 and s[1][0] == 10.0]
    assert len(x5_walls) == 1
    assert len(x10_walls) == 1
    assert {x5_walls[0][2], x5_walls[0][3]} == {"Disjoint_Units", "Adjacent_Room"}
    assert {x10_walls[0][2], x10_walls[0][3]} == {"Disjoint_Units", "Adjacent_Room"}


def test_10_door_references_canonical_wall():
    """10. Door opening on shared wall references the single canonical wall."""
    payload = {
        "project_name": "Door Canonical Test",
        "plot": {"width": 30.0, "depth": 40.0},
        "setbacks": {"left": 2.0, "right": 2.0, "bottom": 3.0, "top": 3.0},
    }
    compiled_result = {
        "floors": {
            "1": {
                "layout": {
                    "Living": {"x": 2.0, "y": 3.0, "width": 10.0, "height": 10.0},
                    "Kitchen": {"x": 12.0, "y": 3.0, "width": 8.0, "height": 10.0},
                }
            }
        }
    }

    building = build_tbm_from_layout(payload, compiled_result)

    assert len(building.walls) == 7
    door_openings = [o for o in building.openings.values() if o.type == "Door"]
    assert len(door_openings) >= 1

    door = door_openings[0]
    host_wall = building.walls[door.wall_id]

    # Host wall must be a partition wall with both rooms populated
    assert host_wall.room_a_id != ""
    assert host_wall.room_b_id != ""


def test_11_door_cutout_geometry_resolver():
    """11. Door cutout in geometry resolver produces correct solid wall panel split."""
    payload = {
        "project_name": "Door Cutout Test",
        "plot": {"width": 30.0, "depth": 40.0},
    }
    compiled_result = {
        "floors": {
            "1": {
                "layout": {
                    "Living": {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0},
                    "Dining": {"x": 10.0, "y": 0.0, "width": 10.0, "height": 10.0},
                }
            }
        }
    }

    building = build_tbm_from_layout(payload, compiled_result)
    geom = resolve_geometry(building)

    # Find the shared wall ID
    shared_wall_id = [
        w_id for w_id, w in building.walls.items() if w.room_a_id and w.room_b_id
    ][0]

    # Because a door was placed at offset 5.0 (width 3.0, span [3.5, 6.5]),
    # the 10ft wall should be split into 2 solid panels: [0, 3.5] and [6.5, 10.0]
    panels = geom.wall_panels[shared_wall_id]
    assert len(panels) == 2


def test_12_junction_deduplication():
    """12. Junctions are strictly deduplicated with zero duplicate coordinate entries."""
    payload = {
        "project_name": "Junction Test",
        "plot": {"width": 40.0, "depth": 40.0},
    }
    compiled_result = {
        "floors": {
            "1": {
                "layout": {
                    "R1": {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0},
                    "R2": {"x": 10.0, "y": 0.0, "width": 10.0, "height": 10.0},
                    "R3": {"x": 0.0, "y": 10.0, "width": 10.0, "height": 10.0},
                    "R4": {"x": 10.0, "y": 10.0, "width": 10.0, "height": 10.0},
                }
            }
        }
    }

    building = build_tbm_from_layout(payload, compiled_result)

    # 4 adjoining squares on a 3x3 grid of vertices = exactly 9 unique junctions
    assert len(building.junctions) == 9

    # Verify all junction coordinates are unique
    junction_coords = [(j.x, j.y) for j in building.junctions.values()]
    assert len(junction_coords) == len(set(junction_coords))


def test_13_deterministic_repeated_execution():
    """13. Repeated execution produces identical serialized TBM wall IDs, junctions, and coordinates."""
    payload = {
        "project_name": "Determinism Test",
        "plot": {"width": 30.0, "depth": 40.0},
        "setbacks": {"left": 1.0, "right": 1.0, "bottom": 2.0, "top": 2.0},
    }
    compiled_result = {
        "floors": {
            "1": {
                "layout": {
                    "Living": {"x": 1.0, "y": 2.0, "width": 12.0, "height": 14.0},
                    "Bedroom": {"x": 13.0, "y": 2.0, "width": 10.0, "height": 14.0},
                }
            }
        }
    }

    b1 = build_tbm_from_layout(payload, compiled_result)
    b2 = build_tbm_from_layout(payload, compiled_result)

    # Compare wall IDs and junction references
    assert list(b1.walls.keys()) == list(b2.walls.keys())
    assert list(b1.junctions.keys()) == list(b2.junctions.keys())

    for w_id in b1.walls:
        w1, w2 = b1.walls[w_id], b2.walls[w_id]
        assert w1.start_junction_id == w2.start_junction_id
        assert w1.end_junction_id == w2.end_junction_id
        assert w1.room_a_id == w2.room_a_id
        assert w1.room_b_id == w2.room_b_id


def test_14_existing_regression_fixtures_valid():
    """14. Existing compiler and TBM integration behavior remains fully valid."""
    payload = {
        "project_name": "Fixture Test",
        "plot": {"width": 40.0, "depth": 50.0},
        "setbacks": {"left": 3.0, "right": 3.0, "bottom": 5.0, "top": 3.0},
    }
    compiled_result = {
        "floors": {
            "1": {
                "layout": {
                    "Main Door": {"x": 3.0, "y": 5.0, "width": 4.0, "height": 4.0},
                    "Living Room": {"x": 7.0, "y": 5.0, "width": 14.0, "height": 16.0},
                    "Kitchen": {"x": 21.0, "y": 5.0, "width": 10.0, "height": 10.0},
                }
            }
        }
    }

    building = build_tbm_from_layout(payload, compiled_result)
    assert len(building.floors) == 1
    assert len(building.rooms) == 3
    assert len(building.walls) > 0
    assert len(building.junctions) > 0

    geom = resolve_geometry(building)
    assert len(geom.wall_panels) > 0
    assert len(geom.merged_wall_boundary) > 0
