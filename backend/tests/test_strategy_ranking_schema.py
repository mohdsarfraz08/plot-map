"""
Tests for Strategy Ranking & Selection Schema Contract (Stage 3B.5-1).
"""

import sys
import pytest
from pydantic import ValidationError

from app.schemas.strategy_ranking import (
    CriterionScore,
    RankedCandidate,
    RankingResult,
    ScoreBreakdown,
    SelectionStatus,
)


def _make_sample_score_breakdown() -> ScoreBreakdown:
    crit1 = CriterionScore(
        criterion_id="program_usability",
        score=0.85,
        weight=0.5,
        weighted_score=0.425,
        explanation="High room requirement satisfaction",
        source_ids=["req-1"],
    )
    crit2 = CriterionScore(
        criterion_id="circulation_efficiency",
        score=0.90,
        weight=0.5,
        weighted_score=0.45,
        explanation="Optimal circulation node connectivity",
        source_ids=["dim-vertical_circulation"],
    )
    return ScoreBreakdown(
        criteria=[crit1, crit2],
        total_score=0.875,
        scoring_version="1.0.0",
    )


def _make_sample_ranked_candidate(
    cand_id: str = "cand-001",
    strategy_id: str = "strat-001",
    rank: int = 1,
    status: SelectionStatus = SelectionStatus.SELECTED,
    reasons: list[str] | None = None,
) -> RankedCandidate:
    if reasons is None:
        reasons = [] if status != SelectionStatus.REJECTED else ["Envelope overflow"]
    return RankedCandidate(
        candidate_id=cand_id,
        strategy_id=strategy_id,
        rank=rank,
        score_breakdown=_make_sample_score_breakdown(),
        selection_status=status,
        rejection_reasons=reasons,
        tie_break_key=[0.875, 1, cand_id],
        provenance={"generator": "CandidateGenerator", "organized_by": "CandidateOrganizer"},
    )


def test_01_minimal_valid_criterion_score():
    """Point 1: Verify minimal valid CriterionScore construction."""
    cs = CriterionScore(
        criterion_id="usability",
        score=1.0,
        weight=0.5,
        weighted_score=0.5,
        explanation="Perfect score",
    )
    assert cs.criterion_id == "usability"
    assert cs.score == 1.0
    assert cs.weight == 0.5
    assert cs.weighted_score == 0.5
    assert cs.explanation == "Perfect score"
    assert cs.source_ids == []


def test_02_criterion_score_bounds():
    """Point 2: Verify score bounds [0.0, 1.0]."""
    invalid_low_score: float = -0.1
    invalid_high_score: float = 1.1
    with pytest.raises(ValidationError):
        CriterionScore(
            criterion_id="c1",
            score=invalid_low_score,  # type: ignore[arg-type]
            weight=0.5,
            weighted_score=0.0,
            explanation="Invalid score",
        )
    with pytest.raises(ValidationError):
        CriterionScore(
            criterion_id="c1",
            score=invalid_high_score,  # type: ignore[arg-type]
            weight=0.5,
            weighted_score=0.55,
            explanation="Invalid score",
        )


def test_03_criterion_weight_bounds():
    """Point 3: Verify weight bounds [0.0, 1.0]."""
    invalid_low_weight: float = -0.1
    invalid_high_weight: float = 1.5
    with pytest.raises(ValidationError):
        CriterionScore(
            criterion_id="c1",
            score=0.5,
            weight=invalid_low_weight,  # type: ignore[arg-type]
            weighted_score=0.0,
            explanation="Invalid weight",
        )
    with pytest.raises(ValidationError):
        CriterionScore(
            criterion_id="c1",
            score=0.5,
            weight=invalid_high_weight,  # type: ignore[arg-type]
            weighted_score=0.75,
            explanation="Invalid weight",
        )


def test_04_score_breakdown_construction():
    """Point 4: Verify ScoreBreakdown construction."""
    sb = _make_sample_score_breakdown()
    assert len(sb.criteria) == 2
    assert sb.total_score == 0.875
    assert sb.scoring_version == "1.0.0"


def test_05_duplicate_criterion_id_rejection():
    """Point 5: Verify duplicate criterion ID rejection in ScoreBreakdown."""
    c1 = CriterionScore(criterion_id="dup", score=0.5, weight=0.5, weighted_score=0.25, explanation="C1")
    c2 = CriterionScore(criterion_id="dup", score=0.8, weight=0.5, weighted_score=0.40, explanation="C2")
    with pytest.raises(ValidationError, match="Criterion IDs must be unique"):
        ScoreBreakdown(criteria=[c1, c2], total_score=0.65, scoring_version="1.0.0")


def test_06_ranked_candidate_construction():
    """Point 6: Verify RankedCandidate construction."""
    rc = _make_sample_ranked_candidate()
    assert rc.candidate_id == "cand-001"
    assert rc.strategy_id == "strat-001"
    assert rc.rank == 1
    assert rc.selection_status == SelectionStatus.SELECTED
    assert rc.rejection_reasons == []


