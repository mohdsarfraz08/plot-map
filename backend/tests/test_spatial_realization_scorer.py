"""
Unit, Contract, AST, and Monkeypatch Test Suite for Stage 3B.5-4: Phase 2 Spatial Realization Scorer.

Validates post-realization scoring, RealizationStatus handling, non-geometric boundary,
monkeypatch solver/compiler isolation, candidate/realization immutability, and Phase 1+2 combination helper.
"""

import ast
import json
from pathlib import Path
import pytest

from app.schemas.architectural_analysis import AnalysisSeverity, DecisionRecord, DecisionStatus
from app.schemas.design_candidate import (
    AbstractCirculationNode,
    AbstractServiceStack,
    DesignCandidate,
)
from app.schemas.design_problem import (
    DesignProblem,
    Objective,
    Preference,
    Requirement,
    RequirementKind,
    SiteDefinition,
    SpaceRequirement,
)
from app.schemas.design_strategy import FeasibilityExpectation
from app.schemas.intent import RoomCategory, RoomIntent
from app.schemas.spatial_realization import (
    RealizationResult,
    RealizationStatus,
    SpatialCoreSpec,
    SpatialLayoutPlan,
    SpatialRoomSpec,
)
from app.schemas.strategy_preference import PreferenceCatalog
from app.schemas.strategy_ranking import (
    RankedCandidate,
    ScoreBreakdown,
    SelectionStatus,
)
from app.services.analysis.catalog_loader import load_preference_catalog
from app.services.ranking.abstract_strategic_scorer import AbstractStrategicScorer
from app.services.ranking.spatial_realization_scorer import SpatialRealizationScorer


def _make_problem() -> DesignProblem:
    return DesignProblem(
        id="problem-1",
        version=1,
        site=SiteDefinition(plot_width=44.0, plot_depth=42.0, floors=2),
        spaces=[
            SpaceRequirement(id="space-1", room=RoomIntent(room_type=RoomCategory.LIVING)),
            SpaceRequirement(id="space-2", room=RoomIntent(room_type=RoomCategory.BEDROOM)),
            SpaceRequirement(id="space-3", room=RoomIntent(room_type=RoomCategory.BATHROOM)),
        ],
        requirements=[
            Requirement(
                id="req-privacy-1",
                kind=RequirementKind.PRIVACY,
                subject="space-2",
                value="high_privacy",
            )
        ],
        objectives=[
            Objective(id="obj-1", metric="area_efficiency", direction="maximize", priority=80)
        ],
        preferences=[
            Preference(id="pref-1", description="Prefer daylighting", target="all_living", priority=70)
        ],
    )


def _make_candidate(candidate_id: str = "cand-1") -> DesignCandidate:
    return DesignCandidate(
        id=candidate_id,
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="problem-1",
        source_problem_version=1,
        candidate_version=1,
        name=f"Test Candidate {candidate_id}",
        selected_decisions=[
            DecisionRecord(
                id="dec-1",
                dimension="circulation_topology",
                subject="circulation",
                value="shared",
                status=DecisionStatus.FIXED,
                rationale="Shared circulation topology",
            )
        ],
        floor_organization={"ground": ["space-1", "space-3"], "first": ["space-2"]},
        unit_organization={"unit-1": ["space-1", "space-2", "space-3"]},
        circulation_intent=[
            AbstractCirculationNode(id="circ-1", type="staircase", connected_space_ids=["space-1", "space-2"])
        ],
        service_organization=[
            AbstractServiceStack(id="serv-1", service_type="plumbing", assigned_space_ids=["space-3"])
        ],
        unresolved_decisions=[],
        assumptions=["Standard ceiling height"],
        risks=[],
        feasibility_expectation=FeasibilityExpectation.EXPECTED_FEASIBLE,
        confidence=0.95,
        provenance={"generator": "test_suite"},
    )


def _make_layout_plan(candidate_id: str = "cand-1") -> SpatialLayoutPlan:
    return SpatialLayoutPlan(
        id=f"plan-{candidate_id}",
        source_candidate_id=candidate_id,
        source_strategy_id="strat-1",
        source_problem_id="problem-1",
        source_problem_version=1,
        plot_width=44.0,
        plot_depth=42.0,
        floors=2,
        rooms=[
            SpatialRoomSpec(id="space-1", name="Living Room", room_type="living", target_area=150.0, floor_assignment=1),
            SpatialRoomSpec(id="space-2", name="Bedroom 1", room_type="bedroom", target_area=100.0, floor_assignment=2),
            SpatialRoomSpec(id="space-3", name="Bathroom 1", room_type="bathroom", target_area=40.0, floor_assignment=1),
        ],
        cores=[
            SpatialCoreSpec(id="core-stair", core_type="vertical_stairwell", floors=[1, 2], connected_space_ids=["space-1", "space-2"]),
            SpatialCoreSpec(id="core-wet", core_type="plumbing_wet_core", floors=[1], connected_space_ids=["space-3"]),
        ],
        provenance={"generator": "spatial_adapter"},
    )


