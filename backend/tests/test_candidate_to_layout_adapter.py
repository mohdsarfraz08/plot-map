"""
Test suite for CandidateToLayoutAdapter (Stage 3B.4D-2).

Verifies 28 points:
1. Minimal candidate -> SpatialLayoutPlan
2. Source traceability
3. Problem/version traceability
4. Room requirements -> SpatialRoomSpec
5. Floor organization translation
6. Unit organization translation
7. Explicit circulation intent translation
8. Explicit service organization translation
9. Selected decision preservation
10. Unresolved decision preservation
11. Assumption preservation
12. Risk preservation
13. Confidence preservation
14. Provenance preservation
15. Unknown/custom dimension pass-through
16. Deterministic repeated execution
17. Stable deterministic IDs
18. Empty optional collections
19. Invalid input handling
20. Non-geometric AST/boundary verification
21. Solver non-invocation verification
22. Compiler non-invocation verification
23. 44x42 benchmark fixture translation
24. Single-family fixture translation
25. Multiple-floor abstract candidate translation
26. Explicit circulation + service topology translation
27. No invented geometry verification
28. Idempotent translation
"""

import ast
import json
import inspect
import pytest
from pydantic import ValidationError

from app.schemas.architectural_analysis import DecisionRecord
from app.schemas.design_candidate import (
    AbstractCirculationNode,
    AbstractServiceStack,
    DesignCandidate,
)
from app.schemas.design_problem import (
    DesignProblem,
    RequirementRelation,
    RoomIntent,
    SpaceRequirement,
)
from app.schemas.design_strategy import FeasibilityExpectation, StrategyRisk
from app.schemas.spatial_realization import SpatialLayoutPlan
from app.services.analysis import spatial_adapter
from app.services.analysis.spatial_adapter import (
    CandidateToLayoutAdapter,
    adapt_candidate_to_spatial_layout_plan,
)
from tests.fixtures.golden_organization_fixtures import (
    get_benchmark_44x42_candidate,
    get_benchmark_44x42_problem,
    get_single_family_candidate,
    get_single_family_problem,
)


def _make_minimal_problem() -> DesignProblem:
    return DesignProblem(
        id="prob-1",
        version=1,
        name="Test Problem",
        site={"plot_width": 40.0, "plot_depth": 40.0, "floors": 2, "setbacks": {"left": 2.0, "right": 2.0}},
        spaces=[
            SpaceRequirement(
                id="space_living",
                room=RoomIntent(room_type="living", min_area_sqft=250),
                quantity=1,
            ),
            SpaceRequirement(
                id="space_bed",
                room=RoomIntent(room_type="bedroom", min_area_sqft=150),
                quantity=1,
            ),
        ],
    )


def _make_minimal_candidate(prob: DesignProblem) -> DesignCandidate:
    return DesignCandidate(
        id="cand-1",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id=prob.id,
        source_problem_version=prob.version,
        name="Test Candidate",
        selected_decisions=[
            DecisionRecord(
                id="dec-1",
                dimension="unit_organization",
                subject="building",
                value="grouped",
                status="fixed",
                rationale="Grouping units",
            ),
            DecisionRecord(
                id="dec-2",
                dimension="solar_shading",
                subject="building",
                value="external",
                status="fixed",
                rationale="Custom solar dim",
            ),
        ],
        floor_organization={"floor_1": ["space_living"], "floor_2": ["space_bed"]},
        unit_organization={"unit_family_a": ["space_living", "space_bed"]},
        circulation_intent=[
            AbstractCirculationNode(
                id="circ-core-1",
                type="vertical_stairwell",
                access_type="shared",
                connected_space_ids=["space_living", "space_bed"],
            )
        ],
        service_organization=[
            AbstractServiceStack(
                id="service-core-1",
                service_type="plumbing_wet_core",
                assigned_space_ids=["space_living"],
            )
        ],
        unresolved_decisions=[
            DecisionRecord(
                id="dec-open",
                dimension="facade_material",
                subject="building",
                value="unresolved",
                status="unresolved",
                rationale="Open choice",
            )
        ],
        assumptions=["Standard structural grid"],
        risks=[StrategyRisk(id="risk-1", description="Corridor egress width risk", severity="warning")],
        feasibility_expectation=FeasibilityExpectation.EXPECTED_FEASIBLE,
        confidence=0.85,
        provenance={"generator": "test-suite"},
    )


def test_01_minimal_candidate_to_spatial_layout_plan():
    """Point 1: Verify candidate -> SpatialLayoutPlan basic translation."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert isinstance(plan, SpatialLayoutPlan)
    assert plan.id == "plan-cand-1"
    assert plan.plot_width == 40.0
    assert plan.plot_depth == 40.0
    assert plan.floors == 2
    assert len(plan.rooms) == 2


def test_02_source_traceability():
    """Point 2: Verify candidate and strategy source traceability."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert plan.source_candidate_id == "cand-1"
    assert plan.source_strategy_id == "strat-1"


