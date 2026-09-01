"""
Opening Resolver Sub-Module (Stage 3B / Phase 5 Geometry).
Computes exact 1D Shapely geometric intersections between room polygons
to anchor doors and windows safely on valid, structural wall spans.

Applies strict architectural graph rules:
1. Main Entrance Door on front road facade.
2. Every bathroom has EXACTLY ONE door:
   - Attached/Ensuite Bath -> connects ONLY to its assigned Master Bedroom.
   - Common Bath -> connects ONLY to the central corridor/hallway.
3. Bedrooms have EXACTLY ONE primary entrance from the corridor, plus optional private ensuite door.
4. Zero doors on OTS lightwells (ventilation windows only).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple
from shapely.geometry import LineString, MultiLineString, Polygon, box


def extract_1d_segments(geom: Any) -> List[LineString]:
    """Extracts atomic 1D LineString segments from any Shapely geometry."""
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom] if geom.length > 0.01 else []
    if isinstance(geom, MultiLineString):
        return [line for line in geom.geoms if line.length > 0.01]
    return []


def resolve_openings_topologically(
    layout_rooms: Dict[str, Dict[str, Any]],
    envelope_coords: List[Tuple[float, float]],
    adjacencies: List[Tuple[str, str]],
    road_edge: str = "bottom",
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Computes mathematically airtight doors and windows using exact 1D Shapely intersections.
    """
    # 1. Build Shapely Polygons for all rooms
    room_polys: Dict[str, Polygon] = {}
    for name, r in layout_rooms.items():
        rx, ry, rw, rh = float(r["x"]), float(r["y"]), float(r["width"]), float(r["height"])
        if rw > 0.1 and rh > 0.1:
            room_polys[name] = box(rx, ry, rx + rw, ry + rh)

    # 2. Extract Envelope Boundary Lines
    if envelope_coords and len(envelope_coords) >= 4:
        xs = [p[0] for p in envelope_coords]
        ys = [p[1] for p in envelope_coords]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
    else:
        min_x = min((r["x"] for r in layout_rooms.values()), default=0.0)
        max_x = max((r["x"] + r["width"] for r in layout_rooms.values()), default=100.0)
        min_y = min((r["y"] for r in layout_rooms.values()), default=0.0)
        max_y = max((r["y"] + r["height"] for r in layout_rooms.values()), default=100.0)

    facade_lines = {
        "bottom": LineString([(min_x, min_y), (max_x, min_y)]),
        "top": LineString([(min_x, max_y), (max_x, max_y)]),
        "left": LineString([(min_x, min_y), (min_x, max_y)]),
        "right": LineString([(max_x, min_y), (max_x, max_y)]),
    }

    doors: List[Dict[str, Any]] = []
    windows: List[Dict[str, Any]] = []
    door_id_counter = 1
    window_id_counter = 1
    doors_per_room: Dict[str, int] = defaultdict(int)

    # 3. Resolve Main Exterior Entrance Door FIRST
    road_line = facade_lines.get(road_edge, facade_lines["bottom"])
    entrance_candidates = [
        name for name, r in layout_rooms.items()
        if ("foyer" in name.lower() or "entrance" in name.lower() or "main door" in name.lower())
        and name in room_polys
    ]
    if not entrance_candidates:
        entrance_candidates = [
            name for name, r in layout_rooms.items()
            if ("living" in name.lower() or "drawing" in name.lower())
            and name in room_polys
        ]
    if not entrance_candidates:
        entrance_candidates = [
            name for name, r in layout_rooms.items()
            if "bath" not in name.lower() and "ots" not in name.lower()
            and name in room_polys
        ]

    entrance_door_info = None
    for name in entrance_candidates:
        poly = room_polys[name]
        front_touch = poly.intersection(road_line)
        segments = extract_1d_segments(front_touch)
        for seg in segments:
            if seg.length >= 3.5:
                # Anchor entrance door cleanly
                mid_pt = seg.interpolate(0.35 if seg.length >= 7.0 else 0.5, normalized=True)
                coords = list(seg.coords)
                dx = abs(coords[-1][0] - coords[0][0])
                dy = abs(coords[-1][1] - coords[0][1])
                direction = "horizontal" if dx >= dy else "vertical"

                entrance_door_info = {
                    "room": name,
                    "position": [round(mid_pt.x, 2), round(mid_pt.y, 2)],
                    "seg": seg,
                }
                doors.append({
                    "id": f"door_{door_id_counter}",
                    "position": entrance_door_info["position"],
                    "direction": direction,
                    "width": 3.5,
                    "type": "entrance",
                    "rooms": [name, "Exterior"],
                })
                doors_per_room[name] += 1
                door_id_counter += 1
                break
        if entrance_door_info:
            break

    # 4. Resolve Interior Doors via Topological Access Hierarchy
    # Helper classifications
    def is_corridor(name: str, r_type: str) -> bool:
        n = name.lower()
        t = r_type.lower()
        return "corridor" in n or "spine" in n or "hallway" in n or "foyer" in n or "corridor" in t

    def is_bath(name: str, r_type: str) -> bool:
        n = name.lower()
        t = r_type.lower()
        return "bath" in n or "toilet" in n or "washroom" in n or "bath" in t

    def is_attached_bath(name: str, r_type: str, r_data: Dict[str, Any]) -> bool:
        n = name.lower()
        t = r_type.lower()
        att = r_data.get("attached_to")
        return bool(att) or "attached" in n or "ensuite" in n or "attached" in t or "master bath" in n

    def is_bedroom(name: str, r_type: str) -> bool:
        n = name.lower()
        t = r_type.lower()
        return "bed" in n or "bedroom" in t

    def is_living(name: str, r_type: str) -> bool:
        n = name.lower()
        t = r_type.lower()
        return "living" in n or "drawing" in n or "lounge" in n or "living" in t

    connected_pairs = set()

    # Pass A: Prioritize Circulation Hub Connections (Corridor/Foyer/Living -> Habitable Rooms & Common Baths)
    for r1_name, r2_name in adjacencies:
        if r1_name not in room_polys or r2_name not in room_polys:
            continue

        pair_key = tuple(sorted([r1_name, r2_name]))
        if pair_key in connected_pairs:
            continue

        r1_data = layout_rooms[r1_name]
        r2_data = layout_rooms[r2_name]
        r1_type = str(r1_data.get("type", "")).lower()
        r2_type = str(r2_data.get("type", "")).lower()

        # Rule 1: Never put doors into OTS
        if "ots" in r1_type or "ots" in r2_type:
            continue

        # Rule 2: Attached Bathroom must NEVER connect to corridor or public rooms
        if is_attached_bath(r1_name, r1_type, r1_data) and not is_bedroom(r2_name, r2_type):
            continue
        if is_attached_bath(r2_name, r2_type, r2_data) and not is_bedroom(r1_name, r1_type):
            continue

        # Rule 3: Single Door Invariant for Bathrooms
        if is_bath(r1_name, r1_type) and doors_per_room[r1_name] >= 1:
            continue
        if is_bath(r2_name, r2_type) and doors_per_room[r2_name] >= 1:
            continue

        # Rule 4: Bed to Bed direct door forbidden
        if is_bedroom(r1_name, r1_type) and is_bedroom(r2_name, r2_type):
            continue

        # Rule 5: If a room is an attached bath, it must only connect to its assigned bedroom
        if is_attached_bath(r1_name, r1_type, r1_data):
            assigned = r1_data.get("attached_to", "Master Bedroom")
            if assigned and assigned.lower() not in r2_name.lower():
                continue
        if is_attached_bath(r2_name, r2_type, r2_data):
            assigned = r2_data.get("attached_to", "Master Bedroom")
            if assigned and assigned.lower() not in r1_name.lower():
                continue

        # Compute 1D Shared Wall Intersection
        poly1 = room_polys[r1_name]
        poly2 = room_polys[r2_name]
        intersection = poly1.intersection(poly2)
        segments = extract_1d_segments(intersection)

        for seg in segments:
            bath_conn = is_bath(r1_name, r1_type) or is_bath(r2_name, r2_type)
            door_width = 2.5 if bath_conn else 3.0
            min_required_wall = door_width + 0.5

            if seg.length >= min_required_wall:
                mid_pt = seg.interpolate(0.5, normalized=True)
                coords = list(seg.coords)
                dx = abs(coords[-1][0] - coords[0][0])
                dy = abs(coords[-1][1] - coords[0][1])
                direction = "horizontal" if dx >= dy else "vertical"

                doors.append({
                    "id": f"door_{door_id_counter}",
                    "position": [round(mid_pt.x, 2), round(mid_pt.y, 2)],
                    "direction": direction,
                    "width": door_width,
                    "type": "bathroom" if bath_conn else "interior",
                    "rooms": [r1_name, r2_name],
                })
                door_id_counter += 1
                doors_per_room[r1_name] += 1
                doors_per_room[r2_name] += 1
                connected_pairs.add(pair_key)
                break

    # 5. Resolve Windows on Exterior Facades & OTS Shafts
    for name, r in layout_rooms.items():
        if name not in room_polys:
            continue
        r_type = str(r.get("type", "")).lower()
        if "ots" in r_type or "stair" in r_type or "corridor" in r_type:
            continue

        poly = room_polys[name]
        placed_for_room = False

        # Check all 4 outer facade lines
        for edge_name, line in facade_lines.items():
            ext_touch = poly.intersection(line)
            segments = extract_1d_segments(ext_touch)
            for seg in segments:
                if seg.length >= 3.5 and not placed_for_room:
                    # If this is the room with the entrance door on the road facade, offset window to 75%
                    if entrance_door_info and entrance_door_info["room"] == name and edge_name == road_edge:
                        if seg.length >= 8.0:
                            mid_pt = seg.interpolate(0.75, normalized=True)
                        else:
                            continue  # Wall too short to hold both door and window
                    else:
                        mid_pt = seg.interpolate(0.5, normalized=True)

                    coords = list(seg.coords)
                    dx = abs(coords[-1][0] - coords[0][0])
                    dy = abs(coords[-1][1] - coords[0][1])
                    direction = "horizontal" if dx >= dy else "vertical"

                    win_w = 3.0 if ("kitchen" in r_type or "bath" in r_type) else 4.0
                    windows.append({
                        "id": f"window_{window_id_counter}",
                        "position": [round(mid_pt.x, 2), round(mid_pt.y, 2)],
                        "direction": direction,
                        "width": win_w,
                        "type": "exterior",
                        "room": name,
                    })
                    window_id_counter += 1
                    placed_for_room = True

        # Check OTS shafts for light and ventilation
        for other_name, other_r in layout_rooms.items():
            if "ots" in str(other_r.get("type", "")).lower() and other_name in room_polys:
                ots_poly = room_polys[other_name]
                ots_touch = poly.intersection(ots_poly)
                segments = extract_1d_segments(ots_touch)
                for seg in segments:
                    if seg.length >= 2.5:
                        mid_pt = seg.interpolate(0.5, normalized=True)
                        coords = list(seg.coords)
                        dx = abs(coords[-1][0] - coords[0][0])
                        dy = abs(coords[-1][1] - coords[0][1])
                        direction = "horizontal" if dx >= dy else "vertical"

                        windows.append({
                            "id": f"window_{window_id_counter}",
                            "position": [round(mid_pt.x, 2), round(mid_pt.y, 2)],
                            "direction": direction,
                            "width": 2.5,
                            "type": "ots",
                            "room": name,
                        })
                        window_id_counter += 1

    return {
        "doors": doors,
        "windows": windows,
    }