def _make_realization(candidate_id: str = "cand-1", success: bool = True, status: RealizationStatus = RealizationStatus.SUCCESS) -> RealizationResult:
    plan = _make_layout_plan(candidate_id) if success else None
    return RealizationResult(
        status=status,
        success=success,
        candidate_id=candidate_id,
        layout_plan=plan,
        realized_geometry={"layout_area": 290.0, "solved": success} if success else None,
        error_message=None if success else f"Realization failed with status {status.value}",
        infeasible_constraints=[] if success else ["c-1"],
        provenance={"solver": "test_solver"},
    )


def test_01_minimal_successful_realization_scoring():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    assert isinstance(breakdown, ScoreBreakdown)
    assert 0.0 <= breakdown.total_score <= 1.0
    assert breakdown.scoring_version == "3B.5-2.v1"


def test_02_score_breakdown_construction():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    assert len(breakdown.criteria) == 6
    for c in breakdown.criteria:
        assert c.criterion_id
        assert 0.0 <= c.score <= 1.0
        assert c.weight >= 0.0
        assert c.explanation


def test_03_preference_catalog_criteria_loading():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    expected_ids = {
        "program_usability",
        "privacy_compliance",
        "circulation_efficiency",
        "service_core_stacking",
        "realization_feasibility",
        "objective_alignment",
    }
    actual_ids = {c.criterion_id for c in breakdown.criteria}
    assert actual_ids == expected_ids


def test_04_catalog_weight_preservation():
    catalog = load_preference_catalog()
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization, catalog)
    catalog_weights = {c.id: c.weight for c in catalog.criteria}
    scored_weights = {c.criterion_id: c.weight for c in breakdown.criteria}
    assert scored_weights == catalog_weights


def test_05_successful_realization_feasibility_score():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization(success=True, status=RealizationStatus.SUCCESS)

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    feas_crit = next(c for c in breakdown.criteria if c.criterion_id == "realization_feasibility")
    assert feas_crit.score == 1.0


def test_06_invalid_candidate_realization():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization(success=False, status=RealizationStatus.INVALID_CANDIDATE)

    ranked_list = SpatialRealizationScorer.score_realizations([cand], [realization], problem)
    assert len(ranked_list) == 1
    assert ranked_list[0].selection_status == SelectionStatus.REJECTED
    assert "invalid_candidate" in ranked_list[0].rejection_reasons[0]


def test_07_unsupported_specification_realization():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization(success=False, status=RealizationStatus.UNSUPPORTED_SPEC)

    ranked_list = SpatialRealizationScorer.score_realizations([cand], [realization], problem)
    assert len(ranked_list) == 1
    assert ranked_list[0].selection_status == SelectionStatus.REJECTED


def test_08_spatially_infeasible_realization():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization(success=False, status=RealizationStatus.SPATIALLY_INFEASIBLE)

    ranked_list = SpatialRealizationScorer.score_realizations([cand], [realization], problem)
    assert len(ranked_list) == 1
    assert ranked_list[0].selection_status == SelectionStatus.REJECTED


def test_09_solver_timeout_realization():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization(success=False, status=RealizationStatus.SOLVER_TIMEOUT)

    ranked_list = SpatialRealizationScorer.score_realizations([cand], [realization], problem)
    assert len(ranked_list) == 1
    assert ranked_list[0].selection_status == SelectionStatus.REJECTED


def test_10_solver_error_realization():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization(success=False, status=RealizationStatus.SOLVER_ERROR)

    ranked_list = SpatialRealizationScorer.score_realizations([cand], [realization], problem)
    assert len(ranked_list) == 1
    assert ranked_list[0].selection_status == SelectionStatus.REJECTED


def test_11_program_usability_from_realized_room_evidence():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    prog_crit = next(c for c in breakdown.criteria if c.criterion_id == "program_usability")
    assert prog_crit.score > 0.0
    assert len(prog_crit.source_ids) == 3


def test_12_room_count_preservation():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    prog_crit = next(c for c in breakdown.criteria if c.criterion_id == "program_usability")
    assert "3 realized rooms" in prog_crit.explanation


