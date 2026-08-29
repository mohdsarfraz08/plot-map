import json
import pytest
from pydantic import ValidationError

from app.schemas.architectural_analysis import (
    AnalysisSeverity,
    DecisionDimension,
    DecisionRecord,
    DecisionStatus,
)
from app.schemas.design_candidate import (
    AbstractCirculationNode,
    AbstractServiceStack,
    DesignCandidate,
)
from app.schemas.design_strategy import FeasibilityExpectation, StrategyRisk


def test_1_minimal_valid_candidate():
    candidate = DesignCandidate(
        id="cand-1",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        candidate_version=1,
        name="Minimal Candidate",
    )
    assert candidate.id == "cand-1"
    assert candidate.source_strategy_id == "strat-1"
    assert candidate.candidate_version == 1
    assert candidate.feasibility_expectation == FeasibilityExpectation.NOT_EVALUATED


def test_2_abstract_floor_organization():
    candidate = DesignCandidate(
        id="cand-floor",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="Floor Org Candidate",
        floor_organization={
            "floor_1": ["space_living", "space_kitchen"],
            "floor_2": ["space_bed_master", "space_bed_guest"],
        },
    )
    assert len(candidate.floor_organization) == 2
    assert candidate.floor_organization["floor_1"] == ["space_living", "space_kitchen"]


def test_3_abstract_unit_organization():
    candidate = DesignCandidate(
        id="cand-unit",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="Unit Org Candidate",
        unit_organization={
            "unit_a": ["space_living_a", "space_kitchen_a"],
            "unit_b": ["space_living_b", "space_kitchen_b"],
        },
    )
    assert candidate.unit_organization["unit_a"] == ["space_living_a", "space_kitchen_a"]
    assert candidate.unit_organization["unit_b"] == ["space_living_b", "space_kitchen_b"]


def test_4_circulation_nodes():
    node = AbstractCirculationNode(
        id="circ-1",
        type="shared_staircase",
        connected_space_ids=["space_lobby", "space_corridor"],
        access_type="shared",
    )
    candidate = DesignCandidate(
        id="cand-circ",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="Circulation Candidate",
        circulation_intent=[node],
    )
    assert len(candidate.circulation_intent) == 1
    assert candidate.circulation_intent[0].type == "shared_staircase"
    assert candidate.circulation_intent[0].access_type == "shared"


def test_5_service_stacks():
    stack = AbstractServiceStack(
        id="stack-wet-1",
        service_type="plumbing_stack",
        assigned_space_ids=["bath_1", "bath_2", "kitchen_1"],
    )
    candidate = DesignCandidate(
        id="cand-serv",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="Service Stack Candidate",
        service_organization=[stack],
    )
    assert candidate.service_organization[0].service_type == "plumbing_stack"
    assert len(candidate.service_organization[0].assigned_space_ids) == 3


def test_6_selected_decision_preservation():
    dec = DecisionRecord(
        id="dec-1",
        dimension=DecisionDimension.VERTICAL_CIRCULATION,
        subject="building",
        value="shared",
        status=DecisionStatus.DERIVED,
    )
    candidate = DesignCandidate(
        id="cand-dec",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="Selected Decision Candidate",
        selected_decisions=[dec],
    )
    assert candidate.selected_decisions[0].value == "shared"


def test_7_unresolved_decisions():
    unresolved_dec = DecisionRecord(
        id="dec-unresolved",
        dimension=DecisionDimension.ORIENTATION,
        subject="building",
        alternatives=["north", "south"],
        status=DecisionStatus.UNRESOLVED,
    )
    candidate = DesignCandidate(
        id="cand-unres",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="Unresolved Decision Candidate",
        unresolved_decisions=[unresolved_dec],
    )
    assert candidate.unresolved_decisions[0].status == DecisionStatus.UNRESOLVED
    assert "north" in candidate.unresolved_decisions[0].alternatives


def test_8_risk_assumption_preservation():
    risk = StrategyRisk(
        id="risk-1",
        description="High circulation area percentage",
        severity=AnalysisSeverity.WARNING,
    )
    candidate = DesignCandidate(
        id="cand-risk",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="Risk Assumption Candidate",
        assumptions=["Site access from north road"],
        risks=[risk],
    )
    assert candidate.assumptions == ["Site access from north road"]
    assert candidate.risks[0].id == "risk-1"


