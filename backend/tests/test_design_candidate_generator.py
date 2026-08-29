import pytest

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
from app.schemas.design_strategy import (
    DesignStrategy,
    FeasibilityExpectation,
    StrategyRisk,
)
from app.services.analysis.candidate_generator import (
    generate_candidate_from_strategy,
    generate_candidates,
)
from app.services.analysis.architectural_analyzer import analyze_design_problem
from app.services.analysis.strategy_generator import generate_strategies
from app.schemas.design_problem import (
    DesignProblem,
    SiteDefinition,
    SpaceRequirement,
    UserGroup,
)
from app.schemas.intent import RoomCategory, RoomIntent


def _sample_strategy(strategy_id: str = "strat-1", name: str = "Sample Strategy") -> DesignStrategy:
    dec = DecisionRecord(
        id="dec-1",
        dimension=DecisionDimension.VERTICAL_CIRCULATION,
        subject="building",
        value="shared",
        status=DecisionStatus.DERIVED,
    )
    risk = StrategyRisk(
        id="risk-1",
        description="Sample risk",
        severity=AnalysisSeverity.WARNING,
    )
    return DesignStrategy(
        id=strategy_id,
        source_problem_id="prob-100",
        source_problem_version=1,
        source_analysis_id="analysis-100",
        name=name,
        approach="Sample strategic approach",
        decisions=[dec],
        flexible_decisions=[DecisionDimension.ORIENTATION],
        assumptions=["Site access from primary road"],
        risks=[risk],
        feasibility_expectation=FeasibilityExpectation.EXPECTED_FEASIBLE,
        rationale="Sample rationale string",
        confidence=0.88,
        provenance={"fingerprint": f"fingerprint-{strategy_id}"},
    )


def test_1_one_strategy_to_one_candidate():
    strategy = _sample_strategy("strat-1")
    candidates = generate_candidates([strategy])
    assert len(candidates) == 1
    candidate = candidates[0]
    assert isinstance(candidate, DesignCandidate)
    assert candidate.source_strategy_id == "strat-1"
    assert candidate.source_problem_id == "prob-100"


def test_2_multiple_strategies_to_deterministic_candidates():
    s1 = _sample_strategy("strat-1", "Strategy 1")
    s2 = _sample_strategy("strat-2", "Strategy 2")
    candidates = generate_candidates([s1, s2])
    assert len(candidates) == 2
    assert candidates[0].id == "candidate-1"
    assert candidates[1].id == "candidate-2"
    assert candidates[0].source_strategy_id == "strat-1"
    assert candidates[1].source_strategy_id == "strat-2"


def test_3_selected_decision_preservation():
    strategy = _sample_strategy()
    candidate = generate_candidate_from_strategy(strategy)
    assert len(candidate.selected_decisions) == 1
    assert candidate.selected_decisions[0].dimension == DecisionDimension.VERTICAL_CIRCULATION
    assert candidate.selected_decisions[0].value == "shared"


def test_4_unresolved_decision_preservation():
    strategy = _sample_strategy()
    candidate = generate_candidate_from_strategy(strategy)
    assert len(candidate.unresolved_decisions) == 1
    assert candidate.unresolved_decisions[0].dimension == DecisionDimension.ORIENTATION
    assert candidate.unresolved_decisions[0].status == DecisionStatus.UNRESOLVED


def test_5_assumption_preservation():
    strategy = _sample_strategy()
    candidate = generate_candidate_from_strategy(strategy)
    assert candidate.assumptions == ["Site access from primary road"]


def test_6_risk_preservation():
    strategy = _sample_strategy()
    candidate = generate_candidate_from_strategy(strategy)
    assert len(candidate.risks) == 1
    assert candidate.risks[0].id == "risk-1"
    assert candidate.risks[0].description == "Sample risk"


def test_7_feasibility_preservation():
    strategy = _sample_strategy()
    candidate = generate_candidate_from_strategy(strategy)
    assert candidate.feasibility_expectation == FeasibilityExpectation.EXPECTED_FEASIBLE
    assert candidate.confidence == 0.88


def test_8_source_traceability():
    strategy = _sample_strategy()
    candidate = generate_candidate_from_strategy(strategy)
    assert candidate.source_strategy_id == "strat-1"
    assert candidate.source_analysis_id == "analysis-100"
    assert candidate.source_problem_id == "prob-100"
    assert candidate.source_problem_version == 1


def test_9_provenance_metadata():
    strategy = _sample_strategy()
    candidate = generate_candidate_from_strategy(strategy)
    assert candidate.provenance["generator"] == "deterministic-data-driven-candidate"
    assert candidate.provenance["source_strategy_id"] == "strat-1"
    assert candidate.provenance["fingerprint"] == "fingerprint-strat-1"


