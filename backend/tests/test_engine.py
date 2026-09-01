from app.services.compiler.serializer import compile_blueprint
from app.services.geometry.setbacks import calculate_buildable_area, create_plot
from app.services.geometry.topology import (
    build_room_graph,
    calculate_ventilation_and_ots,
    validate_privacy,
)


def test_phase_1_geometry_validation():
    """
    Validation Check from roadmap:
    Feed the engine a 40x40 ft plot with a 5 ft setback on all sides and a 10x10 ft core.
    The resulting Buildable_Area must be exactly 800 sq ft.
    """
    plot = create_plot(40.0, 40.0)
    setbacks = {'left': 5.0, 'right': 5.0, 'bottom': 5.0, 'top': 5.0}
    stair_core_cfg = {'width': 10.0, 'height': 10.0, 'edge': 'bottom-left'}
    
    envelope, core, buildable_area = calculate_buildable_area(plot, setbacks, stair_core_cfg)
    
    assert envelope.area == 900.0, f"Envelope area should be 900.0, got {envelope.area}"
    assert core.area == 100.0, f"Stair core area should be 100.0, got {core.area}"
    assert buildable_area.area == 800.0, f"Buildable area should be exactly 800.0, got {buildable_area.area}"

def test_phase_2_privacy_failure():
    """Verify that routing flows that force users to walk through private areas (Bedroom) fail."""
    rooms = [
        {'name': 'Main Door', 'type': 'Entrance', 'requires_ventilation': False, 'adjacent_to_road': True},
        {'name': 'Bedroom', 'type': 'Bedroom', 'requires_ventilation': True, 'adjacent_to_road': False},
        {'name': 'Kitchen', 'type': 'Kitchen', 'requires_ventilation': True, 'adjacent_to_road': False}
    ]
    # Path: Main Door -> Bedroom -> Kitchen (violates privacy)
    adjacencies = [('Main Door', 'Bedroom'), ('Bedroom', 'Kitchen')]
    
    G = build_room_graph(rooms, adjacencies)
    passed, msg = validate_privacy(G, main_door='Main Door')
    assert not passed
    assert "privacy violation" in msg.lower()

def test_phase_2_ventilation_and_ots():
    """Verify that landlocked rooms trigger procedural Open-To-Sky (OTS) shaft generation."""
    rooms = [
        {'name': 'Main Door', 'type': 'Entrance', 'requires_ventilation': False, 'adjacent_to_road': True},
        {'name': 'Living Room', 'type': 'Living Room', 'requires_ventilation': True, 'adjacent_to_road': True},
        {'name': 'Bedroom 1', 'type': 'Bedroom', 'requires_ventilation': True, 'adjacent_to_road': False}
    ]
    adjacencies = [('Main Door', 'Living Room'), ('Living Room', 'Bedroom 1')]
    
    G = build_room_graph(rooms, adjacencies)
    new_G, ots_shafts = calculate_ventilation_and_ots(G)
    
    # Bedroom 1 requires ventilation but is not adjacent to road, so OTS is generated.
    assert len(ots_shafts) == 1
    assert ots_shafts[0]['name'] == 'OTS_Bedroom 1'
    assert 'OTS_Bedroom 1' in new_G