def test_07_rank_validation():
    """Point 7: Verify rank >= 1 validation."""
    invalid_rank: int = 0
    with pytest.raises(ValidationError):
        _make_sample_ranked_candidate(rank=invalid_rank)  # type: ignore[arg-type]


def test_08_selection_status_enum_validation():
    """Point 8: Verify SelectionStatus enum values."""
    assert SelectionStatus.SELECTED == "selected"
    assert SelectionStatus.VIABLE == "viable"
    assert SelectionStatus.MARGINAL == "marginal"
    assert SelectionStatus.REJECTED == "rejected"

    with pytest.raises(ValidationError):
        RankedCandidate(
            candidate_id="c1",
            strategy_id="s1",
            rank=1,
            score_breakdown=_make_sample_score_breakdown(),
            selection_status="invalid_status",
        )


def test_09_rejected_candidate_requires_rejection_reason():
    """Point 9: Verify REJECTED candidate requires non-empty rejection_reasons."""
    with pytest.raises(ValidationError, match="rejection_reasons"):
        _make_sample_ranked_candidate(status=SelectionStatus.REJECTED, reasons=[])

    rc = _make_sample_ranked_candidate(status=SelectionStatus.REJECTED, reasons=["Envelope overflow"])
    assert rc.selection_status == SelectionStatus.REJECTED
    assert "Envelope overflow" in rc.rejection_reasons


def test_10_ranking_result_construction():
    """Point 10: Verify RankingResult construction."""
    rc1 = _make_sample_ranked_candidate("cand-001", rank=1, status=SelectionStatus.SELECTED)
    rc2 = _make_sample_ranked_candidate("cand-002", rank=2, status=SelectionStatus.VIABLE)
    rr = RankingResult(
        id="rank-res-001",
        source_problem_id="prob-001",
        source_problem_version=1,
        ranked_candidates=[rc1, rc2],
        selected_candidate_ids=["cand-001"],
        ranking_version="1.0.0",
        provenance={"catalog_version": "1.0.0"},
    )
    assert rr.id == "rank-res-001"
    assert rr.source_problem_id == "prob-001"
    assert rr.source_problem_version == 1
    assert len(rr.ranked_candidates) == 2
    assert rr.selected_candidate_ids == ["cand-001"]


def test_11_duplicate_ranked_candidate_id_rejection():
    """Point 11: Verify duplicate ranked candidate ID rejection in RankingResult."""
    rc1 = _make_sample_ranked_candidate("dup-cand", rank=1)
    rc2 = _make_sample_ranked_candidate("dup-cand", rank=2)
    with pytest.raises(ValidationError, match="Candidate IDs must be unique"):
        RankingResult(
            id="rr-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            ranked_candidates=[rc1, rc2],
            selected_candidate_ids=["dup-cand"],
            ranking_version="1.0.0",
        )


def test_12_duplicate_selected_candidate_id_rejection():
    """Point 12: Verify duplicate selected candidate ID rejection in RankingResult."""
    rc1 = _make_sample_ranked_candidate("c1", rank=1)
    with pytest.raises(ValidationError, match="selected_candidate_ids must contain unique IDs"):
        RankingResult(
            id="rr-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            ranked_candidates=[rc1],
            selected_candidate_ids=["c1", "c1"],
            ranking_version="1.0.0",
        )


def test_13_selected_candidate_must_exist_in_ranked_candidates():
    """Point 13: Verify selected candidate ID must exist in ranked_candidates list."""
    rc1 = _make_sample_ranked_candidate("c1", rank=1)
    with pytest.raises(ValidationError, match="Selected candidate_id 'c999' must exist"):
        RankingResult(
            id="rr-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            ranked_candidates=[rc1],
            selected_candidate_ids=["c999"],
            ranking_version="1.0.0",
        )


def test_14_source_problem_version_validation():
    """Point 14: Verify source_problem_version >= 1 validation."""
    rc1 = _make_sample_ranked_candidate("c1", rank=1)
    invalid_version: int = 0
    with pytest.raises(ValidationError):
        RankingResult(
            id="rr-1",
            source_problem_id="prob-1",
            source_problem_version=invalid_version,  # type: ignore[arg-type]
            ranked_candidates=[rc1],
            selected_candidate_ids=["c1"],
            ranking_version="1.0.0",
        )


def test_15_provenance_preservation():
    """Point 15: Verify provenance preservation on RankedCandidate and RankingResult."""
    prov = {"strategy": "independent", "rules_applied": ["rule-1", "rule-2"]}
    rc = RankedCandidate(
        candidate_id="c1",
        strategy_id="s1",
        rank=1,
        score_breakdown=_make_sample_score_breakdown(),
        selection_status=SelectionStatus.SELECTED,
        provenance=prov,
    )
    assert rc.provenance == prov