def test_9_provenance_metadata():
    candidate = DesignCandidate(
        id="cand-prov",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="Provenance Candidate",
        provenance={"generator": "data-driven-candidate", "fingerprint": "abc-123"},
    )
    assert candidate.provenance["generator"] == "data-driven-candidate"
    assert candidate.provenance["fingerprint"] == "abc-123"


def test_10_versioning_validation():
    with pytest.raises(ValidationError):
        DesignCandidate(
            id="cand-v0",
            source_strategy_id="strat-1",
            source_analysis_id="analysis-1",
            source_problem_id="prob-1",
            source_problem_version=0,  # invalid <= 0
            candidate_version=1,
            name="Invalid Version Candidate",
        )

    with pytest.raises(ValidationError):
        DesignCandidate(
            id="cand-cv0",
            source_strategy_id="strat-1",
            source_analysis_id="analysis-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            candidate_version=0,  # invalid <= 0
            name="Invalid Candidate Version Candidate",
        )


def test_11_confidence_bounds():
    valid_cand = DesignCandidate(
        id="cand-conf",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="Confidence Candidate",
        confidence=0.85,
    )
    assert valid_cand.confidence == 0.85

    with pytest.raises(ValidationError):
        DesignCandidate(
            id="cand-conf-high",
            source_strategy_id="strat-1",
            source_analysis_id="analysis-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            name="High Conf Candidate",
            confidence=1.5,
        )

    with pytest.raises(ValidationError):
        DesignCandidate(
            id="cand-conf-low",
            source_strategy_id="strat-1",
            source_analysis_id="analysis-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            name="Low Conf Candidate",
            confidence=-0.1,
        )


def test_12_duplicate_id_validation():
    n1 = AbstractCirculationNode(id="dup-node", type="stair")
    n2 = AbstractCirculationNode(id="dup-node", type="corridor")

    with pytest.raises(ValidationError) as exc_info:
        DesignCandidate(
            id="cand-dup",
            source_strategy_id="strat-1",
            source_analysis_id="analysis-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            name="Duplicate Collection Candidate",
            circulation_intent=[n1, n2],
        )
    assert "circulation_intent" in str(exc_info.value)


def test_13_json_serialization():
    candidate = DesignCandidate(
        id="cand-json",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="JSON Candidate",
        floor_organization={"floor_1": ["space_a"]},
    )
    dumped_dict = candidate.model_dump()
    assert isinstance(dumped_dict, dict)
    assert dumped_dict["id"] == "cand-json"

    json_str = candidate.model_dump_json()
    assert isinstance(json_str, str)
    assert "cand-json" in json_str


def test_14_json_round_trip():
    candidate = DesignCandidate(
        id="cand-rt",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        candidate_version=2,
        name="Round Trip Candidate",
        floor_organization={"floor_1": ["space_a"], "floor_2": ["space_b"]},
        confidence=0.9,
    )
    json_str = candidate.model_dump_json()
    reconstructed = DesignCandidate.model_validate_json(json_str)

    assert reconstructed.id == candidate.id
    assert reconstructed.candidate_version == candidate.candidate_version
    assert reconstructed.floor_organization == candidate.floor_organization
    assert reconstructed.confidence == candidate.confidence


def test_15_unseen_custom_decision_dimensions():
    custom_dec = DecisionRecord(
        id="dec-custom-1",
        dimension="fire_compartmentation_strategy",
        subject="building",
        value="compartmentalized_floors",
        status=DecisionStatus.DERIVED,
    )
    candidate = DesignCandidate(
        id="cand-unseen",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="Unseen Dimension Candidate",
        selected_decisions=[custom_dec],
    )
    assert candidate.selected_decisions[0].dimension == "fire_compartmentation_strategy"
    assert candidate.selected_decisions[0].value == "compartmentalized_floors"


def test_16_non_geometric_boundary():
    # Attempting to insert geometric coordinates / CAD attributes should fail validation
    with pytest.raises(ValidationError):
        DesignCandidate(
            id="cand-geom-fail",
            source_strategy_id="strat-1",
            source_analysis_id="analysis-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            name="Geom Candidate Fail",
            provenance={"coordinates": [0, 0, 10, 10]},  # Prohibited key 'coordinates'
        )

    with pytest.raises(ValidationError):
        DesignCandidate(
            id="cand-geom-fail-2",
            source_strategy_id="strat-1",
            source_analysis_id="analysis-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            name="Geom Candidate Fail 2",
            floor_organization={"floor_1": [{"polygon": "0 0, 10 0, 10 10"}]},  # Prohibited key 'polygon'
        )


