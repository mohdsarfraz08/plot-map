from typing import Any


def compile_geometry(
    layout_rooms: dict[str, dict],
    envelope_coords: list[tuple[float, float]],
    stair_core_coords: list[tuple[float, float]],
    adjacencies: list[tuple[str, str]]
) -> dict[str, Any]:
    """
    Phase 5 Geometry Compiler:
    Converts 2D room box coordinates into a detailed architectural model with:
    - Walls (exterior/interior with thickness)
    - Doors (positioned on shared walls)
    - Windows (exterior and OTS ventilation openings)
    - Snapping & merging of shared boundaries
    """
    # 1. Extract bounding boxes of all elements
    boxes = {}
    for name, room in layout_rooms.items():
        boxes[name] = {
            "name": name,
            "type": room["type"],
            "x": room["x"],
            "y": room["y"],
            "w": room["width"],
            "h": room["height"],
            "is_ots": room["type"] == "OTS",
            "is_stair": room["type"] == "Staircase" or "stair" in name.lower()
        }
        
    # Add stair core as a box if present in coordinates
    if stair_core_coords and len(stair_core_coords) >= 4:
        xs = [p[0] for p in stair_core_coords]
        ys = [p[1] for p in stair_core_coords]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        if max_x - min_x > 0.05 and max_y - min_y > 0.05:
            boxes["Staircase"] = {
                "name": "Staircase",
                "type": "Staircase",
                "x": min_x,
                "y": min_y,
                "w": max_x - min_x,
                "h": max_y - min_y,
                "is_ots": False,
                "is_stair": True
            }
            
    # 2. Extract unique wall segments
    walls = []
    wall_id_counter = 1
    
    horizontal_walls = []
    vertical_walls = []
    
    # Get envelope bounds
    if envelope_coords:
        xs = [p[0] for p in envelope_coords]
        ys = [p[1] for p in envelope_coords]
        env_min_x, env_max_x = min(xs), max(xs)
        env_min_y, env_max_y = min(ys), max(ys)
    else:
        env_min_x, env_max_x = 0.0, 100.0
        env_min_y, env_max_y = 0.0, 100.0
        
    # Helper to add wall
    def add_wall(x1, y1, x2, y2, wall_type, rooms_list):
        nonlocal wall_id_counter
        x1, y1 = round(x1, 2), round(y1, 2)
        x2, y2 = round(x2, 2), round(y2, 2)
        if x1 == x2 and y1 == y2:
            return
        
        # Sort coordinates to keep start < end
        if x1 > x2 or (x1 == x2 and y1 > y2):
            x1, x2 = x2, x1
            y1, y2 = y2, y1
            
        thickness = 0.75 if wall_type == "exterior" else 0.375
        walls.append({
            "id": f"wall_{wall_id_counter}",
            "start": [x1, y1],
            "end": [x2, y2],
            "type": wall_type,
            "thickness": thickness,
            "rooms": rooms_list
        })
        wall_id_counter += 1

    # For each box, generate its 4 wall segments
    for name, box in boxes.items():
        if box["is_ots"]:
            continue  # OTS has no physical walls
            
        # Helper to classify vertical segment
        def classify_vertical(vx, vy1, vy2, name=name):
            sharing_rooms = [name]
            is_ext = True
            for other_name, other_box in boxes.items():
                if other_name == name or other_box["is_ots"]:
                    continue
                if abs(other_box["x"] - vx) < 0.05 or abs(other_box["x"] + other_box["w"] - vx) < 0.05:
                    oy1 = max(vy1, other_box["y"])
                    oy2 = min(vy2, other_box["y"] + other_box["h"])
                    if oy2 - oy1 > 0.05:
                        sharing_rooms.append(other_name)
                        is_ext = False
            
            if abs(vx - env_min_x) < 0.05 or abs(vx - env_max_x) < 0.05:
                is_ext = True
            return "exterior" if is_ext else "interior", list(set(sharing_rooms))

        # Helper to classify horizontal segment
        def classify_horizontal(hy, hx1, hx2, name=name):
            sharing_rooms = [name]
            is_ext = True
            for other_name, other_box in boxes.items():
                if other_name == name or other_box["is_ots"]:
                    continue
                if abs(other_box["y"] - hy) < 0.05 or abs(other_box["y"] + other_box["h"] - hy) < 0.05:
                    ox1 = max(hx1, other_box["x"])
                    ox2 = min(hx2, other_box["x"] + other_box["w"])
                    if ox2 - ox1 > 0.05:
                        sharing_rooms.append(other_name)
                        is_ext = False
                        
            if abs(hy - env_min_y) < 0.05 or abs(hy - env_max_y) < 0.05:
                is_ext = True
            return "exterior" if is_ext else "interior", list(set(sharing_rooms))

        # Left edge
        w_type, rooms_list = classify_vertical(box["x"], box["y"], box["y"] + box["h"])
        vertical_walls.append((box["x"], box["y"], box["y"] + box["h"], w_type, rooms_list))
        # Right edge
        w_type, rooms_list = classify_vertical(box["x"] + box["w"], box["y"], box["y"] + box["h"])
        vertical_walls.append((box["x"] + box["w"], box["y"], box["y"] + box["h"], w_type, rooms_list))
        # Bottom edge
        w_type, rooms_list = classify_horizontal(box["y"], box["x"], box["x"] + box["w"])
        horizontal_walls.append((box["y"], box["x"], box["x"] + box["w"], w_type, rooms_list))
        # Top edge
        w_type, rooms_list = classify_horizontal(box["y"] + box["h"], box["x"], box["x"] + box["w"])
        horizontal_walls.append((box["y"] + box["h"], box["x"], box["x"] + box["w"], w_type, rooms_list))

    # Merge collinear overlapping horizontal walls
    merged_horizontal = []
    by_y = {}
    for y, x1, x2, w_type, rooms_list in horizontal_walls:
        y_key = round(y, 2)
        if y_key not in by_y:
            by_y[y_key] = []
        by_y[y_key].append((x1, x2, w_type, rooms_list))
        
    for y_val, segs in by_y.items():
        segs.sort(key=lambda s: s[0])
        cur_x1, cur_x2, cur_type, cur_rooms = segs[0]
        for next_x1, next_x2, next_type, next_rooms in segs[1:]:
            if next_x1 <= cur_x2 + 0.05:
                cur_x2 = max(cur_x2, next_x2)
                if next_type == "interior":
                    cur_type = "interior"
                cur_rooms = list(set(cur_rooms + next_rooms))
            else:
                merged_horizontal.append((y_val, cur_x1, cur_x2, cur_type, cur_rooms))
                cur_x1, cur_x2, cur_type, cur_rooms = next_x1, next_x2, next_type, next_rooms
        merged_horizontal.append((y_val, cur_x1, cur_x2, cur_type, cur_rooms))

    # Merge collinear overlapping vertical walls
    merged_vertical = []
    by_x = {}
    for x, y1, y2, w_type, rooms_list in vertical_walls:
        x_key = round(x, 2)
        if x_key not in by_x:
            by_x[x_key] = []
        by_x[x_key].append((y1, y2, w_type, rooms_list))
        
    for x_val, segs in by_x.items():
        segs.sort(key=lambda s: s[0])
        cur_y1, cur_y2, cur_type, cur_rooms = segs[0]
        for next_y1, next_y2, next_type, next_rooms in segs[1:]:
            if next_y1 <= cur_y2 + 0.05:
                cur_y2 = max(cur_y2, next_y2)
                if next_type == "interior":
                    cur_type = "interior"
                cur_rooms = list(set(cur_rooms + next_rooms))
            else:
                merged_vertical.append((x_val, cur_y1, cur_y2, cur_type, cur_rooms))
                cur_y1, cur_y2, cur_type, cur_rooms = next_y1, next_y2, next_type, next_rooms
        merged_vertical.append((x_val, cur_y1, cur_y2, cur_type, cur_rooms))

    # Add all merged walls
    for y_val, x1, x2, w_type, r_list in merged_horizontal:
        add_wall(x1, y_val, x2, y_val, w_type, r_list)
    for x_val, y1, y2, w_type, r_list in merged_vertical:
        add_wall(x_val, y1, x_val, y2, w_type, r_list)

    # 3. Generate doors & windows using topological 1D Shapely intersections
    from app.services.geometry.opening_resolver import resolve_openings_topologically
    
    openings = resolve_openings_topologically(
        layout_rooms=layout_rooms,
        envelope_coords=envelope_coords,
        adjacencies=adjacencies,
        road_edge="bottom"
    )

    return {
        "walls": walls,
        "doors": openings["doors"],
        "windows": openings["windows"]
    }

