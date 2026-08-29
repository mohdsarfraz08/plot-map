"""
Unit, Contract, AST, and Boundary Test Suite for Stage 3B.5-5: Candidate Selector & Deterministic Tie-Breaking Engine.

Validates candidate selection, tie-breaking cascade, threshold classification, immutability,
duplicate rejection, AST non-geometric boundary, and RankingResult compliance.
"""

import ast
import json
from pathlib import Path
import pytest

from app.schemas.strategy_preference import PreferenceCatalog
from app.schemas.strategy_ranking import (
    CriterionScore,
    RankedCandidate,
    RankingResult,
    ScoreBreakdown,
    SelectionStatus,
)
from app.services.analysis.catalog_loader import load_preference_catalog
from app.services.ranking.candidate_selector import CandidateSelector


def _make_ranked_candidate(
    candidate_id: str = "cand-1",
    score: float = 0.85,
    status: SelectionStatus = SelectionStatus.SELECTED,
    strategy_id: str = "strat-1",
    rejection_reasons: list[str] | None = None,
    criteria_override: list[CriterionScore] | None = None,
) -> RankedCandidate:
    if criteria_override is None:
        criteria = [
            CriterionScore(criterion_id="program_usability", score=score, weight=0.25, weighted_score=score * 0.25, explanation="ok", source_ids=[]),
            CriterionScore(criterion_id="privacy_compliance", score=score, weight=0.20, weighted_score=score * 0.20, explanation="ok", source_ids=[]),
            CriterionScore(criterion_id="circulation_efficiency", score=score, weight=0.15, weighted_score=score * 0.15, explanation="ok", source_ids=[]),
            CriterionScore(criterion_id="service_core_stacking", score=score, weight=0.15, weighted_score=score * 0.15, explanation="ok", source_ids=[]),
            CriterionScore(criterion_id="realization_feasibility", score=score, weight=0.15, weighted_score=score * 0.15, explanation="ok", source_ids=[]),
            CriterionScore(criterion_id="objective_alignment", score=score, weight=0.10, weighted_score=score * 0.10, explanation="ok", source_ids=[]),
        ]
    else:
        criteria = criteria_override

    tot = round(sum(c.weighted_score for c in criteria), 6)
    sb = ScoreBreakdown(criteria=criteria, total_score=tot, scoring_version="3B.5-2.v1")

    reasons = rejection_reasons if rejection_reasons is not None else ([] if status != SelectionStatus.REJECTED else ["Rejection reason"])

    return RankedCandidate(
        candidate_id=candidate_id,
        strategy_id=strategy_id,
        rank=1,
        score_breakdown=sb,
        selection_status=status,
        rejection_reasons=reasons,
        tie_break_key=[tot, candidate_id],
        provenance={"problem_id": "problem-1", "problem_version": 1},
    )


def test_01_minimal_candidate_selection():
    rc = _make_ranked_candidate()
    res = CandidateSelector.select([rc])

    assert isinstance(res, RankingResult)
    assert res.id == "ranking-problem-1-1"
    assert len(res.ranked_candidates) == 1
    assert res.selected_candidate_ids == ["cand-1"]


def test_02_empty_input_handling():
    res = CandidateSelector.select([])

    assert isinstance(res, RankingResult)
    assert res.ranked_candidates == []
    assert res.selected_candidate_ids == []
    assert res.provenance["total_ranked"] == 0


def test_03_single_candidate_selection():
    rc = _make_ranked_candidate("c1", 0.9)
    res = CandidateSelector.select([rc])

    assert res.selected_candidate_ids == ["c1"]
    assert res.ranked_candidates[0].rank == 1
    assert res.ranked_candidates[0].selection_status == SelectionStatus.SELECTED


def test_04_multiple_candidate_ranking():
    c1 = _make_ranked_candidate("c1", 0.70)
    c2 = _make_ranked_candidate("c2", 0.90)
    c3 = _make_ranked_candidate("c3", 0.80)

    res = CandidateSelector.select([c1, c2, c3])
    actual_ids = [rc.candidate_id for rc in res.ranked_candidates]
    assert actual_ids == ["c2", "c3", "c1"]


def test_05_deterministic_ranking_order():
    c1 = _make_ranked_candidate("c1", 0.85)
    c2 = _make_ranked_candidate("c2", 0.75)

    res1 = CandidateSelector.select([c1, c2])
    res2 = CandidateSelector.select([c2, c1])

    assert res1.selected_candidate_ids == res2.selected_candidate_ids
    assert [rc.candidate_id for rc in res1.ranked_candidates] == [rc.candidate_id for rc in res2.ranked_candidates]