def test_10_deterministic_candidate_ids():
    s1 = _sample_strategy("strat-10")
    c1 = generate_candidate_from_strategy(s1)
    assert c1.id == "candidate-strat-10"

    c2 = generate_candidate_from_strategy(s1, candidate_id="custom-cand-id")
    assert c2.id == "custom-cand-id"


def test_11_candidate_limit():
    strategies = [_sample_strategy(f"strat-{i}") for i in range(15)]
    candidates = generate_candidates(strategies, max_candidates=5)
    assert len(candidates) == 5
    assert candidates[-1].id == "candidate-5"


def test_12_unknown_custom_decision_dimensions():
    custom_dec = DecisionRecord(
        id="dec-custom",
        dimension="solar_shading_strategy",
        subject="facade",
        value="louvers",
        status=DecisionStatus.DERIVED,
    )
    strategy = DesignStrategy(
        id="strat-custom",
        source_problem_id="prob-1",
        source_problem_version=1,
        source_analysis_id="analysis-1",
        name="Custom Dim Strategy",
        approach="Custom approach",
        decisions=[custom_dec],
        flexible_decisions=["acoustic_isolation_tier"],
        rationale="Custom rationale",
    )
    candidate = generate_candidate_from_strategy(strategy)
    assert candidate.selected_decisions[0].dimension == "solar_shading_strategy"
    assert candidate.selected_decisions[0].value == "louvers"
    assert candidate.unresolved_decisions[0].dimension == "acoustic_isolation_tier"


def test_13_abstract_floor_organization_explicit():
    # If explicit structured floor organization is in decision value, preserve it. If unprovided, leave empty.
    dec_with_floor = DecisionRecord(
        id="dec-floor-struct",
        dimension="floor_allocation",
        subject="building",
        value={"floor_organization": {"floor_1": ["room_a"], "floor_2": ["room_b"]}},
        status=DecisionStatus.DERIVED,
    )
    strategy_explicit = DesignStrategy(
        id="strat-explicit-floor",
        source_problem_id="prob-1",
        source_problem_version=1,
        source_analysis_id="analysis-1",
        name="Explicit Floor Strategy",
        approach="Approach",
        decisions=[dec_with_floor],
        rationale="Rationale",
    )
    candidate_explicit = generate_candidate_from_strategy(strategy_explicit)
    assert candidate_explicit.floor_organization == {"floor_1": ["room_a"], "floor_2": ["room_b"]}

    # Non-explicit strategy should leave floor_organization empty (STRICT NON-INFERENCE)
    strategy_string_only = _sample_strategy("strat-str")
    candidate_str = generate_candidate_from_strategy(strategy_string_only)
    assert candidate_str.floor_organization == {}


def test_14_abstract_unit_organization_explicit():
    dec_with_unit = DecisionRecord(
        id="dec-unit-struct",
        dimension="unit_organization",
        subject="building",
        value={"unit_organization": {"unit_1": ["room_a", "room_b"]}},
        status=DecisionStatus.DERIVED,
    )
    strategy_explicit = DesignStrategy(
        id="strat-explicit-unit",
        source_problem_id="prob-1",
        source_problem_version=1,
        source_analysis_id="analysis-1",
        name="Explicit Unit Strategy",
        approach="Approach",
        decisions=[dec_with_unit],
        rationale="Rationale",
    )
    candidate = generate_candidate_from_strategy(strategy_explicit)
    assert candidate.unit_organization == {"unit_1": ["room_a", "room_b"]}


def test_15_abstract_circulation_relationships_explicit():
    node = AbstractCirculationNode(id="circ-node-1", type="staircase", connected_space_ids=["room_a", "room_b"])
    dec_circ = DecisionRecord(
        id="dec-circ-struct",
        dimension="vertical_circulation",
        subject="building",
        value={"circulation_intent": [node.model_dump()]},
        status=DecisionStatus.DERIVED,
    )
    strategy = DesignStrategy(
        id="strat-explicit-circ",
        source_problem_id="prob-1",
        source_problem_version=1,
        source_analysis_id="analysis-1",
        name="Explicit Circ Strategy",
        approach="Approach",
        decisions=[dec_circ],
        rationale="Rationale",
    )
    candidate = generate_candidate_from_strategy(strategy)
    assert len(candidate.circulation_intent) == 1
    assert candidate.circulation_intent[0].id == "circ-node-1"