def test_13_missing_room_detection():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()
    # Remove space-3 from plan
    realization.layout_plan.rooms = [r for r in realization.layout_plan.rooms if r.id != "space-3"]

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    prog_crit = next(c for c in breakdown.criteria if c.criterion_id == "program_usability")
    assert "2 realized rooms" in prog_crit.explanation


def test_14_floor_assignment_consistency():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    prog_crit = next(c for c in breakdown.criteria if c.criterion_id == "program_usability")
    assert "floor-consistent" in prog_crit.explanation


def test_15_service_core_realization_scoring():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    serv_crit = next(c for c in breakdown.criteria if c.criterion_id == "service_core_stacking")
    assert serv_crit.score > 0.0
    assert "core-wet" in serv_crit.source_ids


def test_16_circulation_evidence_handling():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    circ_crit = next(c for c in breakdown.criteria if c.criterion_id == "circulation_efficiency")
    assert circ_crit.score > 0.0
    assert "core-stair" in circ_crit.source_ids


def test_17_missing_circulation_metric_handling():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()
    realization.layout_plan.cores = []

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    circ_crit = next(c for c in breakdown.criteria if c.criterion_id == "circulation_efficiency")
    assert circ_crit.score == 0.5
    assert "neutral baseline applied" in circ_crit.explanation


def test_18_objective_alignment_handling():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    obj_crit = next(c for c in breakdown.criteria if c.criterion_id == "objective_alignment")
    assert obj_crit.score > 0.0
    assert "obj-1" in obj_crit.source_ids


def test_19_unresolved_decision_preservation():
    problem = _make_problem()
    cand = _make_candidate()
    cand.unresolved_decisions = [
        DecisionRecord(id="unres-1", dimension="dim-1", subject="sub-1", value="val-1", status=DecisionStatus.UNRESOLVED, rationale="test")
    ]
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    assert breakdown.total_score > 0.0


def test_20_phase_2_provenance():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    ranked_list = SpatialRealizationScorer.score_realizations([cand], [realization], problem)
    prov = ranked_list[0].provenance

    assert prov["scoring_phase"] == "phase_2_spatial_realization"
    assert prov["layout_plan_id"] == realization.layout_plan.id
    assert prov["realization_status"] == "success"


def test_21_source_id_preservation():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    for c in breakdown.criteria:
        assert isinstance(c.source_ids, list)


def test_22_layout_plan_lineage_preservation():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    ranked_list = SpatialRealizationScorer.score_realizations([cand], [realization], problem)
    assert ranked_list[0].provenance["layout_plan_id"] == "plan-cand-1"


def test_23_custom_unseen_decision_dimensions():
    custom_catalog_dict = {
        "version": "custom-v1",
        "provenance": {"author": "test"},
        "deterministic_precision": 6,
        "selection_thresholds": {
            "selected_min_score": 0.8,
            "viable_min_score": 0.6,
            "marginal_min_score": 0.4,
            "rejected_max_score": 0.4,
        },
        "tie_break": {
            "priority_criteria": [
                "solar_shading_strategy",
                "facade_transparency",
                "energy_resilience_strategy",
                "future_custom_dimension",
            ],
            "fallback_strategy": "candidate_id",
        },
        "criteria": [
            {"id": "solar_shading_strategy", "description": "Custom shading", "weight": 0.25},
            {"id": "facade_transparency", "description": "Custom facade", "weight": 0.25},
            {"id": "energy_resilience_strategy", "description": "Custom energy", "weight": 0.25},
            {"id": "future_custom_dimension", "description": "Custom metric", "weight": 0.25},
        ],
    }
    catalog = PreferenceCatalog.model_validate(custom_catalog_dict)
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization, catalog)
    assert breakdown.scoring_version == "custom-v1"
    assert len(breakdown.criteria) == 4


def test_24_deterministic_repeated_execution():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    sb1 = SpatialRealizationScorer.score_realization(cand, problem, realization)
    sb2 = SpatialRealizationScorer.score_realization(cand, problem, realization)
    sb3 = SpatialRealizationScorer.score_realization(cand, problem, realization)

    assert sb1.model_dump_json() == sb2.model_dump_json() == sb3.model_dump_json()


def test_25_deterministic_criterion_ordering():
    catalog = load_preference_catalog()
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    sb = SpatialRealizationScorer.score_realization(cand, problem, realization, catalog)
    catalog_order = [c.id for c in catalog.criteria]
    scored_order = [c.criterion_id for c in sb.criteria]
    assert scored_order == catalog_order


def test_26_json_round_trip_determinism():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    ranked_list = SpatialRealizationScorer.score_realizations([cand], [realization], problem)
    json_str = ranked_list[0].model_dump_json()
    reconstructed = RankedCandidate.model_validate_json(json_str)
    assert reconstructed == ranked_list[0]