def test_16_custom_unseen_metadata_dimensions():
    """Point 16: Verify custom/unseen dimensions survive in provenance and tie_break_key."""
    custom_prov = {
        "solar_shading_strategy": "dynamic_louvers",
        "facade_transparency": 0.75,
        "custom_dimension_alpha": "custom_val",
    }
    rc = RankedCandidate(
        candidate_id="c1",
        strategy_id="s1",
        rank=1,
        score_breakdown=_make_sample_score_breakdown(),
        selection_status=SelectionStatus.SELECTED,
        tie_break_key=[0.95, "custom_val"],
        provenance=custom_prov,
    )
    assert rc.provenance["solar_shading_strategy"] == "dynamic_louvers"
    assert rc.provenance["custom_dimension_alpha"] == "custom_val"
    assert rc.tie_break_key == [0.95, "custom_val"]


def test_17_json_serialization():
    """Point 17: Verify JSON serialization."""
    rc1 = _make_sample_ranked_candidate("c1", rank=1)
    rr = RankingResult(
        id="rr-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        ranked_candidates=[rc1],
        selected_candidate_ids=["c1"],
        ranking_version="1.0.0",
    )
    json_str = rr.model_dump_json()
    assert isinstance(json_str, str)
    assert "prob-1" in json_str
    assert "selected" in json_str


def test_18_json_round_trip():
    """Point 18: Verify JSON round-trip model validation."""
    rc1 = _make_sample_ranked_candidate("c1", rank=1)
    rr1 = RankingResult(
        id="rr-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        ranked_candidates=[rc1],
        selected_candidate_ids=["c1"],
        ranking_version="1.0.0",
    )
    json_str = rr1.model_dump_json()
    rr2 = RankingResult.model_validate_json(json_str)
    assert rr2.id == rr1.id
    assert rr2.source_problem_id == rr1.source_problem_id
    assert rr2.ranked_candidates[0].candidate_id == "c1"
    assert rr2.selected_candidate_ids == ["c1"]


def test_19_deterministic_serialization():
    """Point 19: Verify deterministic serialization output across repeated calls."""
    rc1 = _make_sample_ranked_candidate("c1", rank=1)
    rr = RankingResult(
        id="rr-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        ranked_candidates=[rc1],
        selected_candidate_ids=["c1"],
        ranking_version="1.0.0",
    )
    dump1 = rr.model_dump_json()
    dump2 = rr.model_dump_json()
    assert dump1 == dump2


def test_20_non_geometric_boundary_verification():
    """Point 20: Verify non-geometric boundary guard rejects prohibited keys."""
    with pytest.raises(ValidationError, match="prohibited geometric"):
        RankedCandidate(
            candidate_id="c1",
            strategy_id="s1",
            rank=1,
            score_breakdown=_make_sample_score_breakdown(),
            selection_status=SelectionStatus.SELECTED,
            provenance={"coordinates": [10.0, 20.0]},
        )

    with pytest.raises(ValidationError, match="prohibited geometric"):
        RankingResult(
            id="rr-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            ranked_candidates=[],
            selected_candidate_ids=[],
            ranking_version="1.0.0",
            provenance={"polygon": "invalid"},
        )


def test_21_no_solver_geometry_imports():
    """Point 21: Verify strategy_ranking schema module imports zero geometry or solver modules."""
    import app.schemas.strategy_ranking as sr_module

    prohibited_modules = ["shapely", "pulp", "cbc", "app.services.optimization.solver", "app.services.compiler.serializer"]
    for mod_name in prohibited_modules:
        assert mod_name not in sys.modules or not hasattr(sr_module, mod_name)


def test_22_empty_candidate_collection_behavior():
    """Point 22: Verify valid RankingResult with empty candidate collection."""
    rr = RankingResult(
        id="rr-empty",
        source_problem_id="prob-empty",
        source_problem_version=1,
        ranked_candidates=[],
        selected_candidate_ids=[],
        ranking_version="1.0.0",
    )
    assert rr.ranked_candidates == []
    assert rr.selected_candidate_ids == []


def test_23_multiple_ranked_candidates_preserve_ordering():
    """Point 23: Verify ordering of multiple ranked candidates is preserved."""
    rc1 = _make_sample_ranked_candidate("c1", rank=1, status=SelectionStatus.SELECTED)
    rc2 = _make_sample_ranked_candidate("c2", rank=2, status=SelectionStatus.VIABLE)
    rc3 = _make_sample_ranked_candidate("c3", rank=3, status=SelectionStatus.MARGINAL)

    rr = RankingResult(
        id="rr-multi",
        source_problem_id="prob-multi",
        source_problem_version=1,
        ranked_candidates=[rc1, rc2, rc3],
        selected_candidate_ids=["c1"],
        ranking_version="1.0.0",
    )
    assert [c.candidate_id for c in rr.ranked_candidates] == ["c1", "c2", "c3"]
    assert [c.rank for c in rr.ranked_candidates] == [1, 2, 3]


def test_24_tie_break_metadata_preservation():
    """Point 24: Verify tie_break_key preservation."""
    tb_key = [0.875, 1, 0.95, "cand-001"]
    rc = RankedCandidate(
        candidate_id="cand-001",
        strategy_id="strat-001",
        rank=1,
        score_breakdown=_make_sample_score_breakdown(),
        selection_status=SelectionStatus.SELECTED,
        tie_break_key=tb_key,
    )
    assert rc.tie_break_key == tb_key
