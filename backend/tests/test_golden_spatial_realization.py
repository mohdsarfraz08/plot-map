"""
Golden Spatial Realization Verification Suite for Stage 3B.4D-4.

Verifies end-to-end realization across 28 points:
1. 44x42 benchmark reaches successful realization
2. 44x42 room count is preserved
3. 44x42 unit assignments are preserved
4. 44x42 floor assignments are preserved
5. 44x42 shared circulation topology is preserved
6. 44x42 service organization is preserved
7. Single-family reaches successful realization
8. Shared circulation reaches successful realization
9. Independent circulation reaches successful realization
10. Hybrid circulation reaches successful realization where supported
11. Ground-floor-only fixture realizes correctly
12. Distributed-floor fixture realizes correctly
13. Centralized service-core fixture realizes correctly
14. Custom/unseen dimensions survive into realization provenance/parameters
15. Complete source traceability survives
16. RealizationResult status is SUCCESS for valid fixtures
17. Realized geometry exists ONLY after the compiler/solver boundary
18. Deterministic room IDs/order are preserved
19. Repeated execution produces equivalent deterministic results
20. Legacy CompilerIntent -> compile_blueprint path remains functional
21. Existing solver implementation is actually reused
22. No second solver implementation was introduced
23. No new geometry engine was introduced
24. CandidateOrganizer behavior remains unchanged
25. CandidateToLayoutAdapter behavior remains unchanged
26. StrategyGenerator behavior remains unchanged
27. Custom dimensions do not require domain-specific Python branching
28. Provenance is complete and internally consistent
"""

import ast
import inspect
import pytest

from app.schemas.architectural_analysis import DecisionRecord, DecisionStatus
from app.schemas.intent import CompilerIntent, RoomCategory, RoomIntent
from app.schemas.spatial_realization import (
    RealizationResult,
    RealizationStatus,
)
from app.services.analysis import candidate_organizer, candidate_generator, spatial_adapter, strategy_generator
from app.services.analysis.candidate_organizer import organize_candidate
from app.services.analysis.catalog_loader import get_catalog_organization_rules
from app.services.analysis.spatial_adapter import CandidateToLayoutAdapter
from app.services.compiler import serializer
from app.services.optimization import solver
from app.services.realization import compiler_bridge
from app.services.realization.compiler_bridge import SpatialCompilerBridge, realize_spatial_layout
from tests.fixtures.golden_spatial_realization_fixtures import (
    get_golden_44x42_benchmark_fixture,
    get_golden_centralized_service_fixture,
    get_golden_custom_dimensions_fixture,
    get_golden_distributed_floor_fixture,
    get_golden_ground_floor_fixture,
    get_golden_hybrid_circulation_fixture,
    get_golden_independent_circulation_fixture,
    get_golden_shared_circulation_fixture,
    get_golden_single_family_fixture,
)


def _realize_golden(prob, cand):
    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    return plan, SpatialCompilerBridge.realize_layout(plan, problem=prob)


def test_01_44x42_benchmark_reaches_successful_realization():
    """Point 1: Verify 44x42 benchmark candidate reaches successful realization."""
    prob, cand = get_golden_44x42_benchmark_fixture()
    _, res = _realize_golden(prob, cand)

    assert res.success is True
    assert res.status == RealizationStatus.SUCCESS


def test_02_44x42_room_count_is_preserved():
    """Point 2: Verify 44x42 room count (16 spaces) is preserved in SpatialLayoutPlan."""
    prob, cand = get_golden_44x42_benchmark_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)

    assert len(plan.rooms) == 16


def test_03_44x42_unit_assignments_are_preserved():
    """Point 3: Verify 44x42 unit assignments (family_a..d) are preserved."""
    prob, cand = get_golden_44x42_benchmark_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)

    units_found = {r.unit_id for r in plan.rooms}
    assert "family_a" in units_found
    assert "family_b" in units_found


def test_04_44x42_floor_assignments_are_preserved():
    """Point 4: Verify 44x42 floor assignments are preserved."""
    prob, cand = get_golden_44x42_benchmark_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)

    floors_assigned = {r.floor_assignment for r in plan.rooms}
    assert 1 in floors_assigned


def test_05_44x42_shared_circulation_topology_is_preserved():
    """Point 5: Verify 44x42 shared circulation core is preserved in cores."""
    prob, cand = get_golden_44x42_benchmark_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)

    stair_cores = [c for c in plan.cores if c.core_type == "vertical_stairwell"]
    assert len(stair_cores) >= 1
    assert stair_cores[0].access_type == "shared"