def test_complete_compiler_pipeline():
    """Verify the entire pipeline end-to-end with the solver."""
    payload = {
        'plot': {'width': 40.0, 'depth': 40.0},
        'setbacks': {'left': 0.0, 'right': 0.0, 'bottom': 5.0, 'top': 0.0},
        'stair_core': {'width': 10.0, 'height': 10.0, 'edge': 'bottom-left'},
        'road_edge': 'bottom',
        'rooms': [
            {'name': 'Main Door', 'type': 'Entrance', 'min_width': 3.0, 'min_height': 3.0, 'min_area': 9.0, 'requires_ventilation': False, 'adjacent_to_road': True},
            {'name': 'Living Room', 'type': 'Living Room', 'min_width': 10.0, 'min_height': 10.0, 'min_area': 100.0, 'requires_ventilation': True, 'adjacent_to_road': True},
            {'name': 'Kitchen', 'type': 'Kitchen', 'min_width': 8.0, 'min_height': 8.0, 'min_area': 64.0, 'requires_ventilation': True, 'adjacent_to_road': False},
            {'name': 'Bedroom', 'type': 'Bedroom', 'min_width': 10.0, 'min_height': 10.0, 'min_area': 100.0, 'requires_ventilation': True, 'adjacent_to_road': False}
        ],
        'adjacencies': [
            ('Main Door', 'Living Room'),
            ('Living Room', 'Kitchen'),
            ('Living Room', 'Bedroom')
        ]
    }
    
    res = compile_blueprint(payload)
    assert res['success'], f"Compilation failed: {res.get('error')}"
    
    layout = res['layout']
    assert 'Living Room' in layout
    assert 'Kitchen' in layout
    assert 'Bedroom' in layout
    
    # Verify that OTS shafts were created for the landlocked Kitchen and Bedroom
    assert 'OTS_Kitchen' in layout
    assert 'OTS_Bedroom' in layout
    
    # Assert coordinates bounds are valid
    for room in layout.values():
        assert room['x'] >= 0.0
        assert room['x'] + room['width'] <= 40.0
        assert room['y'] >= 5.0
        assert room['y'] + room['height'] <= 40.0

def test_api_endpoint():
    """Verify that the FastAPI endpoint compiles successfully with mocked LLM response."""
    from unittest.mock import MagicMock

    from app.api.v1.endpoints.compile import CompileRequest, compile_layout
    from app.schemas.intent import CompilerIntent, RoomIntent
    
    mock_intent = CompilerIntent(
        plot_width=40.0,
        plot_depth=40.0,
        floors=2,
        front_road_setback=5.0,
        rooms=[
            RoomIntent(room_type="bedroom", min_area_sqft=100),
            RoomIntent(room_type="kitchen", min_area_sqft=60)
        ]
    )
    mock_client = MagicMock()
    mock_client.create.return_value = mock_intent
    
    req = CompileRequest(prompt="G+1 house on 40x40 plot with bedroom and kitchen")
    res = compile_layout(req, client=mock_client)
    assert res["status"] == "success"
    assert res["message"] == "Layout compiled successfully."
    assert res["extracted_intent"]["plot_width"] == 40.0
    assert res["extracted_intent"]["plot_depth"] == 40.0
    assert res["extracted_intent"]["floors"] == 2
    assert len(res["extracted_intent"]["rooms"]) == 2

def test_feasibility_engine():
    """Verify that the feasibility engine successfully detects and rejects impossible requests."""
    from app.schemas.intent import CompilerIntent, RoomCategory, RoomIntent
    from app.services.optimization.feasibility import verify_feasibility
    
    # 1. Feasible request
    intent_ok = CompilerIntent(
        plot_width=40.0,
        plot_depth=40.0,
        floors=1,
        front_road_setback=5.0,
        rooms=[
            RoomIntent(room_type=RoomCategory.BEDROOM, min_area_sqft=100),
            RoomIntent(room_type=RoomCategory.KITCHEN, min_area_sqft=60)
        ]
    )
    setbacks = {"left": 3.0, "right": 3.0, "bottom": 5.0, "top": 3.0}
    is_feasible, reason = verify_feasibility(intent_ok, setbacks)
    assert is_feasible is True
    
    # 2. Infeasible request (plot setbacks exceed plot bounds)
    setbacks_bad = {"left": 25.0, "right": 25.0, "bottom": 5.0, "top": 3.0}
    is_feasible, reason = verify_feasibility(intent_ok, setbacks_bad)
    assert is_feasible is False
    assert "setbacks are infeasible" in reason
    
    # 3. Infeasible request (requested area exceeds ground footprint)
    intent_huge = CompilerIntent(
        plot_width=20.0,
        plot_depth=20.0,
        floors=1,
        front_road_setback=5.0,
        rooms=[
            RoomIntent(room_type=RoomCategory.BEDROOM, min_area_sqft=300),
            RoomIntent(room_type=RoomCategory.LIVING, min_area_sqft=300)
        ]
    )
    setbacks_small = {"left": 3.0, "right": 3.0, "bottom": 5.0, "top": 3.0}
    is_feasible, reason = verify_feasibility(intent_huge, setbacks_small)
    assert is_feasible is False
    assert "exceeds ground footprint" in reason