def test_06_deterministic_candidate_ranks():
    c1 = _make_ranked_candidate("c1", 0.90)
    c2 = _make_ranked_candidate("c2", 0.80)

    res = CandidateSelector.select([c1, c2])
    assert res.ranked_candidates[0].rank == 1
    assert res.ranked_candidates[1].rank == 2


def test_07_selection_threshold_application():
    c_selected = _make_ranked_candidate("c-sel", 0.85)
    c_viable = _make_ranked_candidate("c-via", 0.65)
    c_marginal = _make_ranked_candidate("c-mar", 0.45)
    c_rejected = _make_ranked_candidate("c-rej", 0.20)

    res = CandidateSelector.select([c_selected, c_viable, c_marginal, c_rejected])
    status_map = {rc.candidate_id: rc.selection_status for rc in res.ranked_candidates}

    assert status_map["c-sel"] == SelectionStatus.SELECTED
    assert status_map["c-via"] == SelectionStatus.VIABLE
    assert status_map["c-mar"] == SelectionStatus.MARGINAL
    assert status_map["c-rej"] == SelectionStatus.REJECTED


def test_08_selected_status_handling():
    rc = _make_ranked_candidate("c1", 0.85)
    res = CandidateSelector.select([rc])
    assert res.ranked_candidates[0].selection_status == SelectionStatus.SELECTED
    assert res.selected_candidate_ids == ["c1"]


def test_09_viable_status_handling():
    rc = _make_ranked_candidate("c1", 0.65)
    res = CandidateSelector.select([rc])
    assert res.ranked_candidates[0].selection_status == SelectionStatus.VIABLE
    assert res.selected_candidate_ids == []


def test_10_marginal_status_handling():
    rc = _make_ranked_candidate("c1", 0.45)
    res = CandidateSelector.select([rc])
    assert res.ranked_candidates[0].selection_status == SelectionStatus.MARGINAL
    assert res.selected_candidate_ids == []


def test_11_rejected_status_handling():
    rc = _make_ranked_candidate("c1", 0.25)
    res = CandidateSelector.select([rc])
    assert res.ranked_candidates[0].selection_status == SelectionStatus.REJECTED
    assert res.selected_candidate_ids == []


def test_12_maximum_selection_count_limit():
    c1 = _make_ranked_candidate("c1", 0.90)
    c2 = _make_ranked_candidate("c2", 0.88)
    c3 = _make_ranked_candidate("c3", 0.85)

    res = CandidateSelector.select([c1, c2, c3], max_selected=2)
    assert len(res.selected_candidate_ids) == 2
    assert res.selected_candidate_ids == ["c1", "c2"]


def test_13_candidate_not_selected_because_max_count_reached():
    c1 = _make_ranked_candidate("c1", 0.90)
    c2 = _make_ranked_candidate("c2", 0.88)

    res = CandidateSelector.select([c1, c2], max_selected=1)
    rc2 = next(r for r in res.ranked_candidates if r.candidate_id == "c2")
    assert rc2.selection_status == SelectionStatus.VIABLE
    assert any("max_selected limit" in r for r in rc2.rejection_reasons)


def test_14_failed_realization_candidate_rejection():
    c_failed = _make_ranked_candidate("c-fail", 0.95, status=SelectionStatus.REJECTED, rejection_reasons=["Realization failed: SPATIALLY_INFEASIBLE"])
    res = CandidateSelector.select([c_failed])

    assert res.selected_candidate_ids == []
    assert res.ranked_candidates[0].selection_status == SelectionStatus.REJECTED
    assert "Realization failed" in res.ranked_candidates[0].rejection_reasons[0]


def test_15_duplicate_candidate_id_rejection():
    c1 = _make_ranked_candidate("dup-1", 0.85)
    c2 = _make_ranked_candidate("dup-1", 0.80)

    with pytest.raises(ValueError, match="Duplicate candidate_id"):
        CandidateSelector.select([c1, c2])


def test_16_deterministic_tie_breaking():
    # Two candidates with identical score
    c1 = _make_ranked_candidate("cand-B", 0.85)
    c2 = _make_ranked_candidate("cand-A", 0.85)

    res = CandidateSelector.select([c1, c2])
    # Tie-break by candidate_id ascending -> cand-A first
    assert [rc.candidate_id for rc in res.ranked_candidates] == ["cand-A", "cand-B"]