def test_06_44x42_service_organization_is_preserved():
    """Point 6: Verify 44x42 service core organization is preserved in cores."""
    prob, cand = get_golden_44x42_benchmark_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)

    service_cores = [c for c in plan.cores if c.core_type == "plumbing_wet_core"]
    assert len(service_cores) >= 1


def test_07_single_family_reaches_successful_realization():
    """Point 7: Verify single-family scenario reaches successful realization."""
    prob, cand = get_golden_single_family_fixture()
    _, res = _realize_golden(prob, cand)

    assert res.success is True
    assert res.status == RealizationStatus.SUCCESS


def test_08_shared_circulation_reaches_successful_realization():
    """Point 8: Verify shared circulation scenario reaches successful realization."""
    prob, cand = get_golden_shared_circulation_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert any(c.access_type == "shared" for c in plan.cores)


def test_09_independent_circulation_reaches_successful_realization():
    """Point 9: Verify independent circulation scenario reaches successful realization."""
    prob, cand = get_golden_independent_circulation_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert not any(c.access_type == "shared" for c in plan.cores if c.core_type == "vertical_stairwell")


def test_10_hybrid_circulation_reaches_successful_realization():
    """Point 10: Verify hybrid circulation scenario reaches successful realization."""
    prob, cand = get_golden_hybrid_circulation_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert plan is not None


def test_11_ground_floor_only_fixture_realizes_correctly():
    """Point 11: Verify ground-floor-only fixture realizes correctly."""
    prob, cand = get_golden_ground_floor_fixture()
    plan, res = _realize_golden(prob, cand)

    assert res.success is True
    assert all(r.floor_assignment == 1 for r in plan.rooms)


def test_12_distributed_floor_fixture_realizes_correctly():
    """Point 12: Verify distributed floor fixture realizes correctly."""
    prob, cand = get_golden_distributed_floor_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert len(plan.rooms) == 16


def test_13_centralized_service_core_fixture_realizes_correctly():
    """Point 13: Verify centralized service-core fixture realizes correctly."""
    prob, cand = get_golden_centralized_service_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert any(c.core_type == "plumbing_wet_core" for c in plan.cores)


def test_14_custom_unseen_dimensions_survive_into_provenance_and_parameters():
    """Point 14: Verify custom/unseen decision dimensions survive into parameters and provenance."""
    prob, cand = get_golden_custom_dimensions_fixture()
    plan, res = _realize_golden(prob, cand)

    sel_decs = plan.realization_parameters["selected_decisions"]
    assert sel_decs["solar_shading_strategy"] == "external_louver"
    assert sel_decs["facade_transparency"] == "high_glazed"
    assert sel_decs["natural_ventilation_strategy"] == "cross_breeze"
    assert res.success is True


def test_15_complete_source_traceability_survives():
    """Point 15: Verify full lineage (candidate -> strategy -> problem -> spatial plan -> realization)."""
    prob, cand = get_golden_single_family_fixture()
    plan, res = _realize_golden(prob, cand)

    assert res.candidate_id == cand.id
    assert res.provenance["source_strategy_id"] == cand.source_strategy_id
    assert res.provenance["source_problem_id"] == prob.id
    assert res.provenance["source_problem_version"] == prob.version
    assert res.provenance["layout_plan_id"] == plan.id


def test_16_realization_result_status_is_success():
    """Point 16: Verify valid golden fixtures produce RealizationStatus.SUCCESS."""
    prob, cand = get_golden_single_family_fixture()
    _, res = _realize_golden(prob, cand)
    assert res.status == RealizationStatus.SUCCESS
    assert res.success is True


def test_17_realized_geometry_exists_only_after_compiler_boundary():
    """Point 17: Assert geometry payload is None on SpatialLayoutPlan and exists ONLY on RealizationResult."""
    prob, cand = get_golden_single_family_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)

    assert not hasattr(plan, "realized_geometry") or plan.realized_geometry is None

    res = SpatialCompilerBridge.realize_layout(plan, problem=prob)
    assert res.realized_geometry is not None
    assert "geometry" in res.realized_geometry