def test_17_benchmark_fixture_abstract_representation():
    # Abstract candidate representation of the 44x42 four-family benchmark test fixture
    candidate = DesignCandidate(
        id="cand-44x42-benchmark",
        source_strategy_id="strat-four-family-shared",
        source_analysis_id="analysis-44x42",
        source_problem_id="prob-44x42-benchmark",
        source_problem_version=1,
        name="44x42 Four-Family Abstract Candidate",
        floor_organization={
            "floor_1": ["unit_fam1_living", "unit_fam1_bed"],
            "floor_2": ["unit_fam2_living", "unit_fam2_bed"],
            "floor_3": ["unit_fam3_living", "unit_fam3_bed"],
            "floor_4": ["unit_fam4_living", "unit_fam4_bed"],
        },
        unit_organization={
            "unit_family_1": ["unit_fam1_living", "unit_fam1_bed"],
            "unit_family_2": ["unit_fam2_living", "unit_fam2_bed"],
            "unit_family_3": ["unit_fam3_living", "unit_fam3_bed"],
            "unit_family_4": ["unit_fam4_living", "unit_fam4_bed"],
        },
        circulation_intent=[
            AbstractCirculationNode(
                id="circ-shared-stair-core",
                type="vertical_stairwell",
                connected_space_ids=["unit_family_1", "unit_family_2", "unit_family_3", "unit_family_4"],
                access_type="shared",
            )
        ],
        service_organization=[
            AbstractServiceStack(
                id="stack-wet-core",
                service_type="plumbing_stack",
                assigned_space_ids=["unit_fam1_bath", "unit_fam2_bath", "unit_fam3_bath", "unit_fam4_bath"],
            )
        ],
        confidence=0.9,
    )
    assert len(candidate.floor_organization) == 4
    assert len(candidate.unit_organization) == 4
    assert candidate.circulation_intent[0].id == "circ-shared-stair-core"


def test_18_single_family_fixture_abstract_representation():
    # Abstract candidate representation of a 2-story single family house
    candidate = DesignCandidate(
        id="cand-single-family",
        source_strategy_id="strat-single-family-compact",
        source_analysis_id="analysis-single-family",
        source_problem_id="prob-single-family",
        source_problem_version=1,
        name="Single Family 2-Story Abstract Candidate",
        floor_organization={
            "floor_ground": ["space_living", "space_dining", "space_kitchen", "space_garage"],
            "floor_upper": ["space_master_bed", "space_bed_2", "space_bed_3", "space_bath"],
        },
        unit_organization={
            "unit_single_residence": [
                "space_living", "space_dining", "space_kitchen",
                "space_master_bed", "space_bed_2", "space_bed_3",
            ]
        },
        circulation_intent=[
            AbstractCirculationNode(
                id="circ-internal-stair",
                type="private_staircase",
                connected_space_ids=["space_living", "space_master_bed"],
                access_type="private",
            )
        ],
        confidence=0.95,
    )
    assert len(candidate.floor_organization) == 2
    assert candidate.unit_organization["unit_single_residence"][0] == "space_living"


def test_19_empty_optional_collections():
    candidate = DesignCandidate(
        id="cand-empty",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="Empty Optional Collections Candidate",
    )
    assert candidate.selected_decisions == []
    assert candidate.floor_organization == {}
    assert candidate.unit_organization == {}
    assert candidate.circulation_intent == []
    assert candidate.service_organization == []
    assert candidate.unresolved_decisions == []
    assert candidate.assumptions == []
    assert candidate.risks == []
    assert candidate.provenance == {}


def test_20_deterministic_model_serialization():
    candidate_a = DesignCandidate(
        id="cand-det",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="Deterministic Serialization Candidate",
        floor_organization={"floor_1": ["space_a", "space_b"]},
        confidence=0.88,
    )

    candidate_b = DesignCandidate(
        id="cand-det",
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="Deterministic Serialization Candidate",
        floor_organization={"floor_1": ["space_a", "space_b"]},
        confidence=0.88,
    )

    assert candidate_a.model_dump_json() == candidate_b.model_dump_json()
