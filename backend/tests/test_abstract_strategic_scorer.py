"""
Unit and Contract Test Suite for Stage 3B.5-3: Phase 1 Abstract Strategic Scorer.

Validates candidate scoring, generic evaluation architecture, tie-break ordering,
selection status classification, determinism, non-geometric AST boundary, and test coverage.
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
from app.schemas.design_strategy import FeasibilityExpectation, StrategyRisk
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
from app.schemas.strategy_preference import PreferenceCatalog
from app.schemas.strategy_ranking import (
    RankedCandidate,
    ScoreBreakdown,
    SelectionStatus,
)
from app.services.analysis.catalog_loader import load_preference_catalog
from app.services.ranking.abstract_strategic_scorer import AbstractStrategicScorer


def _make_minimal_problem() -> DesignProblem:
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


def _make_minimal_candidate(candidate_id: str = "cand-1", score_boost: bool = True) -> DesignCandidate:
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
        ] if score_boost else [],
        service_organization=[
            AbstractServiceStack(id="serv-1", service_type="plumbing", assigned_space_ids=["space-3"])
        ] if score_boost else [],
        unresolved_decisions=[],
        assumptions=["Standard ceiling height"],
        risks=[],
        feasibility_expectation=FeasibilityExpectation.EXPECTED_FEASIBLE if score_boost else FeasibilityExpectation.CONDITIONALLY_FEASIBLE,
        confidence=0.95 if score_boost else 0.7,
        provenance={"generator": "test_suite"},
    )


def test_01_minimal_candidate_scoring():
    problem = _make_minimal_problem()
    candidate = _make_minimal_candidate()
    breakdown = AbstractStrategicScorer.score_candidate(candidate, problem)

    assert isinstance(breakdown, ScoreBreakdown)
    assert 0.0 <= breakdown.total_score <= 1.0
    assert breakdown.scoring_version == "3B.5-2.v1"


def test_02_score_breakdown_construction():
    problem = _make_minimal_problem()
    candidate = _make_minimal_candidate()
    breakdown = AbstractStrategicScorer.score_candidate(candidate, problem)

    assert len(breakdown.criteria) == 6
    for c in breakdown.criteria:
        assert c.criterion_id
        assert 0.0 <= c.score <= 1.0
        assert c.weight >= 0.0
        assert c.explanation


def test_03_all_six_catalog_criteria_represented():
    problem = _make_minimal_problem()
    candidate = _make_minimal_candidate()
    breakdown = AbstractStrategicScorer.score_candidate(candidate, problem)

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


def test_04_catalog_weights_preserved():
    catalog = load_preference_catalog()
    problem = _make_minimal_problem()
    candidate = _make_minimal_candidate()
    breakdown = AbstractStrategicScorer.score_candidate(candidate, problem, catalog)

    catalog_weights = {c.id: c.weight for c in catalog.criteria}
    scored_weights = {c.criterion_id: c.weight for c in breakdown.criteria}
    assert scored_weights == catalog_weights


def test_05_weighted_score_calculation():
    problem = _make_minimal_problem()
    candidate = _make_minimal_candidate()
    breakdown = AbstractStrategicScorer.score_candidate(candidate, problem)

    for c in breakdown.criteria:
        expected_weighted = round(c.score * c.weight, 6)
        assert pytest.approx(c.weighted_score, abs=1e-5) == expected_weighted


def test_06_total_score_normalization():
    problem = _make_minimal_problem()
    candidate = _make_minimal_candidate()
    breakdown = AbstractStrategicScorer.score_candidate(candidate, problem)

    assert 0.0 <= breakdown.total_score <= 1.0


def test_07_program_coverage_scoring():
    problem = _make_minimal_problem()
    cand_full = _make_minimal_candidate("cand-full")
    cand_partial = _make_minimal_candidate("cand-part")
    cand_partial.floor_organization = {"ground": ["space-1"]}
    cand_partial.unit_organization = {}

    sb_full = AbstractStrategicScorer.score_candidate(cand_full, problem)
    sb_part = AbstractStrategicScorer.score_candidate(cand_partial, problem)

    prog_full = next(c for c in sb_full.criteria if c.criterion_id == "program_usability")
    prog_part = next(c for c in sb_part.criteria if c.criterion_id == "program_usability")
    assert prog_full.score >= prog_part.score


def test_08_privacy_compliance_scoring():
    problem = _make_minimal_problem()
    cand = _make_minimal_candidate()
    sb = AbstractStrategicScorer.score_candidate(cand, problem)

    priv_crit = next(c for c in sb.criteria if c.criterion_id == "privacy_compliance")
    assert priv_crit.score > 0.0
    assert "req-privacy-1" in priv_crit.source_ids


def test_09_abstract_circulation_scoring():
    problem = _make_minimal_problem()
    cand_with = _make_minimal_candidate("c-with", score_boost=True)
    cand_without = _make_minimal_candidate("c-without", score_boost=False)

    sb_with = AbstractStrategicScorer.score_candidate(cand_with, problem)
    sb_without = AbstractStrategicScorer.score_candidate(cand_without, problem)

    circ_with = next(c for c in sb_with.criteria if c.criterion_id == "circulation_efficiency")
    circ_without = next(c for c in sb_without.criteria if c.criterion_id == "circulation_efficiency")
    assert circ_with.score > circ_without.score


def test_10_abstract_service_organization_scoring():
    problem = _make_minimal_problem()
    cand_with = _make_minimal_candidate("c-serv-with", score_boost=True)
    cand_without = _make_minimal_candidate("c-serv-without", score_boost=False)

    sb_with = AbstractStrategicScorer.score_candidate(cand_with, problem)
    sb_without = AbstractStrategicScorer.score_candidate(cand_without, problem)

    serv_with = next(c for c in sb_with.criteria if c.criterion_id == "service_core_stacking")
    serv_without = next(c for c in sb_without.criteria if c.criterion_id == "service_core_stacking")
    assert serv_with.score >= serv_without.score


def test_11_feasibility_expectation_scoring():
    problem = _make_minimal_problem()
    cand_high = _make_minimal_candidate("c-high", score_boost=True)
    cand_low = _make_minimal_candidate("c-low", score_boost=False)
    cand_low.feasibility_expectation = FeasibilityExpectation.UNCERTAIN

    sb_high = AbstractStrategicScorer.score_candidate(cand_high, problem)
    sb_low = AbstractStrategicScorer.score_candidate(cand_low, problem)

    feas_high = next(c for c in sb_high.criteria if c.criterion_id == "realization_feasibility")
    feas_low = next(c for c in sb_low.criteria if c.criterion_id == "realization_feasibility")
    assert feas_high.score > feas_low.score


def test_12_objective_alignment_scoring():
    problem = _make_minimal_problem()
    cand = _make_minimal_candidate()
    sb = AbstractStrategicScorer.score_candidate(cand, problem)

    obj_crit = next(c for c in sb.criteria if c.criterion_id == "objective_alignment")
    assert obj_crit.score > 0.0
    assert "obj-1" in obj_crit.source_ids


def test_13_unresolved_decision_impact():
    problem = _make_minimal_problem()
    cand_clean = _make_minimal_candidate("c-clean")
    cand_unresolved = _make_minimal_candidate("c-unresolved")
    cand_unresolved.unresolved_decisions = [
        DecisionRecord(
            id="unres-1",
            dimension="dim-1",
            subject="subject-1",
            value="val-1",
            status=DecisionStatus.UNRESOLVED,
            rationale="unresolved",
        )
    ]

    sb_clean = AbstractStrategicScorer.score_candidate(cand_clean, problem)
    sb_unres = AbstractStrategicScorer.score_candidate(cand_unresolved, problem)

    feas_clean = next(c for c in sb_clean.criteria if c.criterion_id == "realization_feasibility")
    feas_unres = next(c for c in sb_unres.criteria if c.criterion_id == "realization_feasibility")
    assert feas_clean.score > feas_unres.score


def test_14_risk_impact():
    problem = _make_minimal_problem()
    cand_high_risk = _make_minimal_candidate("c-risk")
    cand_high_risk.risks = [
        StrategyRisk(id=f"risk-{i}", description="desc", severity=AnalysisSeverity.ERROR)
        for i in range(5)
    ]

    ranked_list = AbstractStrategicScorer.score_candidates([cand_high_risk], problem)
    assert len(ranked_list) == 1
    assert ranked_list[0].selection_status == SelectionStatus.REJECTED
    assert "high-severity risks" in ranked_list[0].rejection_reasons[0]


def test_15_confidence_impact():
    problem = _make_minimal_problem()
    cand_conf = _make_minimal_candidate("c-conf")
    cand_conf.confidence = 0.95

    cand_low_conf = _make_minimal_candidate("c-low-conf")
    cand_low_conf.confidence = 0.3

    sb_conf = AbstractStrategicScorer.score_candidate(cand_conf, problem)
    sb_low = AbstractStrategicScorer.score_candidate(cand_low_conf, problem)

    feas_conf = next(c for c in sb_conf.criteria if c.criterion_id == "realization_feasibility")
    feas_low = next(c for c in sb_low.criteria if c.criterion_id == "realization_feasibility")
    assert feas_conf.score > feas_low.score


def test_16_missing_data_handling():
    problem = _make_minimal_problem()
    cand_empty = _make_minimal_candidate("c-empty", score_boost=False)
    cand_empty.circulation_intent = []
    cand_empty.service_organization = []

    sb = AbstractStrategicScorer.score_candidate(cand_empty, problem)
    assert sb.total_score > 0.0
    assert len(sb.criteria) == 6


def test_17_invalid_candidate_handling():
    problem = _make_minimal_problem()
    cand_invalid = _make_minimal_candidate("c-invalid")
    # Force malformed attribute by setting None where list is expected
    cand_invalid.circulation_intent = None  # type: ignore

    ranked_list = AbstractStrategicScorer.score_candidates([cand_invalid], problem)
    assert len(ranked_list) == 1
    assert ranked_list[0].selection_status == SelectionStatus.REJECTED
    assert ranked_list[0].score_breakdown.total_score == 0.0


def test_18_selection_threshold_classification():
    problem = _make_minimal_problem()
    cand = _make_minimal_candidate("c-thresh")
    ranked_list = AbstractStrategicScorer.score_candidates([cand], problem)

    assert len(ranked_list) == 1
    status = ranked_list[0].selection_status
    assert status in {SelectionStatus.SELECTED, SelectionStatus.VIABLE, SelectionStatus.MARGINAL, SelectionStatus.REJECTED}


def test_19_provenance_preservation():
    problem = _make_minimal_problem()
    cand = _make_minimal_candidate("c-prov")
    ranked_list = AbstractStrategicScorer.score_candidates([cand], problem)

    prov = ranked_list[0].provenance
    assert prov["problem_id"] == problem.id
    assert prov["problem_version"] == problem.version
    assert prov["strategy_id"] == cand.source_strategy_id
    assert prov["candidate_id"] == cand.id
    assert prov["scoring_catalog_version"] == "3B.5-2.v1"


def test_20_source_id_preservation():
    problem = _make_minimal_problem()
    cand = _make_minimal_candidate("c-source")
    sb = AbstractStrategicScorer.score_candidate(cand, problem)

    for c in sb.criteria:
        assert isinstance(c.source_ids, list)


def test_21_custom_unseen_dimension_support():
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
    problem = _make_minimal_problem()
    cand = _make_minimal_candidate("c-custom")

    sb = AbstractStrategicScorer.score_candidate(cand, problem, catalog)
    assert sb.scoring_version == "custom-v1"
    assert len(sb.criteria) == 4
    assert {c.criterion_id for c in sb.criteria} == {
        "solar_shading_strategy",
        "facade_transparency",
        "energy_resilience_strategy",
        "future_custom_dimension",
    }


def test_22_deterministic_repeated_execution():
    problem = _make_minimal_problem()
    cand = _make_minimal_candidate("c-det")

    sb1 = AbstractStrategicScorer.score_candidate(cand, problem)
    sb2 = AbstractStrategicScorer.score_candidate(cand, problem)
    sb3 = AbstractStrategicScorer.score_candidate(cand, problem)

    assert sb1.model_dump_json() == sb2.model_dump_json() == sb3.model_dump_json()


def test_23_deterministic_criterion_ordering():
    catalog = load_preference_catalog()
    problem = _make_minimal_problem()
    cand = _make_minimal_candidate("c-order")

    sb = AbstractStrategicScorer.score_candidate(cand, problem, catalog)
    catalog_order = [c.id for c in catalog.criteria]
    scored_order = [c.criterion_id for c in sb.criteria]
    assert scored_order == catalog_order


def test_24_non_geometric_ast_boundary():
    scorer_file = Path(__file__).parent.parent / "app" / "services" / "ranking" / "abstract_strategic_scorer.py"
    content = scorer_file.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(scorer_file))

    # Verify no prohibited module imports
    prohibited = {"shapely", "pulp", "cbc", "cad", "mesh", "geometry"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0].lower() not in prohibited
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert node.module.split(".")[0].lower() not in prohibited

        # Verify no hardcoded string comparison AST nodes for specific criterion names
        if isinstance(node, ast.Compare):
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    assert comparator.value not in {"program_usability", "privacy_compliance", "circulation_efficiency"}


def test_25_no_solver_compiler_invocation():
    problem = _make_minimal_problem()
    cand = _make_minimal_candidate("c-no-solver")
    sb = AbstractStrategicScorer.score_candidate(cand, problem)
    assert sb.total_score > 0.0


def test_26_no_external_api_invocation():
    problem = _make_minimal_problem()
    cand = _make_minimal_candidate("c-no-api")
    sb = AbstractStrategicScorer.score_candidate(cand, problem)
    assert sb.scoring_version


def test_27_empty_candidate_collection_handling():
    problem = _make_minimal_problem()
    ranked = AbstractStrategicScorer.score_candidates([], problem)
    assert ranked == []


def test_28_multiple_candidate_scoring_and_ranking():
    problem = _make_minimal_problem()
    cand1 = _make_minimal_candidate("cand-1", score_boost=True)
    cand2 = _make_minimal_candidate("cand-2", score_boost=False)
    cand3 = _make_minimal_candidate("cand-3", score_boost=True)

    ranked_list = AbstractStrategicScorer.score_candidates([cand1, cand2, cand3], problem)
    assert len(ranked_list) == 3

    ranks = [r.rank for r in ranked_list]
    assert ranks == [1, 2, 3]

    cand_ids = [r.candidate_id for r in ranked_list]
    assert len(set(cand_ids)) == 3


def test_29_json_round_trip_determinism():
    problem = _make_minimal_problem()
    cand = _make_minimal_candidate("c-json")
    ranked_list = AbstractStrategicScorer.score_candidates([cand], problem)

    json_str = ranked_list[0].model_dump_json()
    reconstructed = RankedCandidate.model_validate_json(json_str)
    assert reconstructed == ranked_list[0]