def test_03_problem_and_version_traceability():
    """Point 3: Verify problem ID and version traceability."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert plan.source_problem_id == prob.id
    assert plan.source_problem_version == prob.version


def test_04_room_requirements_to_spatial_room_spec():
    """Point 4: Verify space requirements convert to SpatialRoomSpecs with correct attributes."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    rooms_by_id = {r.id: r for r in plan.rooms}

    assert "space_living" in rooms_by_id
    assert rooms_by_id["space_living"].target_area == 250.0
    assert rooms_by_id["space_bed"].target_area == 150.0


def test_05_floor_organization_translation():
    """Point 5: Verify floor_organization translates to 1-indexed floor assignments."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    rooms_by_id = {r.id: r for r in plan.rooms}

    assert rooms_by_id["space_living"].floor_assignment == 1
    assert rooms_by_id["space_bed"].floor_assignment == 2


def test_06_unit_organization_translation():
    """Point 6: Verify unit_organization translates to SpatialRoomSpec.unit_id."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    rooms_by_id = {r.id: r for r in plan.rooms}

    assert rooms_by_id["space_living"].unit_id == "unit_family_a"
    assert rooms_by_id["space_bed"].unit_id == "unit_family_a"


def test_07_explicit_circulation_intent_translation():
    """Point 7: Verify circulation_intent translates to SpatialCoreSpec."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    cores_by_id = {c.id: c for c in plan.cores}

    assert "circ-core-1" in cores_by_id
    assert cores_by_id["circ-core-1"].core_type == "vertical_stairwell"
    assert cores_by_id["circ-core-1"].access_type == "shared"


def test_08_explicit_service_organization_translation():
    """Point 8: Verify service_organization translates to SpatialCoreSpec."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    cores_by_id = {c.id: c for c in plan.cores}

    assert "service-core-1" in cores_by_id
    assert cores_by_id["service-core-1"].core_type == "plumbing_wet_core"


def test_09_selected_decision_preservation():
    """Point 9: Verify selected decisions are preserved in realization_parameters."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    sel_decs = plan.realization_parameters["selected_decisions"]

    assert sel_decs["unit_organization"] == "grouped"
    assert sel_decs["solar_shading"] == "external"


def test_10_unresolved_decision_preservation():
    """Point 10: Verify unresolved decisions are preserved in realization_parameters."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    unres_decs = plan.realization_parameters["unresolved_decisions"]

    assert len(unres_decs) == 1
    assert unres_decs[0]["dimension"] == "facade_material"


def test_11_assumption_preservation():
    """Point 11: Verify candidate assumptions are preserved in provenance."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert "Standard structural grid" in plan.provenance["assumptions"]


def test_12_risk_preservation():
    """Point 12: Verify candidate risks are preserved in provenance."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    risks = plan.provenance["risks"]
    assert len(risks) == 1
    assert risks[0]["id"] == "risk-1"


def test_13_confidence_preservation():
    """Point 13: Verify candidate confidence score is preserved in provenance."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert plan.provenance["confidence"] == 0.85


def test_14_provenance_preservation():
    """Point 14: Verify adapter provenance is appended to candidate provenance."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert plan.provenance["generator"] == "test-suite"
    assert plan.provenance["adapter"] == "CandidateToLayoutAdapter"


def test_15_unknown_custom_dimension_pass_through():
    """Point 15: Verify unseen/custom decision dimensions pass through without code changes."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)
    cand.selected_decisions.append(
        DecisionRecord(
            id="dec-custom-unseen",
            dimension="brand_new_custom_dimension",
            subject="building",
            value="custom_value_abc",
            status="fixed",
            rationale="Testing unseen dimension pass through",
        )
    )

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    sel_decs = plan.realization_parameters["selected_decisions"]
    assert sel_decs["brand_new_custom_dimension"] == "custom_value_abc"


def test_16_deterministic_repeated_execution():
    """Point 16: Verify repeated translation of the same candidate produces byte-for-byte identical output."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    json_1 = CandidateToLayoutAdapter.adapt(cand, prob).model_dump_json()
    json_2 = CandidateToLayoutAdapter.adapt(cand, prob).model_dump_json()

    assert json_1 == json_2