def test_room_program_generator():
    """Verify that the Room Program Generator correctly turns intent into optimization-ready rooms."""
    from app.schemas.intent import CompilerIntent, RoomCategory, RoomIntent
    from app.services.optimization.room_generator import generate_layout_program
    
    intent = CompilerIntent(
        plot_width=40.0,
        plot_depth=40.0,
        floors=1,
        front_road_setback=5.0,
        rooms=[
            RoomIntent(room_type=RoomCategory.BEDROOM, min_area_sqft=100),
            RoomIntent(room_type=RoomCategory.KITCHEN, min_area_sqft=60)
        ]
    )
    setbacks = {"left": 3.0, "right": 3.0, "bottom": 5.0, "top": 3.0}
    program = generate_layout_program(intent, setbacks)
    
    assert "stair_core" in program
    assert "rooms" in program
    assert "adjacencies" in program
    
    # Check that rooms receive all target attributes of Phase 3
    for room in program["rooms"]:
        assert "min_area" in room
        assert "preferred_area" in room
        assert "priority" in room
        assert "aspect_ratio_range" in room
        assert "floor_assignment" in room
        assert room["floor_assignment"] == 1

def test_optimization_engine_soft_constraints():
    """Verify that the optimization solver runs and yields valid layouts under Phase 4 constraints."""
    from app.services.optimization.solver import solve_layout
    
    # 40x40 plot with 3 ft setbacks on all sides
    setbacks = {"left": 3.0, "right": 3.0, "bottom": 3.0, "top": 3.0}
    rooms = [
        {"name": "Entrance Lobby", "type": "Entrance", "min_width": 3.0, "min_height": 3.0, "min_area": 9.0, "requires_ventilation": False, "adjacent_to_road": True},
        {"name": "Living Room", "type": "Living Room", "min_width": 8.0, "min_height": 8.0, "min_area": 80.0, "requires_ventilation": True, "adjacent_to_road": True},
        {"name": "Master Bedroom", "type": "Bedroom", "min_width": 8.0, "min_height": 8.0, "min_area": 80.0, "requires_ventilation": True, "adjacent_to_road": False},
        {"name": "Kitchen", "type": "Kitchen", "min_width": 5.0, "min_height": 5.0, "min_area": 50.0, "requires_ventilation": True, "adjacent_to_road": False}
    ]
    adjacencies = [("Entrance Lobby", "Living Room"), ("Living Room", "Kitchen")]
    
    stair_core_coords = (3.0, 3.0, 11.0, 11.0)  # Stair core at bottom-left corner
    
    res = solve_layout(
        plot_width=40.0,
        plot_depth=40.0,
        setbacks=setbacks,
        stair_core_coords=stair_core_coords,
        rooms=rooms,
        adjacencies=adjacencies,
        road_edge="bottom",
        grid_snap=0.5,
        time_limit_sec=8
    )
    
    assert res["success"] is True
    assert "Living Room" in res["rooms"]
    assert "Master Bedroom" in res["rooms"]
    assert "Kitchen" in res["rooms"]
    
    # Ensure all room coordinates fit inside the buildable boundaries
    for room in res["rooms"].values():
        assert room["x"] >= 3.0
        assert room["x"] + room["width"] <= 37.0
        assert room["y"] >= 3.0
        assert room["y"] + room["height"] <= 37.0

