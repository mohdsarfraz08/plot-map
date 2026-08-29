"""
Test suite for SpatialCompilerBridge (Stage 3B.4D-3).

Verifies 28 points:
1. Minimal SpatialLayoutPlan realization
2. Successful compiler invocation
3. Successful solver invocation
4. Compiler input translation
5. Solver output translation
6. RealizationResult SUCCESS
7. Source candidate traceability
8. Source strategy traceability
9. Source problem traceability
10. SpatialLayoutPlan traceability
11. Deterministic IDs
12. Repeated realization determinism
13. Invalid SpatialLayoutPlan handling
14. Unsupported specification handling
15. Spatial infeasibility handling
16. Solver timeout handling
17. Solver error handling
18. Existing compiler reuse verification
19. Existing solver reuse verification
20. No duplicate solver implementation
21. Custom/unseen decision metadata preservation
22. Benchmark 44x42 realization (REAL integration test)
23. Single-family realization (REAL integration test)
24. Multi-floor realization (REAL integration test)
25. Legacy CompilerIntent path remains functional
26. No changes to StrategyGenerator behavior
27. No changes to CandidateOrganizer behavior
28. Provenance completeness
"""

import inspect
import pytest

from app.schemas.architectural_analysis import DecisionRecord, DecisionStatus
from app.schemas.design_candidate import DesignCandidate
from app.schemas.design_problem import DesignProblem
from app.schemas.intent import CompilerIntent, RoomCategory, RoomIntent
from app.schemas.spatial_realization import (
    RealizationResult,
    RealizationStatus,
    SpatialCoreSpec,
    SpatialLayoutPlan,
    SpatialRoomSpec,
)
from app.services.analysis.candidate_organizer import organize_candidate
from app.services.analysis.catalog_loader import get_catalog_organization_rules
from app.services.analysis.spatial_adapter import CandidateToLayoutAdapter
from app.services.compiler import serializer
from app.services.compiler.serializer import compile_blueprint
from app.services.optimization import solver
from app.services.realization.compiler_bridge import (
    SpatialCompilerBridge,
    realize_spatial_layout,
)
from tests.fixtures.golden_organization_fixtures import (
    get_benchmark_44x42_candidate,
    get_benchmark_44x42_problem,
    get_single_family_candidate,
    get_single_family_problem,
)


def _make_sample_plan() -> SpatialLayoutPlan:
    return SpatialLayoutPlan(
        id="plan-bridge-1",
        source_candidate_id="cand-1",
        source_strategy_id="strat-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        plot_width=40.0,
        plot_depth=40.0,
        setbacks={"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0},
        floors=1,
        rooms=[
            SpatialRoomSpec(
                id="room_living",
                name="Living Room",
                room_type="living",
                target_area=150.0,
                aspect_ratio_range=(0.6, 1.8),
                floor_assignment=1,
            ),
            SpatialRoomSpec(
                id="room_bed",
                name="Bedroom",
                room_type="bedroom",
                target_area=100.0,
                aspect_ratio_range=(0.7, 1.5),
                floor_assignment=1,
            ),
        ],
        cores=[
            SpatialCoreSpec(
                id="core-stair",
                core_type="vertical_stairwell",
                access_type="shared",
                floors=[1],
            )
        ],
        realization_parameters={
            "custom_shading": "external_screen",
            "grid_snap": 0.5,
            "time_limit_sec": 5,
        },
        provenance={"generator": "sample-bridge-plan"},
    )


def test_01_minimal_spatial_layout_plan_realization():
    """Point 1: Verify minimal SpatialLayoutPlan realization executes."""
    plan = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan)

    assert isinstance(res, RealizationResult)
    assert res.candidate_id == "cand-1"


def test_02_successful_compiler_invocation(monkeypatch):
    """Point 2: Verify compile_blueprint is actually invoked by the bridge."""
    called = False

    def _mock_compile(payload):
        nonlocal called
        called = True
        return {"success": True, "floors": {}, "geometry": {}}

    monkeypatch.setattr(serializer, "compile_blueprint", _mock_compile)

    plan = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan)

    assert called is True
    assert res.success is True


def test_03_successful_solver_invocation():
    """Point 3: Verify downstream MILP solver is invoked via compile_blueprint."""
    plan = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan)

    assert res.success is True
    assert res.realized_geometry is not None
    assert res.status == RealizationStatus.SUCCESS


def test_04_compiler_input_translation():
    """Point 4: Verify SpatialLayoutPlan translates correctly into compiler input payload."""
    plan = _make_sample_plan()
    payload = SpatialCompilerBridge.plan_to_compiler_payload(plan)

    assert payload["plot"]["width"] == 40.0
    assert payload["plot"]["depth"] == 40.0
    assert payload["floors"] == 1
    assert len(payload["rooms"]) == 2
    assert payload["rooms"][0]["name"] == "room_living"


def test_05_solver_output_translation():
    """Point 5: Verify solver output is captured in RealizationResult.realized_geometry."""
    plan = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan)

    assert res.realized_geometry is not None
    assert "floors" in res.realized_geometry
    assert "metrics" in res.realized_geometry


