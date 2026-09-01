import math
import os

import pulp


def solve_layout(
    plot_width: float,
    plot_depth: float,
    setbacks: dict,
    stair_core_coords: tuple[float, float, float, float],  # (min_x, min_y, max_x, max_y)
    rooms: list[dict],
    adjacencies: list[tuple[str, str]] | None = None,
    road_edge: str = 'bottom',
    grid_snap: float = 0.5,
    time_limit_sec: int = 8,
    plumbing_cores: list[tuple[float, float, float, float]] | None = None
) -> dict:
    """
    Solves the room layout packing problem using Mixed-Integer Linear Programming (MILP).
    
    Args:
        plot_width: Width of the plot.
        plot_depth: Depth of the plot.
        setbacks: Dict of setbacks {'left', 'right', 'bottom', 'top'}.
        stair_core_coords: Bounding box of the stair core (min_x, min_y, max_x, max_y).
        rooms: List of room dictionaries.
        road_edge: Direction of the road ('bottom', 'top', 'left', 'right').
        grid_snap: Step size for grid snapping (default: 0.5 ft).
        time_limit_sec: Max solver runtime in seconds.
        
    Returns:
        Dict containing solver status, objective value, and room coordinates.
    """
    # Scale factor to convert float coordinates to integer variables for grid snapping
    S = 1.0 / grid_snap
    
    # Scale dimensions to integers
    pw_int = round(plot_width * S)
    pd_int = round(plot_depth * S)
    
    x_env_min = round(setbacks.get('left', 0.0) * S)
    x_env_max = pw_int - round(setbacks.get('right', 0.0) * S)
    y_env_min = round(setbacks.get('bottom', 0.0) * S)
    y_env_max = pd_int - round(setbacks.get('top', 0.0) * S)
    
    sc_x_min, sc_y_min, sc_x_max, sc_y_max = stair_core_coords
    sc_x_min_int = round(sc_x_min * S)
    sc_y_min_int = round(sc_y_min * S)
    sc_x_max_int = round(sc_x_max * S)
    sc_y_max_int = round(sc_y_max * S)
    
    # Big-M value: Maximum coordinate dimension
    M = max(pw_int, pd_int)
    
    # Initialize optimization problem
    prob = pulp.LpProblem("BuildingLayoutCompiler", pulp.LpMaximize)
    
    # Create variables for each room
    # x_i, y_i are bottom-left coordinates (as integers in grid units)
    # w_i, h_i are dimensions (as integers in grid units)
    x_vars = {}
    y_vars = {}
    w_vars = {}
    h_vars = {}
    x_prime_vars = {}
    y_prime_vars = {}
    orientation_vars = {}  # 1 = horizontal, 0 = vertical
    
    for room in rooms:
        name = room['name']
        
        # Determine room bounds in grid units
        min_w_int = round(room.get('min_width', 3.0) * S)
        min_h_int = round(room.get('min_height', 3.0) * S)
        
        # Continuous-like integer variables
        x_vars[name] = pulp.LpVariable(f"x_{name}", lowBound=x_env_min, upBound=x_env_max, cat=pulp.LpInteger)
        y_vars[name] = pulp.LpVariable(f"y_{name}", lowBound=y_env_min, upBound=y_env_max, cat=pulp.LpInteger)
        
        w_vars[name] = pulp.LpVariable(f"w_{name}", lowBound=min_w_int, upBound=x_env_max - x_env_min, cat=pulp.LpInteger)
        h_vars[name] = pulp.LpVariable(f"h_{name}", lowBound=min_h_int, upBound=y_env_max - y_env_min, cat=pulp.LpInteger)
        
        x_prime_vars[name] = pulp.LpVariable(f"x_prime_{name}", lowBound=x_env_min, upBound=x_env_max, cat=pulp.LpInteger)
        y_prime_vars[name] = pulp.LpVariable(f"y_prime_{name}", lowBound=y_env_min, upBound=y_env_max, cat=pulp.LpInteger)
        
        # Orientation variable for aspect ratio rotation
        orientation_vars[name] = pulp.LpVariable(f"o_{name}", cat=pulp.LpBinary)
        
        # Link coordinates
        prob += x_prime_vars[name] == x_vars[name] + w_vars[name], f"link_x_{name}"
        prob += y_prime_vars[name] == y_vars[name] + h_vars[name], f"link_y_{name}"
        
        # Keep rooms strictly inside buildable envelope boundaries
        prob += x_vars[name] >= x_env_min, f"bound_x_min_{name}"
        prob += x_prime_vars[name] <= x_env_max, f"bound_x_max_{name}"
        prob += y_vars[name] >= y_env_min, f"bound_y_min_{name}"
        prob += y_prime_vars[name] <= y_env_max, f"bound_y_max_{name}"
        
        # Avoid Stair Core (Obstacle) - only if stair core has non-zero area
        has_stair_core = (sc_x_max_int > sc_x_min_int) and (sc_y_max_int > sc_y_min_int)
        if has_stair_core:
            sc_bin = [pulp.LpVariable(f"b_sc_{name}_{k}", cat=pulp.LpBinary) for k in range(4)]
            prob += x_prime_vars[name] <= sc_x_min_int + M * (1 - sc_bin[0]), f"sc_left_{name}"
            prob += x_vars[name] >= sc_x_max_int - M * (1 - sc_bin[1]), f"sc_right_{name}"
            prob += y_prime_vars[name] <= sc_y_min_int + M * (1 - sc_bin[2]), f"sc_below_{name}"
            prob += y_vars[name] >= sc_y_max_int - M * (1 - sc_bin[3]), f"sc_above_{name}"
            prob += sum(sc_bin) >= 1, f"sc_overlap_{name}"
        
        # Aspect Ratio Constraints
        # Aspect ratio bounds (default 1.0 to 1.6)
        _ar_min, ar_max = room.get('aspect_ratio_range', (1.0, 1.6))
        
        # o_i = 1: Horizontal (w >= h, w <= ar_max * h)
        # o_i = 0: Vertical (h >= w, h <= ar_max * w)
        prob += w_vars[name] - h_vars[name] >= -M * (1 - orientation_vars[name]), f"ar_orient_1_{name}"
        prob += w_vars[name] - ar_max * h_vars[name] <= M * (1 - orientation_vars[name]), f"ar_orient_2_{name}"
        
        prob += h_vars[name] - w_vars[name] >= -M * orientation_vars[name], f"ar_orient_3_{name}"
        prob += h_vars[name] - ar_max * w_vars[name] <= M * orientation_vars[name], f"ar_orient_4_{name}"
        
        # Area constraint: w_i * h_i >= A_i (min_area)
        # Using linear tangent approximation (convex boundary h_i_int >= A_int / w_i_int)
        min_area = room.get('min_area', 100.0)
        A_int = min_area * (S ** 2)
        
        # Sample 5 points for tangent lines based on range of valid widths
        w_start = max(min_w_int, int(math.sqrt(A_int / ar_max)))
        w_end = min(x_env_max - x_env_min, int(math.sqrt(A_int * ar_max)))
        
        if w_end > w_start:
            points = [w_start + i * (w_end - w_start) // 4 for i in range(5)]
            points = sorted(set(points))  # Remove duplicates
        else:
            points = [w_start]
            
        for k, wk in enumerate(points):
            if wk <= 0:
                continue
            # Tangent line of h = A/w at wk is h >= 2A/wk - (A/wk^2)*w
            slope = A_int / (wk ** 2)
            intercept = 2 * A_int / wk
            prob += h_vars[name] >= intercept - slope * w_vars[name], f"area_tangent_{name}_{k}"
            
        # Adjacency to road (if applicable)
        if room.get('adjacent_to_road', False):
            if road_edge == 'bottom':
                prob += y_vars[name] == y_env_min, f"road_bottom_{name}"
            elif road_edge == 'top':
                prob += y_prime_vars[name] == y_env_max, f"road_top_{name}"
            elif road_edge == 'left':
                prob += x_vars[name] == x_env_min, f"road_left_{name}"
            elif road_edge == 'right':
                prob += x_prime_vars[name] == x_env_max, f"road_right_{name}"
                
    # Room-to-Room Non-Overlap Constraints
    overlap_vars_dict = {}
    room_names = [room['name'] for room in rooms]
    for i in range(len(room_names)):
        for j in range(i + 1, len(room_names)):
            ri = room_names[i]
            rj = room_names[j]
            
            # Non-overlap binary variables
            overlap_bin = [pulp.LpVariable(f"b_overlap_{ri.replace(' ', '_')}_{rj.replace(' ', '_')}_{k}", cat=pulp.LpBinary) for k in range(4)]
            
            # Constraints:
            # 1. ri is to the left of rj
            prob += x_prime_vars[ri] <= x_vars[rj] + M * (1 - overlap_bin[0]), f"overlap_left_{ri}_{rj}"
            # 2. ri is to the right of rj
            prob += x_vars[ri] >= x_prime_vars[rj] - M * (1 - overlap_bin[1]), f"overlap_right_{ri}_{rj}"
            # 3. ri is below rj
            prob += y_prime_vars[ri] <= y_vars[rj] + M * (1 - overlap_bin[2]), f"overlap_below_{ri}_{rj}"
            # 4. ri is above rj
            prob += y_vars[ri] >= y_prime_vars[rj] - M * (1 - overlap_bin[3]), f"overlap_above_{ri}_{rj}"
            
            # Enforce at least one non-overlapping boundary condition
            prob += sum(overlap_bin) >= 1, f"overlap_sum_{ri}_{rj}"
            
            # Store for reuse in touch constraints
            key = tuple(sorted([ri, rj]))
            overlap_vars_dict[key] = (overlap_bin, ri, rj)
            
    # Optimized touch helper function that reuses existing non-overlap binary variables
    def add_optimized_touch_constraint(r1: str, r2: str, D_touch: int, prefix: str):
        nonlocal prob
        key = tuple(sorted([r1, r2]))
        if key not in overlap_vars_dict:
            return
        
        overlap_bin, u, _v = overlap_vars_dict[key]
        is_r1_u = (r1 == u)
        
        if is_r1_u:
            # Side 0: u (r1) is immediately to the left of v (r2)
            prob += x_prime_vars[r1] >= x_vars[r2] - M * (1 - overlap_bin[0]), f"{prefix}_opt_left_1"
            prob += y_prime_vars[r1] - y_vars[r2] >= D_touch - M * (1 - overlap_bin[0]), f"{prefix}_opt_left_2"
            prob += y_prime_vars[r2] - y_vars[r1] >= D_touch - M * (1 - overlap_bin[0]), f"{prefix}_opt_left_3"
            
            # Side 1: u (r1) is immediately to the right of v (r2)
            prob += x_vars[r1] <= x_prime_vars[r2] + M * (1 - overlap_bin[1]), f"{prefix}_opt_right_1"
            prob += y_prime_vars[r1] - y_vars[r2] >= D_touch - M * (1 - overlap_bin[1]), f"{prefix}_opt_right_2"
            prob += y_prime_vars[r2] - y_vars[r1] >= D_touch - M * (1 - overlap_bin[1]), f"{prefix}_opt_right_3"
            
            # Side 2: u (r1) is immediately below v (r2)
            prob += y_prime_vars[r1] >= y_vars[r2] - M * (1 - overlap_bin[2]), f"{prefix}_opt_below_1"
            prob += x_prime_vars[r1] - x_vars[r2] >= D_touch - M * (1 - overlap_bin[2]), f"{prefix}_opt_below_2"
            prob += x_prime_vars[r2] - x_vars[r1] >= D_touch - M * (1 - overlap_bin[2]), f"{prefix}_opt_below_3"
            
            # Side 3: u (r1) is immediately above v (r2)
            prob += y_vars[r1] <= y_prime_vars[r2] + M * (1 - overlap_bin[3]), f"{prefix}_opt_above_1"
            prob += x_prime_vars[r1] - x_vars[r2] >= D_touch - M * (1 - overlap_bin[3]), f"{prefix}_opt_above_2"
            prob += x_prime_vars[r2] - x_vars[r1] >= D_touch - M * (1 - overlap_bin[3]), f"{prefix}_opt_above_3"
        else:
            # Side 0: v (r1) is to the left of u (r2) -> u (r2) is to the right of v (r1) -> overlap_bin[1]
            prob += x_prime_vars[r1] >= x_vars[r2] - M * (1 - overlap_bin[1]), f"{prefix}_opt_left_1_rev"
            prob += y_prime_vars[r1] - y_vars[r2] >= D_touch - M * (1 - overlap_bin[1]), f"{prefix}_opt_left_2_rev"
            prob += y_prime_vars[r2] - y_vars[r1] >= D_touch - M * (1 - overlap_bin[1]), f"{prefix}_opt_left_3_rev"
            
            # Side 1: v (r1) is to the right of u (r2) -> u (r2) is to the left of v (r1) -> overlap_bin[0]
            prob += x_vars[r1] <= x_prime_vars[r2] + M * (1 - overlap_bin[0]), f"{prefix}_opt_right_1_rev"
            prob += y_prime_vars[r1] - y_vars[r2] >= D_touch - M * (1 - overlap_bin[0]), f"{prefix}_opt_right_2_rev"
            prob += y_prime_vars[r2] - y_vars[r1] >= D_touch - M * (1 - overlap_bin[0]), f"{prefix}_opt_right_3_rev"
            
            # Side 2: v (r1) is below u (r2) -> u (r2) is above v (r1) -> overlap_bin[3]
            prob += y_prime_vars[r1] >= y_vars[r2] - M * (1 - overlap_bin[3]), f"{prefix}_opt_below_1_rev"
            prob += x_prime_vars[r1] - x_vars[r2] >= D_touch - M * (1 - overlap_bin[3]), f"{prefix}_opt_below_2_rev"
            prob += x_prime_vars[r2] - x_vars[r1] >= D_touch - M * (1 - overlap_bin[3]), f"{prefix}_opt_below_3_rev"
            
            # Side 3: v (r1) is above u (r2) -> u (r2) is below v (r1) -> overlap_bin[2]
            prob += y_vars[r1] <= y_prime_vars[r2] + M * (1 - overlap_bin[2]), f"{prefix}_opt_above_1_rev"
            prob += x_prime_vars[r1] - x_vars[r2] >= D_touch - M * (1 - overlap_bin[2]), f"{prefix}_opt_above_2_rev"
            prob += x_prime_vars[r2] - x_vars[r1] >= D_touch - M * (1 - overlap_bin[2]), f"{prefix}_opt_above_3_rev"

    # Enforce OTS ventilation touch constraints (minimum 2 ft shared wall)
    D_ots_touch_int = max(1, round(2.0 * S))
    for room in rooms:
        name = room['name']
        ventilates_target = room.get('ventilates', None)
        if ventilates_target and ventilates_target in x_vars:
            add_optimized_touch_constraint(name, ventilates_target, D_ots_touch_int, f"ots_touch_{name.replace(' ', '_')}_{ventilates_target.replace(' ', '_')}")
            
    # Enforce door adjacency touch constraints (minimum 3 ft shared wall for access doorways)
    if adjacencies:
        D_door_touch_int = max(1, round(3.0 * S))
        for idx, (r1, r2) in enumerate(adjacencies):
            # Only apply if both rooms are active/packed
            if r1 in x_vars and r2 in x_vars:
                r1_clean = r1.replace(" ", "_")
                r2_clean = r2.replace(" ", "_")
                add_optimized_touch_constraint(r1, r2, D_door_touch_int, f"adj_touch_{idx}_{r1_clean}_{r2_clean}")
            
    # --- Phase 4 Soft Constraints & Objective Function Configuration ---
    
    # Helper to calculate Manhattan distance between two rooms (bottom-left to bottom-left)
    def add_distance_vars(r1: str, r2: str, prefix: str):
        nonlocal prob
        if r1 not in x_vars or r2 not in x_vars:
            return None
        dx = pulp.LpVariable(f"dx_{prefix}", lowBound=0, cat=pulp.LpInteger)
        dy = pulp.LpVariable(f"dy_{prefix}", lowBound=0, cat=pulp.LpInteger)
        
        prob += dx >= x_vars[r1] - x_vars[r2]
        prob += dx >= x_vars[r2] - x_vars[r1]
        prob += dy >= y_vars[r1] - y_vars[r2]
        prob += dy >= y_vars[r2] - y_vars[r1]
        
        return dx + dy

    def _is_rtype(r, target):
        return target in str(r.get('type', '')).lower() or target in str(r.get('name', '')).lower()

    # 1. Target Proportions & Sizing: Penalize deviation from target size (prevents bloat)
    dev_vars = {}
    for r in rooms:
        name = r['name']
        t_area = r.get('target_area', r.get('min_area', 100.0))
        target_semi_p = round(2.0 * math.sqrt(t_area) * S)
        dev = pulp.LpVariable(f"dev_{name.replace(' ', '_').replace('-', '_')}", lowBound=0, cat=pulp.LpContinuous)
        prob += dev >= (w_vars[name] + h_vars[name]) - target_semi_p
        prob += dev >= target_semi_p - (w_vars[name] + h_vars[name])
        dev_vars[name] = dev

    obj = -4.0 * sum(dev_vars.values())
    
    # 2. Daylight & Ventilation: Reward rooms touching outer envelope boundaries
    vent_rooms = [r['name'] for r in rooms if r.get('requires_ventilation', False) or _is_rtype(r, 'bed') or _is_rtype(r, 'kitchen')]
    vent_rewards = []
    for name in vent_rooms:
        clean_n = name.replace(' ', '_').replace('-', '_')
        b_left = pulp.LpVariable(f"b_left_{clean_n}", cat=pulp.LpBinary)
        b_right = pulp.LpVariable(f"b_right_{clean_n}", cat=pulp.LpBinary)
        b_top = pulp.LpVariable(f"b_top_{clean_n}", cat=pulp.LpBinary)
        b_bottom = pulp.LpVariable(f"b_bottom_{clean_n}", cat=pulp.LpBinary)
        
        prob += x_vars[name] <= x_env_min + M * (1 - b_left)
        prob += x_prime_vars[name] >= x_env_max - M * (1 - b_right)
        prob += y_vars[name] <= y_env_min + M * (1 - b_bottom)
        prob += y_prime_vars[name] >= y_env_max - M * (1 - b_top)
        
        vent_rewards.append(b_left + b_right + b_top + b_bottom)
        
    if vent_rewards:
        obj += 10.0 * sum(vent_rewards)
        
    # 3. Compact Circulation: Keep Kitchen near Living Room
    units = set(r.get('unit_id') for r in rooms if r.get('unit_id'))
    if units:
        for u in units:
            k_name = next((r['name'] for r in rooms if _is_rtype(r, 'kitchen') and r.get('unit_id') == u), None)
            l_name = next((r['name'] for r in rooms if _is_rtype(r, 'living') and r.get('unit_id') == u), None)
            if k_name and l_name:
                dist_kl = add_distance_vars(k_name, l_name, f"kit_liv_{u}")
                if dist_kl is not None:
                    obj -= 2.0 * dist_kl
    else:
        kitchen_name = next((r['name'] for r in rooms if _is_rtype(r, 'kitchen')), None)
        living_name = next((r['name'] for r in rooms if _is_rtype(r, 'living')), None)
        if kitchen_name and living_name:
            dist_kl = add_distance_vars(kitchen_name, living_name, "kit_liv")
            if dist_kl is not None:
                obj -= 2.5 * dist_kl
            
    # 4. Plumbing Alignment: Keep Bathrooms close to each other
    bath_names = [r['name'] for r in rooms if _is_rtype(r, 'bath')]
    if len(bath_names) >= 2 and len(rooms) <= 6:
        for idx in range(len(bath_names) - 1):
            dist_bb = add_distance_vars(bath_names[idx], bath_names[idx+1], f"bath_{idx}")
            if dist_bb is not None:
                obj -= 2.0 * dist_bb
                
    # 5. Bedroom Privacy: Keep Bedrooms in quiet rear zone away from Entrance
    bedroom_names = [r['name'] for r in rooms if _is_rtype(r, 'bed')]
    if bedroom_names:
        for bed_name in bedroom_names:
            if road_edge == 'bottom':
                obj += 3.0 * y_vars[bed_name]
            elif road_edge == 'top':
                obj -= 3.0 * y_vars[bed_name]
            elif road_edge == 'left':
                obj += 3.0 * x_vars[bed_name]
            elif road_edge == 'right':
                obj -= 3.0 * x_vars[bed_name]
                
    # 6. Public Zone: Keep Living Room along the front road edge
    living_names = [r['name'] for r in rooms if _is_rtype(r, 'living')]
    if living_names:
        for l_name in living_names:
            if road_edge == 'bottom':
                obj -= 3.0 * y_vars[l_name]
            elif road_edge == 'top':
                obj += 3.0 * y_vars[l_name]
            elif road_edge == 'left':
                obj -= 3.0 * x_vars[l_name]
            elif road_edge == 'right':
                obj += 3.0 * x_vars[l_name]
                
    # 6. Multi-Floor Plumbing Alignment: Align bathrooms with lower floor plumbing cores
    if plumbing_cores:
        bath_rooms = [r['name'] for r in rooms if r['type'] == 'Bathroom']
        for i, bath_name in enumerate(bath_rooms):
            for j, pc in enumerate(plumbing_cores):
                pc_xmin, pc_ymin, pc_xmax, pc_ymax = pc
                pc_cx = (pc_xmin + pc_xmax) / 2.0
                pc_cy = (pc_ymin + pc_ymax) / 2.0
                
                pc_cx_int = round(pc_cx * S)
                pc_cy_int = round(pc_cy * S)
                
                # Distance variables
                dx = pulp.LpVariable(f"dx_pc_{i}_{j}", lowBound=0, cat=pulp.LpContinuous)
                dy = pulp.LpVariable(f"dy_pc_{i}_{j}", lowBound=0, cat=pulp.LpContinuous)
                
                prob += dx >= (x_vars[bath_name] + w_vars[bath_name] / 2.0) - pc_cx_int
                prob += dx >= pc_cx_int - (x_vars[bath_name] + w_vars[bath_name] / 2.0)
                prob += dy >= (y_vars[bath_name] + h_vars[bath_name] / 2.0) - pc_cy_int
                prob += dy >= pc_cy_int - (y_vars[bath_name] + h_vars[bath_name] / 2.0)
                
                # Subtract from objective to reward overlap/proximity
                obj -= 5.0 * (dx + dy)

    # Register objective function
    prob += obj, "Maximize_Aesthetic_Layout"
    
    # Solve with time limit and optimization tolerances (gap tolerance: 2%)
    solver = pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit_sec, gapRel=0.02)
    
    # Configure custom temporary directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    tmp_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "..", "tmp"))
    os.makedirs(tmp_dir, exist_ok=True)
    solver.tmpDir = tmp_dir
    
    status = prob.solve(solver)
    status_str = pulp.LpStatus[status]
    
    if status_str != "Optimal" and status_str != "Feasible":
        return {
            "status": status_str,
            "success": False,
            "error": f"MILP solver failed to find a valid layout. Status: {status_str}"
        }
        
    # Extract coordinates and convert back to actual float dimensions
    results = {}
    for name in room_names:
        rx = x_vars[name].varValue * grid_snap
        ry = y_vars[name].varValue * grid_snap
        rw = w_vars[name].varValue * grid_snap
        rh = h_vars[name].varValue * grid_snap
        
        results[name] = {
            "name": name,
            "type": next(r['type'] for r in rooms if r['name'] == name),
            "x": float(rx),
            "y": float(ry),
            "width": float(rw),
            "height": float(rh),
            "coordinates": [
                [float(rx), float(ry)],
                [float(rx), float(ry + rh)],
                [float(rx + rw), float(ry + rh)],
                [float(rx + rw), float(ry)]
            ]
        }
        
    return {
        "status": status_str,
        "success": True,
        "rooms": results
    }