def test_17_stable_deterministic_ids():
    """Point 17: Verify plan ID generation is deterministic."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    p1 = CandidateToLayoutAdapter.adapt(cand, prob)
    p2 = CandidateToLayoutAdapter.adapt(cand, prob)
    assert p1.id == p2.id == "plan-cand-1"


def test_18_empty_optional_collections():
    """Point 18: Verify candidate with empty collections adapts successfully."""
    prob = _make_minimal_problem()
    cand = DesignCandidate(
        id="cand-empty",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id=prob.id,
        source_problem_version=prob.version,
        name="Empty Candidate",
    )

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert len(plan.rooms) == 2
    assert len(plan.cores) == 0


def test_19_invalid_input_handling():
    """Point 19: Verify invalid problem or candidate inputs raise explicit exceptions."""
    prob = _make_minimal_problem()

    # Invalid candidate with empty ID
    with pytest.raises(ValidationError):
        DesignCandidate(
            id="",
            source_strategy_id="strat-1",
            source_analysis_id="analysis-1",
            source_problem_id=prob.id,
            source_problem_version=prob.version,
            name="Bad",
        )


def test_20_non_geometric_ast_boundary_verification():
    """Point 20: AST check verifying zero geometric/Shapely/solver imports in spatial_adapter.py."""
    source = inspect.getsource(spatial_adapter)
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", "") or ""
            names = [alias.name for alias in node.names]
            full_imported = mod + " " + " ".join(names)
            for prohibited in ["shapely", "pulp", "cbc", "compiler", "solver", "renderer"]:
                assert prohibited not in full_imported.lower(), f"Prohibited import '{prohibited}' found in adapter AST"


def test_21_solver_non_invocation_verification(monkeypatch):
    """Point 21: Verify solver module function solve_layout is NEVER called during adaptation."""
    from app.services.optimization import solver

    def _fail_solver(*args, **kwargs):
        pytest.fail("solve_layout MUST NOT be called by CandidateToLayoutAdapter")

    monkeypatch.setattr(solver, "solve_layout", _fail_solver)

    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)
    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert plan is not None


def test_22_compiler_non_invocation_verification(monkeypatch):
    """Point 22: Verify compiler module function compile_blueprint is NEVER called during adaptation."""
    from app.services.compiler import serializer

    def _fail_compiler(*args, **kwargs):
        pytest.fail("compile_blueprint MUST NOT be called by CandidateToLayoutAdapter")

    monkeypatch.setattr(serializer, "compile_blueprint", _fail_compiler)

    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)
    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assert plan is not None


def test_23_44x42_benchmark_fixture_translation():
    """Point 23: Verify 44x42 benchmark scenario translates to SpatialLayoutPlan cleanly."""
    from app.services.analysis.candidate_organizer import organize_candidate
    from app.services.analysis.catalog_loader import get_catalog_organization_rules

    prob = get_benchmark_44x42_problem()
    raw_cand = get_benchmark_44x42_candidate(prob)
    rules = get_catalog_organization_rules()
    cand = organize_candidate(raw_cand, rules, problem=prob)

    plan = adapt_candidate_to_spatial_layout_plan(cand, prob)

    assert plan.plot_width == 44.0
    assert plan.plot_depth == 42.0
    assert len(plan.rooms) == 16
    assert len(plan.cores) >= 1


def test_24_single_family_fixture_translation():
    """Point 24: Verify single-family scenario translates to SpatialLayoutPlan cleanly."""
    prob = get_single_family_problem()
    cand = get_single_family_candidate(prob)

    plan = adapt_candidate_to_spatial_layout_plan(cand, prob)

    assert plan.plot_width == 30.0
    assert plan.plot_depth == 40.0
    assert len(plan.rooms) == 5


def test_25_multiple_floor_abstract_candidate_translation():
    """Point 25: Verify multi-floor abstract candidate retains floor assignments."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    assignments = {r.id: r.floor_assignment for r in plan.rooms}

    assert assignments["space_living"] == 1
    assert assignments["space_bed"] == 2


def test_26_explicit_circulation_and_service_topology_translation():
    """Point 26: Verify explicit circulation & service core topology translation."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    core_types = {c.id: c.core_type for c in plan.cores}

    assert core_types["circ-core-1"] == "vertical_stairwell"
    assert core_types["service-core-1"] == "plumbing_wet_core"


def test_27_no_invented_geometry_verification():
    """Point 27: Assert serialized plan output contains zero geometric keywords or coordinates."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan = CandidateToLayoutAdapter.adapt(cand, prob)
    dump_str = json.dumps(plan.model_dump()).lower()

    for geo_kw in ["polygon", "mesh", "coordinate", "cad_layer", "vertex", "bounding_box"]:
        assert geo_kw not in dump_str


def test_28_idempotent_translation():
    """Point 28: Verify idempotent adapter execution (adapt(cand) produces identical plan)."""
    prob = _make_minimal_problem()
    cand = _make_minimal_candidate(prob)

    plan_a = CandidateToLayoutAdapter.adapt(cand, prob)
    plan_b = CandidateToLayoutAdapter.adapt(cand, prob)

    assert plan_a.model_dump() == plan_b.model_dump()
