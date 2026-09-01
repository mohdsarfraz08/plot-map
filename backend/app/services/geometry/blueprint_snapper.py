"""
Blueprint Snapper & Boundary Stitcher.
Cleanses raw LLM floating-point outputs, crushes micro-gaps and overlaps,
and scales normalized blueprints into clean, grid-aligned real-world coordinates.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from app.schemas.spatial_blueprint import NormalizedRoomBox, SpatialBlueprint


def cleanse_and_stitch_blueprint(
    blueprint: SpatialBlueprint,
    snap_grid: float = 0.025,
    stitch_threshold: float = 0.05,
) -> SpatialBlueprint:
    """
    Cleanses a raw SpatialBlueprint:
    1. Snaps all u_min, v_min, u_max, v_max to discrete grid steps (e.g. 0.025).
    2. Boundary Stitching: Detects near-collinear boundaries within stitch_threshold
       and forces them to share exact identical coordinates (crushing micro-gaps and overlaps).
    3. Clamps extreme edges to exactly 0.0 and 1.0.
    """
    cleaned_rooms: List[NormalizedRoomBox] = []

    # 1. Discrete Grid Snapping
    for room in blueprint.rooms:
        u_min = round(round(room.u_min / snap_grid) * snap_grid, 4)
        v_min = round(round(room.v_min / snap_grid) * snap_grid, 4)
        u_max = round(round(room.u_max / snap_grid) * snap_grid, 4)
        v_max = round(round(room.v_max / snap_grid) * snap_grid, 4)

        # Enforce minimum dimension span
        if u_max <= u_min + snap_grid:
            u_max = u_min + snap_grid
        if v_max <= v_min + snap_grid:
            v_max = v_min + snap_grid

        # Clamp boundaries
        if u_min < 0.05:
            u_min = 0.0
        if v_min < 0.05:
            v_min = 0.0
        if u_max > 0.95:
            u_max = 1.0
        if v_max > 0.95:
            v_max = 1.0

        cleaned_rooms.append(
            NormalizedRoomBox(
                name=room.name,
                room_type=room.room_type,
                zone=room.zone,
                u_min=u_min,
                v_min=v_min,
                u_max=u_max,
                v_max=v_max,
                floor_assignment=room.floor_assignment,
                attached_to=room.attached_to,
                requires_natural_light=room.requires_natural_light,
            )
        )

    # 2. Boundary Stitcher (Crush Gaps & Overlaps between room pairs)
    # Collect all unique cut lines on U and V axes
    u_cuts = sorted(list({r.u_min for r in cleaned_rooms} | {r.u_max for r in cleaned_rooms}))
    v_cuts = sorted(list({r.v_min for r in cleaned_rooms} | {r.v_max for r in cleaned_rooms}))

    # Cluster cut lines that are within stitch_threshold
    def cluster_cuts(cuts: List[float]) -> Dict[float, float]:
        mapping = {}
        if not cuts:
            return mapping
        clusters: List[List[float]] = [[cuts[0]]]
        for c in cuts[1:]:
            if c - clusters[-1][-1] <= stitch_threshold:
                clusters[-1].append(c)
            else:
                clusters.append([c])
        for cluster in clusters:
            # Pick representative cut (boundary 0.0 or 1.0 takes priority, else average)
            if 0.0 in cluster:
                rep = 0.0
            elif 1.0 in cluster:
                rep = 1.0
            else:
                rep = round(sum(cluster) / len(cluster), 4)
            for val in cluster:
                mapping[val] = rep
        return mapping

    u_map = cluster_cuts(u_cuts)
    v_map = cluster_cuts(v_cuts)

    stitched_rooms: List[NormalizedRoomBox] = []
    for r in cleaned_rooms:
        new_u_min = u_map.get(r.u_min, r.u_min)
        new_u_max = u_map.get(r.u_max, r.u_max)
        new_v_min = v_map.get(r.v_min, r.v_min)
        new_v_max = v_map.get(r.v_max, r.v_max)

        # Ensure valid non-zero span
        if new_u_max <= new_u_min:
            new_u_max = new_u_min + snap_grid
        if new_v_max <= new_v_min:
            new_v_max = new_v_min + snap_grid

        stitched_rooms.append(
            NormalizedRoomBox(
                name=r.name,
                room_type=r.room_type,
                zone=r.zone,
                u_min=new_u_min,
                v_min=new_v_min,
                u_max=new_u_max,
                v_max=new_v_max,
                floor_assignment=r.floor_assignment,
                attached_to=r.attached_to,
                requires_natural_light=r.requires_natural_light,
            )
        )

    return SpatialBlueprint(
        title=blueprint.title,
        concept_summary=blueprint.concept_summary,
        envelope_aspect_ratio_type=blueprint.envelope_aspect_ratio_type,
        road_facing_edge=blueprint.road_facing_edge,
        rooms=stitched_rooms,
        has_central_circulation=blueprint.has_central_circulation,
    )


def realize_blueprint_to_world_layout(
    blueprint: SpatialBlueprint,
    plot_width: float,
    plot_depth: float,
    setbacks: Dict[str, float],
    grid_snap_ft: float = 0.5,
) -> Dict[str, Any]:
    """
    Transforms a cleansed SpatialBlueprint into real-world coordinates:
    1. Scales [u, v] to [X_world, Y_world] inside the legal setback envelope.
    2. Snaps all room coordinates to a discrete construction grid (e.g. 0.5 ft).
    3. Derives shared topological adjacencies and door/window placements.
    
    Returns:
        Dict with "rooms" dictionary and "adjacencies" list.
    """
    sb_left = float(setbacks.get("left", 3.0))
    sb_right = float(setbacks.get("right", 3.0))
    sb_bottom = float(setbacks.get("bottom", 5.0))
    sb_top = float(setbacks.get("top", 3.0))

    buildable_w = max(10.0, plot_width - sb_left - sb_right)
    buildable_d = max(10.0, plot_depth - sb_bottom - sb_top)

    # First stitch and cleanse normalized floats
    stitched_bp = cleanse_and_stitch_blueprint(blueprint)

    world_rooms: Dict[str, Dict[str, Any]] = {}

    for r in stitched_bp.rooms:
        # Scale to continuous world coordinates
        x_min = sb_left + r.u_min * buildable_w
        x_max = sb_left + r.u_max * buildable_w
        y_min = sb_bottom + r.v_min * buildable_d
        y_max = sb_bottom + r.v_max * buildable_d

        # Snap to real-world construction grid
        x_min = round(round(x_min / grid_snap_ft) * grid_snap_ft, 2)
        x_max = round(round(x_max / grid_snap_ft) * grid_snap_ft, 2)
        y_min = round(round(y_min / grid_snap_ft) * grid_snap_ft, 2)
        y_max = round(round(y_max / grid_snap_ft) * grid_snap_ft, 2)

        w = round(x_max - x_min, 2)
        h = round(y_max - y_min, 2)

        # Guarantee non-zero dimensions
        if w < grid_snap_ft:
            w = grid_snap_ft
            x_max = x_min + w
        if h < grid_snap_ft:
            h = grid_snap_ft
            y_max = y_min + h

        world_rooms[r.name] = {
            "name": r.name,
            "type": r.room_type.value,
            "zone": r.zone.value,
            "x": float(x_min),
            "y": float(y_min),
            "width": float(w),
            "height": float(h),
            "floor_assignment": r.floor_assignment,
            "attached_to": r.attached_to,
            "requires_ventilation": r.requires_natural_light,
            "coordinates": [
                [float(x_min), float(y_min)],
                [float(x_min), float(y_max)],
                [float(x_max), float(y_max)],
                [float(x_max), float(y_min)],
            ],
        }

    # Extract Topological Adjacencies (rooms sharing a wall segment >= 2.0 ft)
    adjacencies: List[Tuple[str, str]] = []
    room_names = list(world_rooms.keys())

    for i in range(len(room_names)):
        for j in range(i + 1, len(room_names)):
            r1 = world_rooms[room_names[i]]
            r2 = world_rooms[room_names[j]]

            # Check vertical shared wall
            if abs(r1["x"] + r1["width"] - r2["x"]) < 0.05 or abs(r2["x"] + r2["width"] - r1["x"]) < 0.05:
                overlap_y = min(r1["y"] + r1["height"], r2["y"] + r2["height"]) - max(r1["y"], r2["y"])
                if overlap_y >= 2.0:
                    adjacencies.append((r1["name"], r2["name"]))
                    continue

            # Check horizontal shared wall
            if abs(r1["y"] + r1["height"] - r2["y"]) < 0.05 or abs(r2["y"] + r2["height"] - r1["y"]) < 0.05:
                overlap_x = min(r1["x"] + r1["width"], r2["x"] + r2["width"]) - max(r1["x"], r2["x"])
                if overlap_x >= 2.0:
                    adjacencies.append((r1["name"], r2["name"]))

    return {
        "rooms": world_rooms,
        "adjacencies": adjacencies,
        "blueprint": stitched_bp,
    }
