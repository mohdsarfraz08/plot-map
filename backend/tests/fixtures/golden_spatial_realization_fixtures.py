"""
Golden Spatial Realization Fixtures for Stage 3B.4D-4.

Provides deterministic, non-geometric problem & candidate scenarios to verify
end-to-end 2D spatial layout realization:
A. 44x42 benchmark (4-family, multi-floor, shared circulation)
B. Single-family (30x40 ft, ground-floor-only)
C. Shared circulation scenario
D. Independent circulation scenario
E. Hybrid circulation scenario
F. Ground-floor-only floor allocation
G. Distributed floor allocation
H. Centralized service core stack
I. Custom/unseen decision dimensions
"""

from app.schemas.architectural_analysis import DecisionRecord, DecisionStatus
from app.schemas.design_candidate import DesignCandidate
from app.schemas.design_problem import DesignProblem
from app.services.analysis.candidate_organizer import organize_candidate
from app.services.analysis.catalog_loader import get_catalog_organization_rules
from tests.fixtures.golden_organization_fixtures import (
    get_benchmark_44x42_candidate,
    get_benchmark_44x42_problem,
    get_single_family_candidate,
    get_single_family_problem,
)


def get_golden_44x42_benchmark_fixture() -> tuple[DesignProblem, DesignCandidate]:
    """Scenario A: Benchmark 44x42 ft, 4-family residential scenario."""
    prob = get_benchmark_44x42_problem()
    raw_cand = get_benchmark_44x42_candidate(prob)
    rules = get_catalog_organization_rules()
    cand = organize_candidate(raw_cand, rules, problem=prob)
    return prob, cand


def get_golden_single_family_fixture() -> tuple[DesignProblem, DesignCandidate]:
    """Scenario B: Single-family 30x40 ft ground floor scenario."""
    prob = get_single_family_problem()
    raw_cand = get_single_family_candidate(prob)
    rules = get_catalog_organization_rules()
    cand = organize_candidate(raw_cand, rules, problem=prob)
    return prob, cand


def get_golden_shared_circulation_fixture() -> tuple[DesignProblem, DesignCandidate]:
    """Scenario C: Multi-unit layout with shared vertical stair core."""
    prob = get_benchmark_44x42_problem()
    raw_cand = get_benchmark_44x42_candidate(prob)
    rules = get_catalog_organization_rules()
    cand = organize_candidate(raw_cand, rules, problem=prob)
    return prob, cand


def get_golden_independent_circulation_fixture() -> tuple[DesignProblem, DesignCandidate]:
    """Scenario D: Multi-unit layout with independent circulation nodes per unit."""
    prob = get_benchmark_44x42_problem()
    raw_cand = get_benchmark_44x42_candidate(prob)
    for dec in raw_cand.selected_decisions:
        if str(dec.dimension) == "vertical_circulation":
            dec.value = "independent"

    rules = get_catalog_organization_rules()
    cand = organize_candidate(raw_cand, rules, problem=prob)
    return prob, cand


def get_golden_hybrid_circulation_fixture() -> tuple[DesignProblem, DesignCandidate]:
    """Scenario E: Hybrid circulation scenario combining shared stairwell and unit access."""
    prob = get_benchmark_44x42_problem()
    raw_cand = get_benchmark_44x42_candidate(prob)
    for dec in raw_cand.selected_decisions:
        if str(dec.dimension) == "vertical_circulation":
            dec.value = "hybrid"

    rules = get_catalog_organization_rules()
    cand = organize_candidate(raw_cand, rules, problem=prob)
    return prob, cand


def get_golden_ground_floor_fixture() -> tuple[DesignProblem, DesignCandidate]:
    """Scenario F: Single level ground floor allocation."""
    prob = get_single_family_problem()
    raw_cand = get_single_family_candidate(prob)
    rules = get_catalog_organization_rules()
    cand = organize_candidate(raw_cand, rules, problem=prob)
    return prob, cand


def get_golden_distributed_floor_fixture() -> tuple[DesignProblem, DesignCandidate]:
    """Scenario G: Distributed floor allocation across multi-floor building."""
    prob = get_benchmark_44x42_problem()
    raw_cand = get_benchmark_44x42_candidate(prob)
    rules = get_catalog_organization_rules()
    cand = organize_candidate(raw_cand, rules, problem=prob)
    return prob, cand


def get_golden_centralized_service_fixture() -> tuple[DesignProblem, DesignCandidate]:
    """Scenario H: Centralized wet service core stack."""
    prob = get_benchmark_44x42_problem()
    raw_cand = get_benchmark_44x42_candidate(prob)
    rules = get_catalog_organization_rules()
    cand = organize_candidate(raw_cand, rules, problem=prob)
    return prob, cand


def get_golden_custom_dimensions_fixture() -> tuple[DesignProblem, DesignCandidate]:
    """Scenario I: Custom/unseen decision dimensions (solar_shading, facade_transparency, ventilation)."""
    prob = get_single_family_problem()
    raw_cand = get_single_family_candidate(prob)

    custom_decisions = [
        DecisionRecord(
            id="dec-solar-shading",
            dimension="solar_shading_strategy",
            subject="building",
            value="external_louver",
            status=DecisionStatus.FIXED,
            rationale="Custom solar shading requirement",
        ),
        DecisionRecord(
            id="dec-facade-transparency",
            dimension="facade_transparency",
            subject="building",
            value="high_glazed",
            status=DecisionStatus.FIXED,
            rationale="Custom facade transparency requirement",
        ),
        DecisionRecord(
            id="dec-ventilation-custom",
            dimension="natural_ventilation_strategy",
            subject="building",
            value="cross_breeze",
            status=DecisionStatus.FIXED,
            rationale="Custom natural ventilation requirement",
        ),
    ]
    raw_cand.selected_decisions.extend(custom_decisions)

    rules = get_catalog_organization_rules()
    cand = organize_candidate(raw_cand, rules, problem=prob)
    return prob, cand