def test_16_abstract_service_relationships_explicit():
    stack = AbstractServiceStack(id="serv-stack-1", service_type="plumbing", assigned_space_ids=["bath_1", "kitchen_1"])
    dec_serv = DecisionRecord(
        id="dec-serv-struct",
        dimension="service_core_strategy",
        subject="building",
        value={"service_organization": [stack.model_dump()]},
        status=DecisionStatus.DERIVED,
    )
    strategy = DesignStrategy(
        id="strat-explicit-serv",
        source_problem_id="prob-1",
        source_problem_version=1,
        source_analysis_id="analysis-1",
        name="Explicit Service Strategy",
        approach="Approach",
        decisions=[dec_serv],
        rationale="Rationale",
    )
    candidate = generate_candidate_from_strategy(strategy)
    assert len(candidate.service_organization) == 1
    assert candidate.service_organization[0].id == "serv-stack-1"


def test_17_no_geometry_generated():
    strategy = _sample_strategy()
    candidate = generate_candidate_from_strategy(strategy)
    cand_dict = candidate.model_dump()
    prohibited = {"coordinates", "polygon", "rectangle", "bounding_box", "x", "y", "z", "wall", "door", "window", "mesh", "cad"}
    for key in cand_dict.keys():
        assert key.lower() not in prohibited


def test_18_no_solver_invocation():
    # Verify module imports contain zero solver or geometry imports
    import app.services.analysis.candidate_generator as cg_mod
    mod_dict = dir(cg_mod)
    assert "solve_layout" not in mod_dict
    assert "PuLP" not in mod_dict
    assert "CBC" not in mod_dict
    assert "compile_blueprint" not in mod_dict


def test_19_benchmark_fixture():
    # End-to-end test using 44x42 four-family benchmark fixture
    problem = DesignProblem(
        id="prob-44x42-benchmark",
        version=1,
        site=SiteDefinition(plot_width=44.0, plot_depth=42.0, floors=4),
        user_groups=[
            UserGroup(id="fam1", name="Family 1"),
            UserGroup(id="fam2", name="Family 2"),
            UserGroup(id="fam3", name="Family 3"),
            UserGroup(id="fam4", name="Family 4"),
        ],
        spaces=[
            SpaceRequirement(id="liv_1", room=RoomIntent(room_type=RoomCategory.LIVING, min_area_sqft=150), owner_id="fam1"),
            SpaceRequirement(id="bed_1", room=RoomIntent(room_type=RoomCategory.BEDROOM, min_area_sqft=120), owner_id="fam1"),
        ],
    )
    analysis = analyze_design_problem(problem)
    strategies = generate_strategies(analysis, problem)
    assert len(strategies) >= 1

    candidates = generate_candidates(strategies)
    assert len(candidates) == len(strategies)
    for c in candidates:
        assert isinstance(c, DesignCandidate)
        assert c.source_problem_id == "prob-44x42-benchmark"
        assert c.source_problem_version == 1


def test_20_single_family_fixture():
    # End-to-end test using single family fixture
    problem = DesignProblem(
        id="prob-single-family-house",
        version=1,
        site=SiteDefinition(plot_width=30.0, plot_depth=40.0, floors=2),
        user_groups=[UserGroup(id="fam_single", name="Single Family")],
        spaces=[
            SpaceRequirement(id="liv", room=RoomIntent(room_type=RoomCategory.LIVING, min_area_sqft=200), owner_id="fam_single"),
            SpaceRequirement(id="kit", room=RoomIntent(room_type=RoomCategory.KITCHEN, min_area_sqft=80), owner_id="fam_single"),
            SpaceRequirement(id="bed_master", room=RoomIntent(room_type=RoomCategory.BEDROOM, min_area_sqft=150), owner_id="fam_single"),
        ],
    )
    analysis = analyze_design_problem(problem)
    strategies = generate_strategies(analysis, problem)
    assert len(strategies) >= 1

    candidates = generate_candidates(strategies)
    assert len(candidates) == len(strategies)
    assert candidates[0].source_problem_id == "prob-single-family-house"


def test_21_empty_optional_strategy_collections():
    strategy_minimal = DesignStrategy(
        id="strat-min",
        source_problem_id="prob-min",
        source_problem_version=1,
        source_analysis_id="analysis-min",
        name="Minimal Strategy",
        approach="Minimal approach",
        rationale="Minimal rationale",
    )
    candidate = generate_candidate_from_strategy(strategy_minimal)
    assert candidate.selected_decisions == []
    assert candidate.unresolved_decisions == []
    assert candidate.assumptions == []
    assert candidate.risks == []
    assert candidate.floor_organization == {}
    assert candidate.unit_organization == {}
    assert candidate.circulation_intent == []
    assert candidate.service_organization == []


def test_22_repeated_execution_produces_identical_output():
    strategy = _sample_strategy("strat-repeat")
    c1 = generate_candidate_from_strategy(strategy)
    c2 = generate_candidate_from_strategy(strategy)
    assert c1.model_dump_json() == c2.model_dump_json()

    strategies = [strategy]
    list1 = generate_candidates(strategies)
    list2 = generate_candidates(strategies)
    assert list1[0].model_dump_json() == list2[0].model_dump_json()
