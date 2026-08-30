"""
Topological Building Model (TBM) & Canonical Wall Deduplication Engine (Stage 3B.4D).

Uses Shapely/GEOS planar line noding and boundary polygon decomposition to:
1. Deconstruct all room and corridor polygons into atomic 1D boundary segments.
2. Deduplicate shared partition centerlines via GEOS noding (unary_union of boundary LineStrings).
3. Determine topological room separation (SEPARATES) and boundary containment (BOUNDS)
   via robust normal-vector spatial probing.
4. Eliminate Double-Wall overlaps, micro-gaps, and Z-fighting in downstream CAD/3D engines.

STRICT BOUNDARY RULES:
- Pure geometry/topology realization only.
- Centralized constants for tolerances, offsets, and wall thicknesses.
- Deterministic lexicographic coordinate ordering.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set, Tuple

from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
    box,
)
from shapely.ops import unary_union

from app.core.tbm import (
    Beam,
    Building,
    Column,
    Floor,
    Junction,
    Opening,
    Plot,
    Room,
    Stair,
    Wall,
)


# ============================================================================
# Centralized Geometry & Topology Constants
# ============================================================================
MIN_WALL_LENGTH: float = 0.01                # Minimum valid wall length in feet
PROBE_OFFSET_DISTANCE: float = 0.05          # Distance along normal vector for adjacency probing (in feet)
COORDINATE_PRECISION_DECIMALS: int = 4       # Precision for deterministic vertex rounding
GRID_SNAP_RESOLUTION: float = 0.5            # Standard architectural snap resolution (0.5 ft)
EXTERIOR_WALL_THICKNESS: float = 0.75        # Exterior structural wall thickness (9 inches in feet)
PARTITION_WALL_THICKNESS: float = 0.5        # Interior shared partition wall thickness (6 inches in feet)
MIN_DOOR_WALL_LENGTH: float = 3.5            # Minimum wall length to host a standard 3ft door
MIN_WINDOW_WALL_LENGTH: float = 4.5          # Minimum wall length to host a standard 4ft window


def snap_coord(c: float, tolerance: float = 0.05) -> float:
    """Snaps a coordinate to clean grid alignment based on resolution."""
    return round(c * 2) / 2  # default snap to 0.5 ft grid


def round_pt(pt: tuple[float, float], decimals: int = COORDINATE_PRECISION_DECIMALS) -> tuple[float, float]:
    """Deterministically round a 2D point tuple."""
    return (round(float(pt[0]), decimals), round(float(pt[1]), decimals))


def extract_polygon_boundary_lines(
    room_polygons: dict[str, Polygon | MultiPolygon],
) -> list[LineString]:
    """
    Pure function: Extracts all boundary LineStrings from room and corridor polygons,
    including exterior boundaries and interior hole rings for Polygon and MultiPolygon entities.
    """
    boundary_lines: list[LineString] = []

    for r_poly in room_polygons.values():
        if r_poly is None or r_poly.is_empty or r_poly.area < MIN_WALL_LENGTH:
            continue

        if isinstance(r_poly, Polygon):
            boundary_lines.append(r_poly.exterior)
            for interior in r_poly.interiors:
                boundary_lines.append(interior)
        elif isinstance(r_poly, MultiPolygon):
            for poly in r_poly.geoms:
                if isinstance(poly, Polygon) and not poly.is_empty and poly.area >= MIN_WALL_LENGTH:
                    boundary_lines.append(poly.exterior)
                    for interior in poly.interiors:
                        boundary_lines.append(interior)

    return boundary_lines


def node_boundary_lines(boundary_lines: list[LineString]) -> list[LineString]:
    """
    Pure function: Uses Shapely/GEOS unary_union to perform planar line noding.
    Splits overlapping/crossing boundary lines at all intersection points and
    eliminates exact duplicate coincident segments.
    """
    if not boundary_lines:
        return []

    noded_geom = unary_union(boundary_lines)

    segments: list[LineString] = []
    if isinstance(noded_geom, LineString):
        segments = [noded_geom]
    elif isinstance(noded_geom, MultiLineString):
        segments = list(noded_geom.geoms)
    elif isinstance(noded_geom, GeometryCollection):
        for g in noded_geom.geoms:
            if isinstance(g, LineString):
                segments.append(g)
            elif isinstance(g, MultiLineString):
                segments.extend(list(g.geoms))

    return segments


def classify_segment_adjacency(
    p1: tuple[float, float],
    p2: tuple[float, float],
    room_polygons: dict[str, Polygon | MultiPolygon],
    probe_distance: float = PROBE_OFFSET_DISTANCE,
) -> tuple[str, str]:
    """
    Pure function: Determines the adjacent spatial entity on each side of a 1D segment
    using normal-vector spatial probing.
    
    Returns:
        (room_a_name, room_b_name) where room_a != room_b.
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < MIN_WALL_LENGTH:
        return ("", "")

    # Tangent and normal unit vectors
    tx, ty = dx / length, dy / length
    nx, ny = -ty, tx

    # Midpoint of segment
    mx = (p1[0] + p2[0]) / 2.0
    my = (p1[1] + p2[1]) / 2.0

    # Probe points offset slightly along normal vector on left and right
    probe_left = Point(mx + nx * probe_distance, my + ny * probe_distance)
    probe_right = Point(mx - nx * probe_distance, my - ny * probe_distance)

    left_rooms: list[str] = []
    right_rooms: list[str] = []

    # Probing with slight buffer tolerance to handle exact edge alignment
    for r_name, r_poly in room_polygons.items():
        if r_poly.contains(probe_left) or r_poly.touches(probe_left):
            left_rooms.append(r_name)
        if r_poly.contains(probe_right) or r_poly.touches(probe_right):
            right_rooms.append(r_name)

    room_a = left_rooms[0] if left_rooms else ""
    room_b = right_rooms[0] if right_rooms else ""

    # Prevent self-adjacency
    if room_a == room_b:
        room_b = ""

    # For exterior walls (only one adjacent entity), canonicalize to room_a
    if not room_a and room_b:
        room_a = room_b
        room_b = ""

    return (room_a, room_b)