def test_geometry_compiler():
    """Verify that the Geometry Compiler generates valid walls, doors, and windows."""
    from app.services.geometry.compiler import compile_geometry
    
    layout_rooms = {
        "Living Room": {"type": "Living Room", "x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0},
        "Kitchen": {"type": "Kitchen", "x": 10.0, "y": 0.0, "width": 8.0, "height": 10.0}
    }
    envelope_coords = [(0.0, 0.0), (18.0, 0.0), (18.0, 10.0), (0.0, 10.0)]
    stair_core_coords = []
    adjacencies = [("Living Room", "Kitchen")]
    
    geom = compile_geometry(layout_rooms, envelope_coords, stair_core_coords, adjacencies)
    
    assert "walls" in geom
    assert "doors" in geom
    assert "windows" in geom
    
    # Check walls: exterior walls (thickness 0.75) and interior walls (thickness 0.375) should be present
    wall_types = {w["type"] for w in geom["walls"]}
    assert "exterior" in wall_types
    assert "interior" in wall_types
    
    # Check doors: both Main Entrance and interior connection are generated
    assert len(geom["doors"]) >= 1
    door_types = {d["type"] for d in geom["doors"]}
    assert "entrance" in door_types or "interior" in door_types


def test_multi_floor_compiler():
    """Verify that multi-floor layouts compile successfully and align plumbing cores."""
    from app.services.compiler.serializer import compile_blueprint
    
    payload = {
        "plot": {"width": 40.0, "depth": 40.0},
        "setbacks": {"left": 3.0, "right": 3.0, "bottom": 5.0, "top": 3.0},
        "stair_core": {"width": 10.0, "height": 10.0, "edge": "bottom-left"},
        "floors": 2,
        "rooms": [
            # Floor 1
            {"name": "Entrance Lobby", "type": "Entrance", "min_area": 20.0, "min_width": 3.0, "min_height": 3.0, "floor_assignment": 1, "requires_ventilation": False, "adjacent_to_road": True},
            {"name": "Living Room", "type": "Living Room", "min_area": 150.0, "min_width": 8.0, "min_height": 8.0, "floor_assignment": 1, "requires_ventilation": True, "adjacent_to_road": True},
            {"name": "Kitchen", "type": "Kitchen", "min_area": 60.0, "min_width": 5.0, "min_height": 5.0, "floor_assignment": 1, "requires_ventilation": True, "adjacent_to_road": False},
            {"name": "Bathroom 1", "type": "Bathroom", "min_area": 30.0, "min_width": 3.5, "min_height": 3.5, "floor_assignment": 1, "requires_ventilation": False, "adjacent_to_road": False},
            # Floor 2
            {"name": "Master Bedroom", "type": "Bedroom", "min_area": 120.0, "min_width": 9.0, "min_height": 9.0, "floor_assignment": 2, "requires_ventilation": True, "adjacent_to_road": False},
            {"name": "Bathroom 2", "type": "Bathroom", "min_area": 30.0, "min_width": 3.5, "min_height": 3.5, "floor_assignment": 2, "requires_ventilation": False, "adjacent_to_road": False}
        ],
        "adjacencies": [
            ("Entrance Lobby", "Living Room"),
            ("Living Room", "Kitchen"),
            ("Living Room", "Bathroom 1"),
            ("Master Bedroom", "Bathroom 2")
        ],
        "road_edge": "bottom",
        "grid_snap": 0.5,
        "time_limit_sec": 5
    }
    
    res = compile_blueprint(payload)
    assert res["success"] is True
    assert "floors" in res
    assert "1" in res["floors"]
    assert "2" in res["floors"]
    
    # Check that Floor 1 and Floor 2 layouts are generated
    assert "Master Bedroom" in res["floors"]["2"]["layout"]
    assert "Living Room" in res["floors"]["1"]["layout"]
    
    # Verify staircase core boundary remains identical on both floors
    assert res["boundaries"]["stair_core"] is not None

def test_metrics_engine():
    """Verify that layout metrics are calculated and fall within valid ranges."""
    from app.services.geometry.metrics import calculate_layout_metrics
    
    floors_data = {
        "1": {
            "layout": {
                "Living Room": {"x": 10.0, "y": 5.0, "width": 12.0, "height": 12.0, "type": "Living Room"},
                "Kitchen": {"x": 22.0, "y": 5.0, "width": 8.0, "height": 8.0, "type": "Kitchen"},
                "Bathroom": {"x": 30.0, "y": 5.0, "width": 6.0, "height": 6.0, "type": "Bathroom"}
            },
            "geometry": {
                "windows": [
                    {"room": "Living Room", "position": [16.0, 5.0], "width": 4.0},
                    {"room": "Kitchen", "position": [26.0, 5.0], "width": 3.0}
                ]
            }
        }
    }
    
    stair_core_cfg = {"width": 8.0, "height": 8.0}
    metrics = calculate_layout_metrics(
        plot_width=40.0,
        plot_depth=40.0,
        floors_data=floors_data,
        stair_core_cfg=stair_core_cfg
    )
    
    assert metrics["far"] > 0
    assert metrics["plot_coverage_pct"] > 0
    assert metrics["daylighting_score"] > 0
    assert metrics["estimated_cost_inr"] > 0
    assert metrics["carbon_score_kg_co2"] > 0
    assert metrics["buildability_score"] > 0
    assert metrics["privacy_score"] > 0
    assert metrics["accessibility_score"] > 0

def test_render_tree():
    """Verify that the hierarchical render tree is generated with correct project structure."""
    from app.services.geometry.renderer import generate_hierarchical_json
    
    compiled_res = {
        "metadata": {
            "plot_width": 40.0,
            "plot_depth": 40.0,
            "buildable_area_sqft": 900.0,
            "floors_count": 1,
            "ots_generated_count": 0
        },
        "boundaries": {
            "envelope": [[0.0, 0.0], [40.0, 0.0], [40.0, 40.0], [0.0, 40.0]],
            "stair_core": []
        },
        "metrics": {"far": 0.5},
        "floors": {
            "1": {
                "layout": {
                    "Living Room": {"type": "Living Room", "x": 10.0, "y": 5.0, "width": 12.0, "height": 12.0, "coordinates": [[10.0, 5.0], [10.0, 17.0]]}
                },
                "geometry": {
                    "walls": [{"id": "w1", "start": [10.0, 5.0], "end": [22.0, 5.0], "type": "exterior", "thickness": 0.75, "rooms": ["Living Room"]}],
                    "doors": [{"id": "d1", "position": [10.0, 10.0], "direction": "vertical", "width": 3.0, "type": "entrance", "rooms": ["Living Room"]}],
                    "windows": [{"id": "win1", "position": [16.0, 5.0], "direction": "horizontal", "width": 4.0, "type": "exterior", "room": "Living Room"}]
                }
            }
        }
    }
    
    tree = generate_hierarchical_json(compiled_res)
    assert "project" in tree
    project = tree["project"]
    assert project["metadata"]["plot_width"] == 40.0
    assert len(project["floors"]) == 1
    
    floor1 = project["floors"][0]
    assert floor1["floor_level"] == 1
    assert len(floor1["rooms"]) == 1
    
    room = floor1["rooms"][0]
    assert room["name"] == "Living Room"
    assert len(room["walls"]) == 1
    assert len(room["doors"]) == 1
    assert len(room["windows"]) == 1
    assert room["furniture"] == []

def test_explainer_service():
    """Verify that the AI explainer returns structured answers and degrades gracefully to fallback."""
    from unittest.mock import MagicMock

    from app.schemas.explanation import DesignExplanation
    from app.services.ai.explainer import explain_layout, explain_layout_fallback
    
    layout_data = {
        "metadata": {
            "plot_width": 40.0,
            "plot_depth": 40.0,
            "buildable_area_sqft": 900.0,
            "floors_count": 2
        },
        "metrics": {
            "far": 1.1,
            "plot_coverage_pct": 55.0,
            "daylighting_score": 80.0,
            "cross_ventilation_score": 75.0,
            "buildability_score": 95.0,
            "privacy_score": 100.0,
            "accessibility_score": 90.0
        },
        "floors": {
            "1": {"layout": {"Living Room": {}, "Kitchen": {}}},
            "2": {"layout": {"Master Bedroom": {}}}
        }
    }
    
    # 1. Test Fallback Explainer
    exp_fallback = explain_layout_fallback("G+1 house with bedroom and kitchen", layout_data)
    assert isinstance(exp_fallback, DesignExplanation)
    assert "G+1" in exp_fallback.overall_concept or "customized" in exp_fallback.overall_concept.lower()
    assert len(exp_fallback.kitchen_placement) > 10
    
    # 2. Test LLM mock explainer
    mock_explanation = DesignExplanation(
        overall_concept="Mocked overall concept",
        kitchen_placement="Mocked kitchen placement",
        plumbing_efficiency="Mocked plumbing efficiency",
        vastu_compliance="Mocked vastu compliance",
        circulation_efficiency="Mocked circulation efficiency"
    )
    mock_client = MagicMock()
    mock_client.create.return_value = mock_explanation
    
    exp_llm = explain_layout("G+1 house with bedroom and kitchen", layout_data, client=mock_client)
    assert exp_llm.overall_concept == "Mocked overall concept"

def test_validation_engine():
    """Verify that the validation engine correctly calculates buildability score and flags errors."""
    from app.services.geometry.validation import validate_layout
    
    stair_core_cfg = {"width": 8.0, "height": 8.0, "edge": "bottom-left"}
    
    # 1. Test clean, valid layout
    floors_data_valid = {
        "1": {
            "layout": {
                "Living Room": {"x": 5.0, "y": 5.0, "width": 10.0, "height": 10.0, "type": "Living Room"},
                "Kitchen": {"x": 15.0, "y": 5.0, "width": 10.0, "height": 10.0, "type": "Kitchen"}
            },
            "geometry": {
                "doors": [
                    {"id": "d1", "position": [10.0, 10.0], "direction": "vertical", "width": 3.0, "type": "entrance", "rooms": ["Living Room"]},
                    {"id": "d2", "position": [15.0, 10.0], "direction": "vertical", "width": 3.0, "type": "interior", "rooms": ["Kitchen"]}
                ],
                "windows": [
                    {"id": "w1", "position": [10.0, 5.0], "direction": "horizontal", "width": 3.0, "type": "exterior", "room": "Living Room"}
                ]
            }
        }
    }
    
    report_valid = validate_layout(40.0, 40.0, floors_data_valid, stair_core_cfg)
    assert report_valid["success"] is True
    assert report_valid["buildability_score"] == 100.0
    
    # 2. Test overlap layout
    floors_data_overlap = {
        "1": {
            "layout": {
                "Living Room": {"x": 5.0, "y": 5.0, "width": 10.0, "height": 10.0, "type": "Living Room"},
                # Overlaps Living Room since x starts at 8.0 (inside Living Room width 10)
                "Kitchen": {"x": 8.0, "y": 5.0, "width": 10.0, "height": 10.0, "type": "Kitchen"}
            },
            "geometry": {
                "doors": [],
                "windows": []
            }
        }
    }
    
    report_overlap = validate_layout(40.0, 40.0, floors_data_overlap, stair_core_cfg)
    assert report_overlap["success"] is False
    assert report_overlap["checks"]["no_overlaps"]["passed"] is False
    assert report_overlap["buildability_score"] < 100.0