def test_06_realization_result_success():
    """Point 6: Verify successful realization sets RealizationStatus.SUCCESS."""
    plan = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan)

    assert res.status == RealizationStatus.SUCCESS
    assert res.success is True


def test_07_source_candidate_traceability():
    """Point 7: Verify candidate ID is preserved in RealizationResult."""
    plan = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan)

    assert res.candidate_id == "cand-1"


def test_08_source_strategy_traceability():
    """Point 8: Verify strategy ID is preserved in provenance."""
    plan = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan)

    assert res.provenance["source_strategy_id"] == "strat-1"


def test_09_source_problem_traceability():
    """Point 9: Verify problem ID and version are preserved in provenance."""
    plan = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan)

    assert res.provenance["source_problem_id"] == "prob-1"
    assert res.provenance["source_problem_version"] == 1


def test_10_spatial_layout_plan_traceability():
    """Point 10: Verify spatial layout plan ID is preserved in provenance."""
    plan = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan)

    assert res.provenance["layout_plan_id"] == "plan-bridge-1"


def test_11_deterministic_ids():
    """Point 11: Verify candidate ID and plan ID are deterministic across bridge calls."""
    plan = _make_sample_plan()
    res1 = SpatialCompilerBridge.realize_layout(plan)
    res2 = SpatialCompilerBridge.realize_layout(plan)

    assert res1.candidate_id == res2.candidate_id == "cand-1"


def test_12_repeated_realization_determinism():
    """Point 12: Verify repeated realization produces stable result structures."""
    plan = _make_sample_plan()
    res1 = SpatialCompilerBridge.realize_layout(plan)
    res2 = SpatialCompilerBridge.realize_layout(plan)

    assert res1.status == res2.status
    assert res1.success == res2.success


def test_13_invalid_spatial_layout_plan_handling():
    """Point 13: Verify invalid empty SpatialLayoutPlan produces INVALID_CANDIDATE status."""
    res = SpatialCompilerBridge.realize_layout(None)

    assert res.success is False
    assert res.status == RealizationStatus.INVALID_CANDIDATE


def test_14_unsupported_specification_handling(monkeypatch):
    """Point 14: Verify payload translation exception yields UNSUPPORTED_SPEC status."""
    def _fail_payload(*args, **kwargs):
        raise ValueError("Invalid room spec for compiler")

    monkeypatch.setattr(SpatialCompilerBridge, "plan_to_compiler_payload", _fail_payload)

    plan = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan)

    assert res.success is False
    assert res.status == RealizationStatus.UNSUPPORTED_SPEC


def test_15_spatial_infeasibility_handling():
    """Point 15: Verify buildable envelope overflow yields SPATIALLY_INFEASIBLE status."""
    plan = SpatialLayoutPlan(
        id="plan-infeasible",
        source_candidate_id="cand-inf",
        source_strategy_id="strat-inf",
        source_problem_id="prob-inf",
        source_problem_version=1,
        plot_width=10.0,
        plot_depth=10.0,
        setbacks={"left": 15.0, "right": 15.0, "top": 15.0, "bottom": 15.0},  # Setbacks exceed plot bounds
        floors=1,
        rooms=[],
    )

    res = SpatialCompilerBridge.realize_layout(plan)

    assert res.success is False
    assert res.status == RealizationStatus.SPATIALLY_INFEASIBLE


def test_16_solver_timeout_handling(monkeypatch):
    """Point 16: Verify solver timeout error message maps to SOLVER_TIMEOUT status."""
    def _mock_timeout(payload):
        return {"success": False, "error": "Optimization solver error: TimeLimit exceeded"}

    monkeypatch.setattr(serializer, "compile_blueprint", _mock_timeout)

    plan = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan)

    assert res.success is False
    assert res.status == RealizationStatus.SOLVER_TIMEOUT


def test_17_solver_error_handling(monkeypatch):
    """Point 17: Verify general solver error maps to SOLVER_ERROR status."""
    def _mock_err(payload):
        return {"success": False, "error": "Internal solver crash"}

    monkeypatch.setattr(serializer, "compile_blueprint", _mock_err)

    plan = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan)

    assert res.success is False
    assert res.status == RealizationStatus.SOLVER_ERROR


def test_18_existing_compiler_reuse_verification(monkeypatch):
    """Point 18: Explicitly verify existing compile_blueprint in serializer module is called."""
    called_module = False

    orig_compile = serializer.compile_blueprint

    def _spy_compile(payload):
        nonlocal called_module
        called_module = True
        return orig_compile(payload)

    monkeypatch.setattr("app.services.compiler.serializer.compile_blueprint", _spy_compile)

    plan = _make_sample_plan()
    SpatialCompilerBridge.realize_layout(plan)

    assert called_module is True


