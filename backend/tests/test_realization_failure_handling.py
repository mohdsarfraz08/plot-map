"""
Infeasibility & Failure Handling Test Suite for Stage 3B.4D-5.

Verifies end-to-end realization failure classification across 28 points:
1. Valid candidate still succeeds
2. Invalid candidate returns INVALID_CANDIDATE
3. Missing required source reference is detected
4. Unsupported spatial specification returns UNSUPPORTED_SPEC
5. Spatially infeasible layout returns SPATIALLY_INFEASIBLE
6. Solver timeout is mapped to SOLVER_TIMEOUT
7. Solver error is mapped to SOLVER_ERROR
8. Unexpected compiler exception is normalized
9. Failure result preserves candidate ID
10. Failure result preserves strategy ID
11. Failure result preserves problem ID
12. Failure result preserves problem version
13. Failure result preserves layout plan ID when available
14. Failure provenance is deterministic
15. Repeated failing execution produces identical result
16. Infeasible constraints are preserved when available
17. Failure result never contains realized geometry
18. Successful result still contains realized geometry
19. Legacy CompilerIntent -> compile_blueprint path remains functional
20. Existing compiler is still reused
21. Existing solver is still reused
22. No second solver implementation exists
23. No new geometry engine exists
24. CandidateOrganizer remains unchanged
25. CandidateToLayoutAdapter remains unchanged
26. StrategyGenerator remains unchanged
27. No domain-specific failure branches exist
28. Custom/unseen dimensions still fail/succeed generically
"""

import ast
import inspect
import pytest

from app.schemas.architectural_analysis import DecisionRecord, DecisionStatus
from app.schemas.spatial_realization import (
    RealizationResult,
    RealizationStatus,
    SpatialLayoutPlan,
    SpatialRoomSpec,
)
from app.services.analysis import candidate_organizer, candidate_generator, spatial_adapter, strategy_generator
from app.services.analysis.candidate_organizer import organize_candidate
from app.services.analysis.catalog_loader import get_catalog_organization_rules
from app.services.analysis.spatial_adapter import CandidateToLayoutAdapter
from app.services.compiler import serializer
from app.services.realization import compiler_bridge
from app.services.realization.compiler_bridge import SpatialCompilerBridge, normalize_error_message
from tests.fixtures.golden_spatial_realization_fixtures import (
    get_golden_custom_dimensions_fixture,
    get_golden_single_family_fixture,
)


def _make_sample_plan():
    prob, cand = get_golden_single_family_fixture()
    return CandidateToLayoutAdapter.adapt(cand, prob), prob


def test_01_valid_candidate_still_succeeds():
    """Point 1: Verify valid spatial plan reaches successful realization."""
    plan, prob = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)

    assert res.success is True
    assert res.status == RealizationStatus.SUCCESS


def test_02_invalid_candidate_returns_invalid_candidate():
    """Point 2: Verify null or empty candidate returns INVALID_CANDIDATE."""
    res = SpatialCompilerBridge.realize_layout(None)

    assert res.success is False
    assert res.status == RealizationStatus.INVALID_CANDIDATE
    assert res.realized_geometry is None


def test_03_missing_required_source_reference_is_detected():
    """Point 3: Verify missing required source candidate reference returns INVALID_CANDIDATE."""
    plan, prob = _make_sample_plan()
    plan.source_candidate_id = ""

    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)

    assert res.success is False
    assert res.status == RealizationStatus.INVALID_CANDIDATE


def test_04_unsupported_spatial_specification_returns_unsupported_spec():
    """Point 4: Verify non-positive plot dimensions return UNSUPPORTED_SPEC."""
    plan, prob = _make_sample_plan()
    plan.plot_width = -10.0

    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)

    assert res.success is False
    assert res.status == RealizationStatus.UNSUPPORTED_SPEC


def test_05_spatially_infeasible_layout_returns_spatially_infeasible(monkeypatch):
    """Point 5: Verify buildable area infeasibility returns SPATIALLY_INFEASIBLE."""

    def _mock_compile_infeasible(payload):
        return {"success": False, "error": "Spatially infeasible: Room area exceeds buildable envelope"}

    monkeypatch.setattr(serializer, "compile_blueprint", _mock_compile_infeasible)

    plan, prob = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)

    assert res.success is False
    assert res.status == RealizationStatus.SPATIALLY_INFEASIBLE
    assert len(res.infeasible_constraints) >= 1