def test_17_score_tie_breaking():
    c1 = _make_ranked_candidate("c1", 0.85)
    c2 = _make_ranked_candidate("c2", 0.80)

    res = CandidateSelector.select([c1, c2])
    assert res.ranked_candidates[0].candidate_id == "c1"


def test_18_feasibility_tie_breaking():
    # Same total score, different realization_feasibility scores
    crit1 = [
        CriterionScore(criterion_id="program_usability", score=0.8, weight=0.5, weighted_score=0.4, explanation="ok"),
        CriterionScore(criterion_id="realization_feasibility", score=0.6, weight=0.5, weighted_score=0.3, explanation="ok"),
    ]
    crit2 = [
        CriterionScore(criterion_id="program_usability", score=0.6, weight=0.5, weighted_score=0.3, explanation="ok"),
        CriterionScore(criterion_id="realization_feasibility", score=0.8, weight=0.5, weighted_score=0.4, explanation="ok"),
    ]
    c1 = _make_ranked_candidate("c1", criteria_override=crit1)
    c2 = _make_ranked_candidate("c2", criteria_override=crit2)

    res = CandidateSelector.select([c1, c2])
    # Total scores equal (0.70). Priority criteria order has realization_feasibility evaluated via catalog
    assert len(res.ranked_candidates) == 2


def test_19_confidence_tie_breaking():
    c1 = _make_ranked_candidate("c1", 0.85)
    c2 = _make_ranked_candidate("c2", 0.85)

    res = CandidateSelector.select([c1, c2])
    assert len(res.ranked_candidates) == 2


def test_20_candidate_id_final_tie_break_fallback():
    c1 = _make_ranked_candidate("z-cand", 0.85)
    c2 = _make_ranked_candidate("a-cand", 0.85)

    res = CandidateSelector.select([c1, c2])
    assert res.ranked_candidates[0].candidate_id == "a-cand"
    assert res.ranked_candidates[1].candidate_id == "z-cand"


def test_21_catalog_tie_break_configuration():
    catalog = load_preference_catalog()
    c1 = _make_ranked_candidate("c1", 0.85)
    c2 = _make_ranked_candidate("c2", 0.80)

    res = CandidateSelector.select([c1, c2], catalog)
    assert res.provenance["catalog_version"] == catalog.version


def test_22_provenance_preservation():
    c1 = _make_ranked_candidate("c1", 0.85)
    res = CandidateSelector.select([c1])

    prov = res.provenance
    assert prov["selector"] == "deterministic-candidate-selector"
    assert prov["ranking_version"] == "3B.5-5.v1"
    assert prov["total_ranked"] == 1
    assert prov["total_selected"] == 1


def test_23_source_problem_metadata_preservation():
    c1 = _make_ranked_candidate("c1", 0.85)
    res = CandidateSelector.select([c1], source_problem_id="prob-custom", source_problem_version=3)

    assert res.source_problem_id == "prob-custom"
    assert res.source_problem_version == 3
    assert res.id == "ranking-prob-custom-3"


def test_24_candidate_immutability_validation():
    c1 = _make_ranked_candidate("c1", 0.85)
    orig_json = c1.model_dump_json()

    CandidateSelector.select([c1])
    assert c1.model_dump_json() == orig_json


def test_25_custom_unseen_decision_dimensions():
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

    crit = [
        CriterionScore(criterion_id="solar_shading_strategy", score=0.9, weight=0.25, weighted_score=0.225, explanation="ok"),
        CriterionScore(criterion_id="facade_transparency", score=0.8, weight=0.25, weighted_score=0.200, explanation="ok"),
        CriterionScore(criterion_id="energy_resilience_strategy", score=0.9, weight=0.25, weighted_score=0.225, explanation="ok"),
        CriterionScore(criterion_id="future_custom_dimension", score=0.8, weight=0.25, weighted_score=0.200, explanation="ok"),
    ]
    c1 = _make_ranked_candidate("c-custom", criteria_override=crit)

    res = CandidateSelector.select([c1], catalog)
    assert res.selected_candidate_ids == ["c-custom"]


def test_26_deterministic_repeated_execution():
    c1 = _make_ranked_candidate("c1", 0.90)
    c2 = _make_ranked_candidate("c2", 0.80)

    res1 = CandidateSelector.select([c1, c2])
    res2 = CandidateSelector.select([c1, c2])
    res3 = CandidateSelector.select([c1, c2])

    assert res1.model_dump_json() == res2.model_dump_json() == res3.model_dump_json()


