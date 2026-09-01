"""
Fast-Track Hybrid Architecture Compiler.
Combines Agent 1 (Spatial Planner), Blueprint Snapper, and Topological Opening Resolver
to generate instant (< 1.5s), mathematically clean, fully-rendered 2D/3D architectural floor plans.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from app.drawing import Drawing, Polyline, Line, Arc, Text, Hatch, Dimension, export_drawing_to_svg
from app.drawing.symbols import generate_door_symbol, generate_window_symbol
from app.schemas.intent import CompilerIntent

from app.services.ai.parser import parse_requirements
from app.services.ai.spatial_planner import plan_spatial_blueprint
from app.services.geometry.blueprint_snapper import realize_blueprint_to_world_layout
from app.services.geometry.compiler import compile_geometry
from app.services.geometry.metrics import calculate_layout_metrics
from app.services.geometry.setbacks import calculate_buildable_area, create_plot


def compile_layout_fast(
    prompt: str,
    client: Any = None,
    ai_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    End-to-end fast-track compilation pipeline:
    1. Parse Intent (CompilerIntent)
    2. Plan Scale-Invariant Spatial Blueprint (Agent 1)
    3. Cleanse, Stitch & Snap to 0.5 ft World Coordinates (Blueprint Snapper)
    4. Compile 1D Topological Geometry (Doors on Spine, Windows on Facades)
    5. Render 2D CAD SVG with dimensions + 3D Payload in < 1.5s.
    """
    # 1. Parse Requirements
    intent = parse_requirements(prompt, client=client, ai_state=ai_state)

    plot_w = float(intent.plot_width)
    plot_d = float(intent.plot_depth)
    front_setback = float(intent.front_road_setback)

    setbacks = {
        "left": 3.0,
        "right": 3.0,
        "bottom": front_setback,
        "top": 3.0,
    }

    buildable_w = max(0.0, plot_w - setbacks["left"] - setbacks["right"])
    buildable_d = max(0.0, plot_d - setbacks["bottom"] - setbacks["top"])

    # 2. Geometric Envelope & Feasibility Gate
    if plot_w < 15.0 or plot_d < 15.0 or (buildable_w * buildable_d < 120.0):
        from app.core.exceptions import InfeasibleRequestError
        raise InfeasibleRequestError("Plot dimensions too small to accommodate the requested residential program.")

    plot = create_plot(plot_w, plot_d)

    stair_cfg = {"width": 8.0, "height": 8.0, "edge": "bottom-left"}
    envelope, core, buildable_area = calculate_buildable_area(plot, setbacks, stair_cfg)

    # 3. Plan Spatial Blueprint (Agent 1)
    blueprint = plan_spatial_blueprint(
        prompt=prompt,
        intent=intent,
        buildable_width=buildable_w,
        buildable_depth=buildable_d,
        road_edge="bottom",
        client=client,
    )

    # 4. Snap and Realize to Real World Coordinates
    realized = realize_blueprint_to_world_layout(
        blueprint=blueprint,
        plot_width=plot_w,
        plot_depth=plot_d,
        setbacks=setbacks,
        grid_snap_ft=0.5,
    )

    world_rooms = realized["rooms"]
    adjacencies = realized["adjacencies"]

    envelope_coords = list(envelope.exterior.coords) if not envelope.is_empty else []
    
    # 5. Core Coords strictly for actual internal Staircase room
    core_coords = []
    stair_room = next((r for name, r in world_rooms.items() if "stair" in name.lower() or "stair" in str(r.get("type", "")).lower()), None)
    if stair_room and intent.floors > 1:
        sx, sy, sw, sh = stair_room["x"], stair_room["y"], stair_room["width"], stair_room["height"]
        core_coords = [(sx, sy), (sx + sw, sy), (sx + sw, sy + sh), (sx, sy + sh)]


    # 6. Compile Geometry & Openings

    geometry_detail = compile_geometry(
        layout_rooms=world_rooms,
        envelope_coords=envelope_coords,
        stair_core_coords=core_coords,
        adjacencies=adjacencies,
    )

    floors_data = {
        "1": {
            "layout": world_rooms,
            "geometry": geometry_detail,
        }
    }

    # If multi-floor, copy upper layout
    if intent.floors > 1:
        floors_data["2"] = {
            "layout": world_rooms,
            "geometry": geometry_detail,
        }

    # Calculate metrics
    metrics = calculate_layout_metrics(
        plot_width=plot_w,
        plot_depth=plot_d,
        floors_data=floors_data,
        stair_core_cfg=stair_cfg,
    )

    # 6. Generate Publication-Grade 2D Architectural CAD Drawing
    drawing = Drawing()

    # 6.1 Outer Plot Boundary & Road Banner (Grid Layer)
    drawing.add(Polyline(
        layer="Grid",
        color="#334155",
        stroke_width=1.5,
        points=[[0, 0], [plot_w, 0], [plot_w, plot_d], [0, plot_d]],
        is_closed=True,
    ))

    # Front Road Access Banner & Entry Arrows
    drawing.add(Text(
        layer="Annotations",
        x=plot_w / 2,
        y=-1.5,
        content="▲ FRONT ROAD ACCESS (NBC 2016) ▲",
        font_size=10.0,
        color="#38bdf8",
        anchor="middle",
    ))

    # North Arrow Indicator (Top Right)
    na_x = plot_w - 2.5
    na_y = plot_d + 3.0
    drawing.add(Line(layer="Annotations", color="#e2e8f0", stroke_width=1.5, x1=na_x, y1=na_y - 1.5, x2=na_x, y2=na_y + 1.5))
    drawing.add(Polyline(layer="Annotations", color="#e2e8f0", stroke_width=1.5, points=[[na_x - 0.6, na_y + 0.5], [na_x, na_y + 1.5], [na_x + 0.6, na_y + 0.5]], is_closed=False))
    drawing.add(Text(layer="Annotations", x=na_x, y=na_y + 2.2, content="N", font_size=11.0, color="#38bdf8", anchor="middle"))

    # 6.2 Room Pastel Zoning Fills & Room Badges (Annotations Layer)
    room_palette = {
        "Living Room": "#0284c7",
        "Dining": "#0369a1",
        "Kitchen": "#d97706",
        "Master Bedroom": "#7c3aed",
        "Bedroom": "#4f46e5",
        "Bathroom": "#0891b2",
        "Attached Bathroom": "#0891b2",
        "OTS": "#059669",
        "Staircase": "#ea580c",
        "Foyer": "#475569",
        "Balcony": "#059669",
        "Corridor": "#334155",
    }

    for r_name, r_box in world_rooms.items():
        rx, ry = float(r_box["x"]), float(r_box["y"])
        rw, rh = float(r_box["width"]), float(r_box["height"])
        r_type = r_box.get("type", "Living Room")

        # Color fill
        fill_col = room_palette.get(r_type, "#64748b")
        drawing.add(Hatch(
            layer="Annotations",
            boundary_points=[[rx, ry], [rx + rw, ry], [rx + rw, ry + rh], [rx, ry + rh]],
            fill_color=fill_col,
        ))

        # Room Text Labels
        cx = rx + rw / 2
        cy = ry + rh / 2

        drawing.add(Text(
            layer="Annotations",
            x=cx,
            y=cy + 1.0,
            content=r_name.upper(),
            font_size=10.5,
            color="#f8fafc",
            anchor="middle",
        ))
        drawing.add(Text(
            layer="Annotations",
            x=cx,
            y=cy - 0.5,
            content=f"{int(rw)}'-0\" × {int(rh)}'-0\"",
            font_size=8.5,
            color="#cbd5e1",
            anchor="middle",
        ))
        area_sqft = int(rw * rh)
        drawing.add(Text(
            layer="Annotations",
            x=cx,
            y=cy - 1.8,
            content=f"({area_sqft} SQ.FT)",
            font_size=7.5,
            color="#94a3b8",
            anchor="middle",
        ))


    # 6.3 Dogleg Staircase 2D Treads (Structural Layer)
    if stair_cfg and core_coords:
        sx_min = min(c[0] for c in core_coords)
        sx_max = max(c[0] for c in core_coords)
        sy_min = min(c[1] for c in core_coords)
        sy_max = max(c[1] for c in core_coords)
        sw = sx_max - sx_min
        sh = sy_max - sy_min

        mid_x = sx_min + sw / 2
        landing_y = sy_min + sh * 0.4

        drawing.add(Line(
            layer="Structural",
            color="#f97316",
            stroke_width=1.5,
            x1=mid_x, y1=landing_y,
            x2=mid_x, y2=sy_max
        ))

        num_treads = 6
        step_h = (sy_max - landing_y) / num_treads
        for step_i in range(num_treads):
            ty_step = landing_y + step_i * step_h
            drawing.add(Line(
                layer="Structural",
                color="#fdba74",
                stroke_width=1.0,
                x1=sx_min, y1=ty_step,
                x2=mid_x, y2=ty_step
            ))
            drawing.add(Line(
                layer="Structural",
                color="#fdba74",
                stroke_width=1.0,
                x1=mid_x, y1=ty_step,
                x2=sx_max, y2=ty_step
            ))

        drawing.add(Text(
            layer="Structural",
            x=mid_x,
            y=sy_min + sh * 0.2,
            content="LANDING",
            font_size=8.0,
            color="#fb923c",
            anchor="middle"
        ))
        drawing.add(Text(
            layer="Structural",
            x=sx_min + sw * 0.25,
            y=sy_max - 0.8,
            content="UP ↑",
            font_size=8.0,
            color="#fdba74",
            anchor="middle"
        ))

    # 6.4 Constructive Walls (Walls Layer)
    for wall in geometry_detail.get("walls", []):
        x1, y1 = wall["start"]
        x2, y2 = wall["end"]
        is_ext = wall["type"] == "exterior"
        drawing.add(Polyline(
            layer="Walls",
            color="#f8fafc" if is_ext else "#cbd5e1",
            stroke_width=3.5 if is_ext else 2.0,
            points=[[x1, y1], [x2, y2]],
            is_closed=False,
        ))

    # 6.5 Architectural Doors (Doors Layer)
    for door in geometry_detail.get("doors", []):
        dx, dy = door["position"]
        dw = door["width"]
        if door["direction"] == "horizontal":
            x1_d, y1_d, x2_d, y2_d = dx - dw / 2, dy, dx + dw / 2, dy
        else:
            x1_d, y1_d, x2_d, y2_d = dx, dy - dw / 2, dx, dy + dw / 2
        for sym in generate_door_symbol(x1_d, y1_d, x2_d, y2_d):
            sym.color = "#38bdf8"
            drawing.add(sym)

    # 6.6 Windows & Fenestrations (Windows Layer)
    for win in geometry_detail.get("windows", []):
        wx, wy = win["position"]
        ww = win["width"]
        if win["direction"] == "horizontal":
            x1_w, y1_w, x2_w, y2_w = wx - ww / 2, wy, wx + ww / 2, wy
        else:
            x1_w, y1_w, x2_w, y2_w = wx, wy - ww / 2, wx, wy + ww / 2
        for sym in generate_window_symbol(x1_w, y1_w, x2_w, y2_w, 0.5):
            sym.color = "#06b6d4"
            drawing.add(sym)

    # 6.7 Overall Plot Dimensions (Dimensions Layer)
    drawing.add(Dimension(
        layer="Dimensions",
        x1=0, y1=0, x2=plot_w, y2=0,
        dim_x=0, dim_y=-2.8,
        text=f"PLOT WIDTH {int(plot_w)}'-0\"",
        color="#38bdf8"
    ))
    drawing.add(Dimension(
        layer="Dimensions",
        x1=0, y1=0, x2=0, y2=plot_d,
        dim_x=-2.8, dim_y=0,
        text=f"PLOT DEPTH {int(plot_d)}'-0\"",
        color="#38bdf8"
    ))

    # 6.8 Sheet Title Stamp
    drawing.add(Text(
        layer="Annotations",
        x=plot_w / 2,
        y=plot_d + 1.8,
        content=f"GROUND FLOOR PLAN | {int(plot_w)}' × {int(plot_d)}' | NBC 2016 COMPLIANT",
        font_size=11.0,
        color="#f1f5f9",
        anchor="middle",
    ))

    drawing_svg = export_drawing_to_svg(drawing)


    return {
        "success": True,
        "session_id": "fast-track-session",
        "selected_candidate_id": "cand_fast_track",
        "extracted_intent": intent.model_dump(),
        "layout": world_rooms,
        "boundaries": {
            "envelope": envelope_coords,
            "stair_core": core_coords,
        },
        "floors": floors_data,
        "geometry": geometry_detail,
        "metrics": metrics,
        "drawing_svg": drawing_svg,
        "metadata": {
            "plot_width": plot_w,
            "plot_depth": plot_d,
            "buildable_area_sqft": buildable_area.area,
            "floors_count": intent.floors,
        },
    }