def test_06_solver_timeout_is_mapped_to_solver_timeout(monkeypatch):
    """Point 6: Verify solver timeout error returns SOLVER_TIMEOUT."""

    def _mock_compile_timeout(payload):
        return {"success": False, "error": "Solver timelimit 5s exceeded"}

    monkeypatch.setattr(serializer, "compile_blueprint", _mock_compile_timeout)

    plan, prob = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)

    assert res.success is False
    assert res.status == RealizationStatus.SOLVER_TIMEOUT


def test_07_solver_error_is_mapped_to_solver_error(monkeypatch):
    """Point 7: Verify unclassified solver error returns SOLVER_ERROR."""

    def _mock_compile_error(payload):
        return {"success": False, "error": "MILP internal solver crash"}

    monkeypatch.setattr(serializer, "compile_blueprint", _mock_compile_error)

    plan, prob = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)

    assert res.success is False
    assert res.status == RealizationStatus.SOLVER_ERROR


def test_08_unexpected_compiler_exception_is_normalized(monkeypatch):
    """Point 8: Verify unexpected Python runtime exception is caught and normalized."""

    def _mock_compile_raise(payload):
        raise RuntimeError("Unexpected internal crash at 0x7f9a8b1c in C:\\Build\\solver.py")

    monkeypatch.setattr(serializer, "compile_blueprint", _mock_compile_raise)

    plan, prob = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)

    assert res.success is False
    assert res.status == RealizationStatus.SOLVER_ERROR
    assert "0x7f9a8b1c" not in res.error_message


def test_09_failure_result_preserves_candidate_id(monkeypatch):
    """Point 9: Verify candidate ID survives on failure result."""
    plan, prob = _make_sample_plan()
    plan.plot_width = 0.0

    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)
    assert res.candidate_id == plan.source_candidate_id


def test_10_failure_result_preserves_strategy_id():
    """Point 10: Verify strategy ID survives in provenance on failure result."""
    plan, prob = _make_sample_plan()
    plan.plot_width = -1.0

    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)
    assert res.provenance["source_strategy_id"] == plan.source_strategy_id


def test_11_failure_result_preserves_problem_id():
    """Point 11: Verify problem ID survives in provenance on failure result."""
    plan, prob = _make_sample_plan()
    plan.plot_width = -1.0

    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)
    assert res.provenance["source_problem_id"] == plan.source_problem_id


def test_12_failure_result_preserves_problem_version():
    """Point 12: Verify problem version survives in provenance on failure result."""
    plan, prob = _make_sample_plan()
    plan.plot_width = -1.0

    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)
    assert res.provenance["source_problem_version"] == plan.source_problem_version


def test_13_failure_result_preserves_layout_plan_id_when_available():
    """Point 13: Verify layout plan ID survives on failure result."""
    plan, prob = _make_sample_plan()
    plan.plot_width = -1.0

    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)
    assert res.provenance["layout_plan_id"] == plan.id


def test_14_failure_provenance_is_deterministic():
    """Point 14: Verify failure provenance metadata is deterministic."""
    plan, prob = _make_sample_plan()
    plan.plot_width = -1.0

    res_1 = SpatialCompilerBridge.realize_layout(plan, problem=prob)
    res_2 = SpatialCompilerBridge.realize_layout(plan, problem=prob)

    assert res_1.provenance == res_2.provenance


def test_15_repeated_failing_execution_produces_identical_result():
    """Point 15: Verify repeated failure execution produces identical status and error message."""
    plan, prob = _make_sample_plan()
    plan.plot_width = -1.0

    res_1 = SpatialCompilerBridge.realize_layout(plan, problem=prob)
    res_2 = SpatialCompilerBridge.realize_layout(plan, problem=prob)

    assert res_1.status == res_2.status
    assert res_1.error_message == res_2.error_message


def test_16_infeasible_constraints_are_preserved_when_available(monkeypatch):
    """Point 16: Verify infeasible constraint strings are preserved in result."""

    def _mock_infeasible(payload):
        return {"success": False, "error": "Spatially infeasible: Room area exceeds setback limits"}

    monkeypatch.setattr(serializer, "compile_blueprint", _mock_infeasible)

    plan, prob = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)

    assert res.status == RealizationStatus.SPATIALLY_INFEASIBLE
    assert len(res.infeasible_constraints) == 1


def test_17_failure_result_never_contains_realized_geometry():
    """Point 17: Assert realized_geometry is None on failure results."""
    plan, prob = _make_sample_plan()
    plan.plot_width = -10.0

    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)
    assert res.success is False
    assert res.realized_geometry is None