def extract_atomic_wall_segments(
    room_polygons: dict[str, Polygon | MultiPolygon],
) -> list[tuple[tuple[float, float], tuple[float, float], str, str]]:
    """
    Extracts canonical, non-overlapping, noded 1D wall segments from a collection of
    room and corridor polygons using GEOS line noding and normal-vector probing.

    Returns:
        list of (p1, p2, room_a_name, room_b_name) in deterministic coordinate order.
    """
    if not room_polygons:
        return []

    # 1. Extract boundary lines
    boundary_lines = extract_polygon_boundary_lines(room_polygons)
    if not boundary_lines:
        return []

    # 2. Planar line noding via GEOS unary_union
    segments = node_boundary_lines(boundary_lines)

    canonical_walls: list[tuple[tuple[float, float], tuple[float, float], str, str]] = []
    seen_segments: set[tuple[tuple[float, float], tuple[float, float]]] = set()

    for seg in segments:
        coords = list(seg.coords)
        if len(coords) < 2:
            continue

        for i in range(len(coords) - 1):
            p1 = round_pt(coords[i])
            p2 = round_pt(coords[i + 1])

            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            length = math.hypot(dx, dy)
            if length < MIN_WALL_LENGTH:
                continue

            # Deterministic canonical orientation: p1 <= p2 lexicographically
            if p1 > p2:
                p1, p2 = p2, p1

            seg_key = (p1, p2)
            if seg_key in seen_segments:
                continue
            seen_segments.add(seg_key)

            # Classify room adjacency
            room_a, room_b = classify_segment_adjacency(p1, p2, room_polygons)

            # Only retain segments that bound at least one valid room/corridor entity
            if room_a or room_b:
                canonical_walls.append((p1, p2, room_a, room_b))

    # Deterministic sorting of all canonical wall segments
    canonical_walls.sort(key=lambda item: (item[0], item[1]))
    return canonical_walls


