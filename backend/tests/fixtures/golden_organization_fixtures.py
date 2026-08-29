"""
Golden Fixtures for Stage 3B.4C-3 Candidate Organization Migration Verification.

Provides reusable, non-geometric benchmark & scenario fixtures to verify
declarative equivalence between strategy/candidate inputs and abstract CandidateOrganizer outputs.
"""

from app.schemas.architectural_analysis import (
    DecisionRecord,
    DecisionStatus,
    OrganizationAction,
    OrganizationRule,
)
from app.schemas.design_candidate import (
    AbstractCirculationNode,
    AbstractServiceStack,
    DesignCandidate,
)
from app.schemas.design_problem import (
    DesignProblem,
    SiteDefinition,
    SpaceRequirement,
)
from app.schemas.design_strategy import (
    DesignStrategy,
    FeasibilityExpectation,
    StrategyRisk,
    TradeOff,
)
from app.schemas.intent import RoomCategory, RoomIntent


def get_benchmark_44x42_problem() -> DesignProblem:
    """Fixture A: Benchmark 44x42 ft, 4-family residential scenario."""
    spaces = []
    families = ["family_a", "family_b", "family_c", "family_d"]
    for fam in families:
        spaces.extend(
            [
                SpaceRequirement(
                    id=f"{fam}_living",
                    room=RoomIntent(room_type=RoomCategory.LIVING),
                    owner_id=fam,
                ),
                SpaceRequirement(
                    id=f"{fam}_kitchen",
                    room=RoomIntent(room_type=RoomCategory.KITCHEN),
                    owner_id=fam,
                ),
                SpaceRequirement(
                    id=f"{fam}_bathroom",
                    room=RoomIntent(room_type=RoomCategory.BATHROOM),
                    owner_id=fam,
                ),
                SpaceRequirement(
                    id=f"{fam}_bedroom",
                    room=RoomIntent(room_type=RoomCategory.BEDROOM),
                    owner_id=fam,
                ),
            ]
        )

    return DesignProblem(
        id="prob-44x42-benchmark",
        version=1,
        site=SiteDefinition(plot_width=44.0, plot_depth=42.0, floors=4),
        spaces=spaces,
    )


def get_benchmark_44x42_candidate(problem: DesignProblem) -> DesignCandidate:
    """Fixture A: Benchmark 44x42 ft candidate with standard decision assignments."""
    selected_decisions = [
        DecisionRecord(
            id="dec-vert-circ",
            dimension="vertical_circulation",
            subject="building",
            value="shared",
            status=DecisionStatus.DERIVED,
        ),
        DecisionRecord(
            id="dec-unit-org",
            dimension="unit_organization",
            subject="building",
            value="grouped",
            status=DecisionStatus.DERIVED,
        ),
        DecisionRecord(
            id="dec-service-core",
            dimension="service_core_strategy",
            subject="building",
            value="centralized",
            status=DecisionStatus.DERIVED,
        ),
        DecisionRecord(
            id="dec-floor-alloc",
            dimension="floor_allocation",
            subject="building",
            value="distributed",
            status=DecisionStatus.DERIVED,
        ),
    ]

    return DesignCandidate(
        id="candidate-44x42-benchmark",
        source_strategy_id="strat-44x42-benchmark",
        source_analysis_id="analysis-44x42",
        source_problem_id=problem.id,
        source_problem_version=problem.version,
        candidate_version=1,
        name="Candidate 44x42 Benchmark",
        selected_decisions=selected_decisions,
        floor_organization={},
        unit_organization={},
        circulation_intent=[],
        service_organization=[],
        unresolved_decisions=[],
        assumptions=["Standard structural grid", "Central core access"],
        risks=[
            StrategyRisk(
                id="risk-circ-1",
                description="Shared stair core creates high foot traffic near ground floor",
                severity="warning",
            )
        ],
        feasibility_expectation=FeasibilityExpectation.EXPECTED_FEASIBLE,
        confidence=0.9,
        provenance={"generator": "golden-fixture-builder"},
    )


def get_single_family_problem() -> DesignProblem:
    """Fixture B: Single-family 30x40 ft scenario."""
    spaces = [
        SpaceRequirement(
            id="sf_living",
            room=RoomIntent(room_type=RoomCategory.LIVING),
            owner_id="family_1",
        ),
        SpaceRequirement(
            id="sf_kitchen",
            room=RoomIntent(room_type=RoomCategory.KITCHEN),
            owner_id="family_1",
        ),
        SpaceRequirement(
            id="sf_bathroom",
            room=RoomIntent(room_type=RoomCategory.BATHROOM),
            owner_id="family_1",
        ),
        SpaceRequirement(
            id="sf_bedroom_1",
            room=RoomIntent(room_type=RoomCategory.BEDROOM),
            owner_id="family_1",
        ),
        SpaceRequirement(
            id="sf_bedroom_2",
            room=RoomIntent(room_type=RoomCategory.BEDROOM),
            owner_id="family_1",
        ),
    ]

    return DesignProblem(
        id="prob-single-family",
        version=1,
        site=SiteDefinition(plot_width=30.0, plot_depth=40.0, floors=1),
        spaces=spaces,
    )


def get_single_family_candidate(problem: DesignProblem) -> DesignCandidate:
    """Fixture B: Single-family candidate assigned to ground floor."""
    selected_decisions = [
        DecisionRecord(
            id="dec-sf-unit",
            dimension="unit_organization",
            subject="building",
            value="grouped",
            status=DecisionStatus.DERIVED,
        ),
        DecisionRecord(
            id="dec-sf-floor",
            dimension="floor_allocation",
            subject="building",
            value="ground_floor_only",
            status=DecisionStatus.DERIVED,
        ),
        DecisionRecord(
            id="dec-sf-service",
            dimension="service_core_strategy",
            subject="building",
            value="centralized",
            status=DecisionStatus.DERIVED,
        ),
    ]

    return DesignCandidate(
        id="candidate-single-family",
        source_strategy_id="strat-single-family",
        source_analysis_id="analysis-single-family",
        source_problem_id=problem.id,
        source_problem_version=problem.version,
        candidate_version=1,
        name="Candidate Single Family",
        selected_decisions=selected_decisions,
        floor_organization={},
        unit_organization={},
        circulation_intent=[],
        service_organization=[],
        unresolved_decisions=[],
        assumptions=["Single level living"],
        risks=[],
        feasibility_expectation=FeasibilityExpectation.EXPECTED_FEASIBLE,
        confidence=0.95,
        provenance={"generator": "golden-fixture-builder"},
    )