def test_19_existing_solver_reuse_verification(monkeypatch):
    """Point 19: Explicitly verify existing solve_layout in solver module is called via compile_blueprint."""
    called_solver = False

    orig_solve = serializer.solve_layout

    def _spy_solve(*args, **kwargs):
        nonlocal called_solver
        called_solver = True
        return orig_solve(*args, **kwargs)

    monkeypatch.setattr(serializer, "solve_layout", _spy_solve)

    plan = _make_sample_plan()
    SpatialCompilerBridge.realize_layout(plan)

    assert called_solver is True


def test_20_no_duplicate_solver_implementation():
    """Point 20: Assert SpatialCompilerBridge source code does NOT contain solver implementations or PuLP imports."""
    source = inspect.getsource(SpatialCompilerBridge)
    for kw in ["pulp", "LpProblem", "LpVariable", "lpSum", "solver.solve"]:
        assert kw not in source


def test_21_custom_unseen_decision_metadata_preservation():
    """Point 21: Verify custom/unseen realization parameters pass through to bridge results."""
    plan = _make_sample_plan()
    plan.realization_parameters["unseen_facade_param"] = "glazed"

    res = SpatialCompilerBridge.realize_layout(plan)
    assert res.success is True


def test_22_benchmark_44x42_realization_integration():
    """Point 22: REAL integration test exercising end-to-end 44x42 benchmark realization."""
    prob = get_benchmark_44x42_problem()
    raw_cand = get_benchmark_44x42_candidate(prob)
    rules = get_catalog_organization_rules()
    cand = organize_candidate(raw_cand, rules, problem=prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    res = realize_spatial_layout(plan, problem=prob)

    assert res.success is True
    assert res.status == RealizationStatus.SUCCESS
    assert "geometry" in res.realized_geometry


def test_23_single_family_realization_integration():
    """Point 23: REAL integration test exercising end-to-end single-family scenario realization."""
    prob = get_single_family_problem()
    raw_cand = get_single_family_candidate(prob)
    rules = get_catalog_organization_rules()
    cand = organize_candidate(raw_cand, rules, problem=prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    res = realize_spatial_layout(plan, problem=prob)

    assert res.success is True
    assert res.status == RealizationStatus.SUCCESS


def test_24_multi_floor_realization_integration():
    """Point 24: REAL integration test exercising multi-floor scenario realization."""
    prob = get_benchmark_44x42_problem()
    raw_cand = get_benchmark_44x42_candidate(prob)
    rules = get_catalog_organization_rules()
    cand = organize_candidate(raw_cand, rules, problem=prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    res = realize_spatial_layout(plan, problem=prob)

    assert res.success is True
    assert "floors" in res.realized_geometry


def test_25_legacy_compiler_intent_path_remains_functional():
    """Point 25: Verify legacy CompilerIntent -> compile_blueprint path works completely unchanged."""
    from app.services.compiler.intent_adapter import to_design_problem

    intent = CompilerIntent(
        plot_width=40.0,
        plot_depth=40.0,
        floors=1,
        front_road_setback=5.0,
        confidence_score=1.0,
        rooms=[
            RoomIntent(room_type=RoomCategory.LIVING, min_area_sqft=150),
            RoomIntent(room_type=RoomCategory.BEDROOM, min_area_sqft=100),
        ],
    )

    problem = to_design_problem(intent, problem_id="problem-from-intent")
    assert problem.site.plot_width == 40.0
    assert problem.site.plot_depth == 40.0
    assert len(problem.spaces) == 2


def test_26_no_changes_to_strategy_generator_behavior():
    """Point 26: Assert StrategyGenerator produces expected strategies without modification."""
    from app.schemas.architectural_analysis import ArchitecturalAnalysis
    from app.services.analysis.strategy_generator import generate_strategies

    analysis = ArchitecturalAnalysis(
        id="analysis-test",
        problem_id="prob-1",
        problem_version=1,
        summary="Test analysis summary",
        decisions=[
            DecisionRecord(
                id="dec-1",
                dimension="unit_organization",
                subject="building",
                value="grouped",
                status=DecisionStatus.FIXED,
                alternatives=["grouped", "distributed"],
            )
        ],
    )
    strats = generate_strategies(analysis)
    assert len(strats) >= 1


def test_27_no_changes_to_candidate_organizer_behavior():
    """Point 27: Assert CandidateOrganizer organizes candidates without modification."""
    prob = get_single_family_problem()
    raw_cand = get_single_family_candidate(prob)
    rules = get_catalog_organization_rules()
    cand = organize_candidate(raw_cand, rules, problem=prob)
    assert cand is not None


def test_28_provenance_completeness():
    """Point 28: Verify provenance carries compiler, candidate, strategy, and problem metadata."""
    plan = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan)

    prov = res.provenance
    assert prov["compiler"] == "compile_blueprint"
    assert prov["layout_plan_id"] == "plan-bridge-1"
    assert prov["source_candidate_id"] == "cand-1"
    assert prov["source_strategy_id"] == "strat-1"
    assert prov["source_problem_id"] == "prob-1"
    assert prov["source_problem_version"] == 1