def build_tbm_from_layout(payload: Dict[str, Any], compiled_result: Dict[str, Any]) -> Building:
    """
    Constructs a complete Topological Building Model (TBM) from the compiled layout
    with canonical GEOS wall deduplication and opening attachment.
    """
    # 1. Parse and build Plot
    plot_cfg = payload.get("plot", {})
    width = float(plot_cfg.get("width", 40.0))
    depth = float(plot_cfg.get("depth", 40.0))
    setbacks = payload.get("setbacks", {"left": 0.0, "right": 0.0, "bottom": 0.0, "top": 0.0})

    boundary_coords = [(0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)]
    plot = Plot(
        id="plot_0",
        width=width,
        depth=depth,
        boundary_coords=boundary_coords,
        road_edge=payload.get("road_edge", "bottom"),
        setbacks=setbacks,
    )

    building = Building(
        id="building_0",
        plot=plot,
        name=payload.get("project_name", "Uncharted CAD Drawing"),
    )

    floors_data = compiled_result.get("floors", {})
    if not floors_data:
        floors_data = {
            "1": {
                "layout": compiled_result.get("layout", {}),
                "geometry": compiled_result.get("geometry", {}),
            }
        }

    for floor_idx_str, floor_content in floors_data.items():
        floor_level = int(floor_idx_str)
        floor_id = f"floor_{floor_level}"

        floor = Floor(
            id=floor_id,
            floor_level=floor_level,
            elevation=(floor_level - 1) * 10.0,
            height=10.0,
        )

        layout = floor_content.get("layout", {})
        rooms_map: Dict[str, Room] = {}
        room_polygons: Dict[str, Polygon | MultiPolygon] = {}

        # 2. Extract Room Entities & Polygons (handles both box dimensions and arbitrary polygons)
        for r_name, r_data in layout.items():
            r_id = f"{floor_id}_room_{r_name.lower().replace(' ', '_')}"

            # Support explicit polygon or rectangular box
            if "polygon" in r_data and isinstance(r_data["polygon"], (Polygon, MultiPolygon)):
                room_poly = r_data["polygon"]
                area = room_poly.area
            elif "polygon" in r_data and isinstance(r_data["polygon"], (list, tuple)) and len(r_data["polygon"]) >= 3:
                room_poly = Polygon(r_data["polygon"])
                area = room_poly.area
            else:
                w = float(r_data.get("width", 10.0))
                h = float(r_data.get("height", 10.0))
                x = float(r_data.get("x", 0.0))
                y = float(r_data.get("y", 0.0))
                room_poly = box(x, y, x + w, y + h)
                area = w * h

            room = Room(
                id=r_id,
                name=r_name,
                type=r_data.get("type", "Living Room"),
                floor_id=floor_id,
                min_area=area,
                target_area=area,
            )
            rooms_map[r_name] = room
            floor.room_ids.append(r_id)
            building.rooms[r_id] = room
            room_polygons[r_name] = room_poly

        # 3. Extract Canonical Deduplicated Wall Segments using GEOS Line Noding
        canonical_segments = extract_atomic_wall_segments(room_polygons)

        # 4. Collect & Sort Unique Junction Points Deterministically
        unique_points: Set[Tuple[float, float]] = set()
        for p1, p2, _, _ in canonical_segments:
            unique_points.add(p1)
            unique_points.add(p2)

        sorted_points = sorted(list(unique_points), key=lambda pt: (pt[0], pt[1]))
        junction_coords_to_id: Dict[Tuple[float, float], str] = {}
        junctions_map: Dict[str, Junction] = {}

        for j_idx, pt in enumerate(sorted_points):
            j_id = f"{floor_id}_j_{j_idx}"
            junction = Junction(id=j_id, x=pt[0], y=pt[1], floor_id=floor_id)
            junctions_map[j_id] = junction
            junction_coords_to_id[pt] = j_id
            floor.junction_ids.append(j_id)
            building.junctions[j_id] = junction

        # 5. Build Canonical Wall Entities
        walls_map: Dict[str, Wall] = {}

        for w_idx, (p1, p2, r_a, r_b) in enumerate(canonical_segments):
            w_id = f"{floor_id}_w_{w_idx}"

            # Thickness: Exterior = 0.75 ft, Partition = 0.5 ft
            thickness = PARTITION_WALL_THICKNESS if (r_a and r_b) else EXTERIOR_WALL_THICKNESS

            wall = Wall(
                id=w_id,
                floor_id=floor_id,
                thickness=thickness,
                start_junction_id=junction_coords_to_id[p1],
                end_junction_id=junction_coords_to_id[p2],
                room_a_id=rooms_map[r_a].id if r_a in rooms_map else "",
                room_b_id=rooms_map[r_b].id if r_b in rooms_map else "",
            )
            walls_map[w_id] = wall
            floor.wall_ids.append(w_id)
            building.walls[w_id] = wall

            # Link junctions to wall
            junctions_map[wall.start_junction_id].connected_wall_ids.append(w_id)
            junctions_map[wall.end_junction_id].connected_wall_ids.append(w_id)

            # Link rooms to bounded wall
            if r_a in rooms_map:
                rooms_map[r_a].bounded_by_wall_ids.append(w_id)
            if r_b in rooms_map:
                rooms_map[r_b].bounded_by_wall_ids.append(w_id)

        # 6. Place Door and Window Openings on Canonical Walls
        opening_counter = 0
        for w_id, wall in sorted(walls_map.items(), key=lambda item: item[0]):
            j1 = building.junctions.get(wall.start_junction_id)
            j2 = building.junctions.get(wall.end_junction_id)
            if not j1 or not j2:
                continue

            wall_length = math.hypot(j2.x - j1.x, j2.y - j1.y)

            # Doors on interior separating partition walls
            if wall.room_a_id and wall.room_b_id:
                if wall_length >= MIN_DOOR_WALL_LENGTH:
                    o_id = f"{floor_id}_op_{opening_counter}"
                    opening_counter += 1
                    opening = Opening(
                        id=o_id,
                        type="Door",
                        wall_id=w_id,
                        width=3.0,
                        height=7.0,
                        position_offset=round(wall_length / 2.0, 2),
                        connects_room_a_id=wall.room_a_id,
                        connects_room_b_id=wall.room_b_id,
                    )
                    wall.hosted_opening_ids.append(o_id)
                    floor.opening_ids.append(o_id)
                    building.openings[o_id] = opening
            # Windows on exterior perimeter walls
            elif (wall.room_a_id or wall.room_b_id) and wall_length >= MIN_WINDOW_WALL_LENGTH:
                o_id = f"{floor_id}_op_{opening_counter}"
                opening_counter += 1
                opening = Opening(
                    id=o_id,
                    type="Window",
                    wall_id=w_id,
                    width=4.0,
                    height=4.0,
                    sill_height=3.0,
                    position_offset=round(wall_length / 2.0, 2),
                )
                wall.hosted_opening_ids.append(o_id)
                floor.opening_ids.append(o_id)
                building.openings[o_id] = opening

        # Register floor inside building
        building.floor_ids.append(floor_id)
        building.floors[floor_id] = floor

    return building