def test_27_no_solver_invocation(monkeypatch):
    # Monkeypatch solve_layout to raise error if called
    def _forbidden_solver(*args, **kwargs):
        raise RuntimeError("Solver must not be invoked during Phase 2 scoring")

    monkeypatch.setattr("app.services.realization.compiler_bridge.SpatialCompilerBridge.realize_layout", _forbidden_solver, raising=False)

    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    assert breakdown.total_score > 0.0


def test_28_no_compiler_invocation(monkeypatch):
    def _forbidden_compiler(*args, **kwargs):
        raise RuntimeError("Compiler must not be invoked during Phase 2 scoring")

    monkeypatch.setattr("app.services.realization.compiler_bridge.SpatialCompilerBridge.compile_candidate", _forbidden_compiler, raising=False)

    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    breakdown = SpatialRealizationScorer.score_realization(cand, problem, realization)
    assert breakdown.total_score > 0.0


def test_29_no_geometry_creation_or_mutation():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()
    orig_geom = json.dumps(realization.realized_geometry)

    SpatialRealizationScorer.score_realization(cand, problem, realization)
    new_geom = json.dumps(realization.realized_geometry)
    assert orig_geom == new_geom


def test_30_non_geometric_ast_boundary():
    scorer_file = Path(__file__).parent.parent / "app" / "services" / "ranking" / "spatial_realization_scorer.py"
    content = scorer_file.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(scorer_file))

    prohibited = {"shapely", "pulp", "cbc", "solver", "compiler"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0].lower() not in prohibited
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert node.module.split(".")[0].lower() not in prohibited

        if isinstance(node, ast.Compare):
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    assert comparator.value not in {"program_usability", "privacy_compliance", "circulation_efficiency"}


def test_31_multiple_realization_scoring():
    problem = _make_problem()
    c1 = _make_candidate("cand-1")
    c2 = _make_candidate("cand-2")
    r1 = _make_realization("cand-1", success=True)
    r2 = _make_realization("cand-2", success=False, status=RealizationStatus.SPATIALLY_INFEASIBLE)

    ranked_list = SpatialRealizationScorer.score_realizations([c1, c2], [r1, r2], problem)
    assert len(ranked_list) == 2
    assert ranked_list[0].candidate_id == "cand-1"
    assert ranked_list[0].selection_status in {SelectionStatus.SELECTED, SelectionStatus.VIABLE}
    assert ranked_list[1].candidate_id == "cand-2"
    assert ranked_list[1].selection_status == SelectionStatus.REJECTED


def test_32_empty_input_handling():
    problem = _make_problem()
    ranked = SpatialRealizationScorer.score_realizations([], [], problem)
    assert ranked == []


def test_33_failed_realization_never_receives_success_score():
    problem = _make_problem()
    cand = _make_candidate("cand-failed")
    realization = _make_realization("cand-failed", success=False, status=RealizationStatus.SOLVER_ERROR)

    ranked_list = SpatialRealizationScorer.score_realizations([cand], [realization], problem)
    assert len(ranked_list) == 1
    assert ranked_list[0].selection_status == SelectionStatus.REJECTED
    assert len(ranked_list[0].rejection_reasons) > 0


def test_34_no_mutation_of_candidate():
    problem = _make_problem()
    cand = _make_candidate("c-immut")
    cand_dump = cand.model_dump_json()
    realization = _make_realization("c-immut")

    SpatialRealizationScorer.score_realization(cand, problem, realization)
    assert cand.model_dump_json() == cand_dump


def test_35_no_mutation_of_realization():
    problem = _make_problem()
    cand = _make_candidate("r-immut")
    realization = _make_realization("r-immut")
    real_dump = realization.model_dump_json()

    SpatialRealizationScorer.score_realization(cand, problem, realization)
    assert realization.model_dump_json() == real_dump


def test_36_catalog_version_preservation():
    catalog = load_preference_catalog()
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    sb = SpatialRealizationScorer.score_realization(cand, problem, realization, catalog)
    assert sb.scoring_version == catalog.version


def test_37_combine_phase1_and_phase2_score_breakdowns_helper():
    problem = _make_problem()
    cand = _make_candidate()
    realization = _make_realization()

    sb1 = AbstractStrategicScorer.score_candidate(cand, problem)
    sb2 = SpatialRealizationScorer.score_realization(cand, problem, realization)

    combined = SpatialRealizationScorer.combine_score_breakdowns(sb1, sb2, weight_phase1=0.4, weight_phase2=0.6)
    assert isinstance(combined, ScoreBreakdown)
    assert 0.0 <= combined.total_score <= 1.0
    assert "+combined" in combined.scoring_version