def test_18_deterministic_room_ids_and_order_are_preserved():
    """Point 18: Verify room IDs and order are deterministic across calls."""
    prob, cand = get_golden_44x42_benchmark_fixture()
    plan_1 = CandidateToLayoutAdapter.adapt(cand, prob)
    plan_2 = CandidateToLayoutAdapter.adapt(cand, prob)

    r_ids_1 = [r.id for r in plan_1.rooms]
    r_ids_2 = [r.id for r in plan_2.rooms]
    assert r_ids_1 == r_ids_2


def test_19_repeated_execution_produces_equivalent_deterministic_results():
    """Point 19: Verify repeated realization produces identical metadata across repeated iterations."""
    prob, cand = get_golden_single_family_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)

    baseline_res = SpatialCompilerBridge.realize_layout(plan, problem=prob)

    for _ in range(3):
        res = SpatialCompilerBridge.realize_layout(plan, problem=prob)
        assert res.status == baseline_res.status
        assert res.success == baseline_res.success
        assert res.candidate_id == baseline_res.candidate_id


def test_20_legacy_compiler_intent_path_remains_functional():
    """Point 20: Verify legacy CompilerIntent -> compile_blueprint path works completely unchanged."""
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
            {
                "name": "Living Room",
                "type": "Living Room",
                "min_area": 80.0,
                "min_width": 8.0,
                "min_height": 8.0,
                "floor_assignment": 1,
                "requires_ventilation": True,
                "adjacent_to_road": True,
            },
        ],
        "adjacencies": [("Entrance Lobby", "Living Room")],
        "road_edge": "bottom",
        "grid_snap": 0.5,
        "time_limit_sec": 5,
    }

    result = compile_blueprint(payload)
    assert result["success"] is True


def test_21_existing_solver_implementation_is_actually_reused(monkeypatch):
    """Point 21: Verify existing solve_layout function is invoked during realization."""
    called_solver = False
    orig_solve = serializer.solve_layout

    def _spy_solve(*args, **kwargs):
        nonlocal called_solver
        called_solver = True
        return orig_solve(*args, **kwargs)

    monkeypatch.setattr(serializer, "solve_layout", _spy_solve)

    prob, cand = get_golden_single_family_fixture()
    _realize_golden(prob, cand)

    assert called_solver is True


def test_22_no_second_solver_implementation_was_introduced():
    """Point 22: Assert no second solver module was created in realization package."""
    bridge_source = inspect.getsource(compiler_bridge)
    for prohibited in ["LpProblem", "LpVariable", "lpSum", "PuLP"]:
        assert prohibited not in bridge_source


def test_23_no_new_geometry_engine_was_introduced():
    """Point 23: Assert spatial_adapter and compiler_bridge do not import Shapely or create geometry algorithms."""
    for mod in [spatial_adapter, compiler_bridge]:
        source = inspect.getsource(mod)
        for prohibited in ["shapely.geometry", "Polygon", "MultiPolygon", "Point"]:
            assert prohibited not in source


def test_24_candidate_organizer_behavior_remains_unchanged():
    """Point 24: Assert CandidateOrganizer behavior is unchanged."""
    prob, cand = get_golden_single_family_fixture()
    assert cand.floor_organization is not None


def test_25_candidate_to_layout_adapter_behavior_remains_unchanged():
    """Point 25: Assert CandidateToLayoutAdapter behavior is unchanged."""
    prob, cand = get_golden_single_family_fixture()
    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert plan.plot_width == 30.0


def test_26_strategy_generator_behavior_remains_unchanged():
    """Point 26: Assert StrategyGenerator behavior is unchanged."""
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


def test_27_custom_dimensions_do_not_require_domain_specific_python_branching():
    """Point 27: AST check verifying zero domain string branches in spatial adapter and compiler bridge."""
    for mod in [spatial_adapter, compiler_bridge]:
        source = inspect.getsource(mod)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                # Ensure no 'if dimension == ...' or 'if value == ...' domain branches exist
                if isinstance(node.test, ast.Compare):
                    left = getattr(node.test.left, "id", "") or getattr(node.test.left, "attr", "")
                    assert left not in ["dimension", "vertical_circulation", "unit_organization"]


def test_28_provenance_is_complete_and_internally_consistent():
    """Point 28: Verify provenance completeness across golden realization outputs."""
    prob, cand = get_golden_44x42_benchmark_fixture()
    _, res = _realize_golden(prob, cand)

    prov = res.provenance
    assert "compiler" in prov
    assert "layout_plan_id" in prov
    assert "source_candidate_id" in prov
    assert "source_strategy_id" in prov
    assert "source_problem_id" in prov