def test_18_successful_result_still_contains_realized_geometry():
    """Point 18: Assert successful realization contains non-null realized geometry."""
    plan, prob = _make_sample_plan()
    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)

    assert res.success is True
    assert res.realized_geometry is not None


def test_19_legacy_compiler_intent_path_remains_functional():
    """Point 19: Verify legacy CompilerIntent -> compile_blueprint path works completely unchanged."""
    from app.services.compiler.serializer import compile_blueprint

    payload = {
        "plot": {"width": 40.0, "depth": 40.0},
        "setbacks": {"left": 3.0, "right": 3.0, "bottom": 5.0, "top": 3.0},
        "stair_core": {"width": 10.0, "height": 10.0, "edge": "bottom-left"},
        "floors": 1,
        "rooms": [
            {
                "name": "Entrance Lobby",
                "type": "Entrance",
                "min_area": 9.0,
                "min_width": 3.0,
                "min_height": 3.0,
                "floor_assignment": 1,
                "requires_ventilation": False,
                "adjacent_to_road": True,
            },
        ],
        "adjacencies": [],
        "road_edge": "bottom",
        "grid_snap": 0.5,
        "time_limit_sec": 5,
    }

    res = compile_blueprint(payload)
    assert res["success"] is True


def test_20_existing_compiler_is_still_reused(monkeypatch):
    """Point 20: Verify existing compile_blueprint in serializer module is called."""
    called = False
    orig_compile = serializer.compile_blueprint

    def _spy_compile(*args, **kwargs):
        nonlocal called
        called = True
        return orig_compile(*args, **kwargs)

    monkeypatch.setattr(serializer, "compile_blueprint", _spy_compile)

    plan, prob = _make_sample_plan()
    SpatialCompilerBridge.realize_layout(plan, problem=prob)

    assert called is True


def test_21_existing_solver_is_still_reused(monkeypatch):
    """Point 21: Verify existing solve_layout in solver module is called via compile_blueprint."""
    called = False
    orig_solve = serializer.solve_layout

    def _spy_solve(*args, **kwargs):
        nonlocal called
        called = True
        return orig_solve(*args, **kwargs)

    monkeypatch.setattr(serializer, "solve_layout", _spy_solve)

    plan, prob = _make_sample_plan()
    SpatialCompilerBridge.realize_layout(plan, problem=prob)

    assert called is True


def test_22_no_second_solver_implementation_exists():
    """Point 22: Assert no second solver implementation was introduced in compiler bridge."""
    source = inspect.getsource(compiler_bridge)
    for kw in ["pulp", "LpProblem", "LpVariable", "lpSum", "solver.solve"]:
        assert kw not in source


def test_23_no_new_geometry_engine_exists():
    """Point 23: Assert spatial_adapter and compiler_bridge contain no geometry algorithms."""
    for mod in [spatial_adapter, compiler_bridge]:
        source = inspect.getsource(mod)
        for kw in ["shapely.geometry", "Polygon", "MultiPolygon", "Point"]:
            assert kw not in source


def test_24_candidate_organizer_remains_unchanged():
    """Point 24: Assert CandidateOrganizer behavior is unchanged."""
    prob, cand = get_golden_single_family_fixture()
    assert cand.floor_organization is not None


def test_25_candidate_to_layout_adapter_remains_unchanged():
    """Point 25: Assert CandidateToLayoutAdapter behavior is unchanged."""
    prob, cand = get_golden_single_family_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert plan.plot_width == 30.0


def test_26_strategy_generator_remains_unchanged():
    """Point 26: Assert StrategyGenerator behavior is unchanged."""
    from app.schemas.architectural_analysis import ArchitecturalAnalysis
    from app.services.analysis.strategy_generator import generate_strategies

    analysis = ArchitecturalAnalysis(
        id="analysis-test",
        problem_id="prob-1",
        problem_version=1,
        summary="Test summary",
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


def test_27_no_domain_specific_failure_branches_exist():
    """Point 27: AST check verifying zero domain string branches in failure classifier."""
    import textwrap
    source = textwrap.dedent(inspect.getsource(SpatialCompilerBridge.classify_failure))
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            if isinstance(node.test, ast.Compare):
                left = getattr(node.test.left, "id", "") or getattr(node.test.left, "attr", "")
                assert left not in ["dimension", "vertical_circulation", "unit_organization"]


def test_28_custom_dimensions_fail_or_succeed_generically():
    """Point 28: Verify custom dimensions succeed or fail generically without hardcoded branches."""
    prob, cand = get_golden_custom_dimensions_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)

    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)
    assert res.success is True