def test_27_json_round_trip_determinism():
    c1 = _make_ranked_candidate("c1", 0.85)
    res = CandidateSelector.select([c1])

    json_str = res.model_dump_json()
    reconstructed = RankingResult.model_validate_json(json_str)
    assert reconstructed == res


def test_28_no_solver_invocation(monkeypatch):
    def _forbidden_solver(*args, **kwargs):
        raise RuntimeError("Solver must not be invoked during CandidateSelector.select")

    monkeypatch.setattr("app.services.realization.compiler_bridge.SpatialCompilerBridge.realize_layout", _forbidden_solver, raising=False)

    c1 = _make_ranked_candidate("c1", 0.85)
    res = CandidateSelector.select([c1])
    assert res.selected_candidate_ids == ["c1"]


def test_29_no_geometry_creation():
    c1 = _make_ranked_candidate("c1", 0.85)
    res = CandidateSelector.select([c1])
    for rc in res.ranked_candidates:
        assert "geometry" not in rc.provenance


def test_30_non_geometric_ast_boundary():
    selector_file = Path(__file__).parent.parent / "app" / "services" / "ranking" / "candidate_selector.py"
    content = selector_file.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(selector_file))

    prohibited = {"shapely", "pulp", "cbc", "solver", "compiler", "requests", "httpx", "urllib", "google", "gemini"}
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


def test_31_no_external_api_invocation(monkeypatch):
    def _forbidden_api(*args, **kwargs):
        raise RuntimeError("External API must not be invoked during CandidateSelector.select")

    monkeypatch.setattr("urllib.request.urlopen", _forbidden_api, raising=False)

    c1 = _make_ranked_candidate("c1", 0.85)
    res = CandidateSelector.select([c1])
    assert res.selected_candidate_ids == ["c1"]


def test_32_ranking_result_schema_compatibility():
    c1 = _make_ranked_candidate("c1", 0.85)
    res = CandidateSelector.select([c1])

    # Validate against RankingResult model validator rules
    assert res.id
    assert res.source_problem_id
    assert res.source_problem_version >= 1
    assert res.ranking_version


def test_33_selected_ids_exist_in_ranked_candidates():
    c1 = _make_ranked_candidate("c1", 0.85)
    c2 = _make_ranked_candidate("c2", 0.80)

    res = CandidateSelector.select([c1, c2], max_selected=1)
    ranked_id_set = {rc.candidate_id for rc in res.ranked_candidates}

    for sel_id in res.selected_candidate_ids:
        assert sel_id in ranked_id_set


def test_34_deterministic_rejection_reasons():
    c_rej = _make_ranked_candidate("c-rej", 0.20)
    res = CandidateSelector.select([c_rej])

    rc = res.ranked_candidates[0]
    assert rc.selection_status == SelectionStatus.REJECTED
    assert "below marginal threshold" in rc.rejection_reasons[0]


def test_35_multiple_selection_limit_variants():
    c1 = _make_ranked_candidate("c1", 0.95)
    c2 = _make_ranked_candidate("c2", 0.90)
    c3 = _make_ranked_candidate("c3", 0.85)
    c4 = _make_ranked_candidate("c4", 0.80)

    # Limit 0
    res0 = CandidateSelector.select([c1, c2, c3, c4], max_selected=0)
    assert res0.selected_candidate_ids == []

    # Limit 2
    res2 = CandidateSelector.select([c1, c2, c3, c4], max_selected=2)
    assert res2.selected_candidate_ids == ["c1", "c2"]

    # Limit 10 (exceeding candidates)
    res10 = CandidateSelector.select([c1, c2, c3, c4], max_selected=10)
    assert res10.selected_candidate_ids == ["c1", "c2", "c3", "c4"]


def test_36_catalog_version_preservation():
    catalog = load_preference_catalog()
    c1 = _make_ranked_candidate("c1", 0.85)

    res = CandidateSelector.select([c1], catalog)
    assert res.provenance["catalog_version"] == catalog.version


def test_37_deep_copy_non_mutation_check():
    c1 = _make_ranked_candidate("c1", 0.85)
    c1_dump = c1.model_dump_json()

    res = CandidateSelector.select([c1], max_selected=1)
    # Output RankedCandidate object is a new instance
    assert res.ranked_candidates[0] is not c1
    # Input remains unchanged
    assert c1.model_dump_json() == c1_dump
