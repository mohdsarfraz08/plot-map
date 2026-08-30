from collections.abc import Iterable
from typing import Any

from app.schemas.architectural_analysis import (
    AnalysisSeverity,
    ArchitecturalAnalysis,
    ConflictRecord,
    ConflictStatus,
    DecisionDimension,
    DecisionRecord,
    DecisionStatus,
    DependencyRecord,
    DimensionRelationship,
    FeasibilityConcern,
    IncompatibilityRule,
    UncertaintyMateriality,
    UncertaintyRecord,
)
from app.schemas.design_problem import (
    Constraint,
    DesignProblem,
    Preference,
    Requirement,
    RequirementKind,
    RequirementStrength,
)
from app.services.analysis.catalog_loader import (
    get_catalog_alternatives,
    get_catalog_incompatibilities,
    get_catalog_relationships,
    load_decision_catalog,
)


def _dim_to_str(dim: Any) -> str:
    if hasattr(dim, "value"):
        return str(dim.value)
    return str(dim)


_FLEXIBLE_DIMENSIONS = (
    DecisionDimension.FLOOR_ALLOCATION,
    DecisionDimension.UNIT_ORGANIZATION,
    DecisionDimension.CIRCULATION,
    DecisionDimension.VERTICAL_CIRCULATION,
    DecisionDimension.ENTRANCE_STRATEGY,
    DecisionDimension.SHARED_PRIVATE_STRATEGY,
    DecisionDimension.SERVICE_CORE_STRATEGY,
    DecisionDimension.ORIENTATION,
    DecisionDimension.ZONING,
)


def _unique_in_order(values: Iterable[Any]) -> list[Any]:
    return list(dict.fromkeys(values))


def _requirement_dimensions(requirement: Requirement) -> list[DecisionDimension]:
    # Check if requirement subject explicitly identifies a DecisionDimension
    subj_str = requirement.subject.lower() if isinstance(requirement.subject, str) else ""
    for dim in DecisionDimension:
        if dim.value == subj_str:
            return [dim]

    mapping = {
        RequirementKind.SITE: DecisionDimension.SITE_RESPONSE,
        RequirementKind.SPACE: DecisionDimension.PROGRAM_DEFINITION,
        RequirementKind.QUANTITY: DecisionDimension.SPACE_QUANTITY,
        RequirementKind.ASSIGNMENT: DecisionDimension.FLOOR_ALLOCATION,
        RequirementKind.CIRCULATION: DecisionDimension.VERTICAL_CIRCULATION if "vert" in subj_str or "stair" in subj_str else DecisionDimension.CIRCULATION,
        RequirementKind.ACCESSIBILITY: DecisionDimension.ENTRANCE_STRATEGY if "entrance" in subj_str else DecisionDimension.ACCESSIBILITY,
        RequirementKind.PRIVACY: DecisionDimension.PRIVACY,
        RequirementKind.RELATIONSHIP: DecisionDimension.UNIT_ORGANIZATION if "unit" in subj_str else DecisionDimension.SHARED_PRIVATE_STRATEGY,
        RequirementKind.ENVIRONMENTAL: DecisionDimension.ENVIRONMENTAL_RESPONSE,
        RequirementKind.REGULATORY: DecisionDimension.REGULATORY_STRATEGY,
        RequirementKind.COST: DecisionDimension.COST_STRATEGY,
        RequirementKind.AESTHETIC: DecisionDimension.ZONING,
        RequirementKind.OPERATIONAL: DecisionDimension.CIRCULATION,
    }
    dimension = mapping.get(requirement.kind)
    return [dimension] if dimension is not None else []


def _explicit_decisions(problem: DesignProblem) -> list[DecisionRecord]:
    decisions = [
        DecisionRecord(
            id="site-dimensions",
            dimension=DecisionDimension.SITE_RESPONSE,
            subject="site",
            value={
                "plot_width": problem.site.plot_width,
                "plot_depth": problem.site.plot_depth,
            },
            source_ids=["site.plot_width", "site.plot_depth"],
            status=DecisionStatus.FIXED,
            rationale="Plot dimensions are explicitly present in the DesignProblem.",
        ),
        DecisionRecord(
            id="floor-count",
            dimension=DecisionDimension.SITE_RESPONSE,
            subject="building",
            value=problem.site.floors,
            source_ids=["site.floors"],
            status=DecisionStatus.FIXED,
            rationale="The available floor count is explicitly present in the DesignProblem.",
        ),
    ]

    for space in problem.spaces:
        decisions.append(
            DecisionRecord(
                id=f"space-{space.id}",
                dimension=DecisionDimension.PROGRAM_DEFINITION,
                subject=space.id,
                value={
                    "room_type": space.room.room_type.value,
                    "min_area_sqft": space.room.min_area_sqft,
                    "quantity": space.quantity,
                    "owner_id": space.owner_id,
                    "optional": space.optional,
                },
                source_ids=[space.id],
                status=DecisionStatus.FIXED,
                rationale="The space requirement is explicitly present in the DesignProblem.",
            )
        )

    for requirement in problem.requirements:
        if requirement.strength is RequirementStrength.HARD:
            for dimension in _requirement_dimensions(requirement):
                decisions.append(
                    DecisionRecord(
                        id=f"fixed-{requirement.id}-{dimension.value}",
                        dimension=dimension,
                        subject=requirement.subject,
                        value=requirement.value,
                        source_ids=[requirement.id],
                        status=DecisionStatus.FIXED,
                        rationale="The decision is supported by an explicit hard requirement.",
                    )
                )
    return decisions


def _flexible_decisions(
    problem: DesignProblem,
    fixed: list[DecisionRecord],
    catalog: dict[str, Any] | None = None,
) -> list[DecisionRecord]:
    fixed_dimensions = {decision.dimension for decision in fixed}
    flexible: list[DecisionRecord] = []
    for dimension in _FLEXIBLE_DIMENSIONS:
        if dimension not in fixed_dimensions:
            catalog_alts = get_catalog_alternatives(dimension, catalog=catalog)
            flexible.append(
                DecisionRecord(
                    id=f"flexible-{_dim_to_str(dimension)}",
                    dimension=dimension,
                    subject="building",
                    alternatives=catalog_alts,
                    status=DecisionStatus.FLEXIBLE,
                    rationale="No final value for this architectural dimension is specified.",
                )
            )
    return flexible


def _conflicts(problem: DesignProblem) -> list[ConflictRecord]:
    requirements = {requirement.id: requirement for requirement in problem.requirements}
    records: list[ConflictRecord] = []
    seen: set[frozenset[str]] = set()
    for requirement in problem.requirements:
        for target_id in requirement.conflicts_with:
            target = requirements.get(target_id)
            if target is None:
                continue
            pair = frozenset((requirement.id, target_id))
            if pair in seen:
                continue
            seen.add(pair)
            both_soft = (
                requirement.strength is RequirementStrength.SOFT
                and target.strength is RequirementStrength.SOFT
            )
            status = (
                ConflictStatus.RESOLVABLE_BY_PRIORITY
                if both_soft and requirement.priority != target.priority
                else ConflictStatus.REQUIRES_CLARIFICATION
            )
            records.append(
                ConflictRecord(
                    id=f"conflict-{min(pair)}-{max(pair)}",
                    source_ids=sorted(pair),
                    type="declared_requirement_conflict",
                    severity=AnalysisSeverity.WARNING if both_soft else AnalysisSeverity.BLOCKING,
                    status=status,
                    explanation="The DesignProblem explicitly marks these requirements as conflicting.",
                    affected_dimensions=_unique_in_order(
                        _requirement_dimensions(requirement) + _requirement_dimensions(target)
                    ),
                    resolution_options=["honor the higher-priority requirement"] if both_soft else [],
                    clarification_question=(
                        "Which conflicting requirement should be retained?" if not both_soft else None
                    ),
                )
            )
    return records


def _uncertainties(problem: DesignProblem, flexible: list[DecisionRecord]) -> list[UncertaintyRecord]:
    uncertainties: list[UncertaintyRecord] = []
    flexible_dimensions = {decision.dimension for decision in flexible}

    if DecisionDimension.ORIENTATION in flexible_dimensions:
        uncertainties.append(
            UncertaintyRecord(
                id="uncertainty-orientation",
                topic="site orientation",
                description="Site orientation is not specified in the DesignProblem.",
                materiality=UncertaintyMateriality.MATERIAL,
                affected_dimensions=[DecisionDimension.ORIENTATION, DecisionDimension.ZONING],
                required_for_strategy=True,
                clarification_question="What is the site orientation or road-facing direction?",
            )
        )

    if problem.spaces and DecisionDimension.FLOOR_ALLOCATION in flexible_dimensions:
        uncertainties.append(
            UncertaintyRecord(
                id="uncertainty-floor-allocation",
                topic="space-to-floor allocation",
                description="Spaces are specified without final floor assignments.",
                materiality=UncertaintyMateriality.MATERIAL,
                affected_dimensions=[DecisionDimension.FLOOR_ALLOCATION],
                required_for_strategy=True,
                clarification_question="Are any spaces required to be on specific floors?",
            )
        )

    if len(problem.user_groups) > 1:
        has_group_relationship = any(
            relation.target_id in {group.id for group in problem.user_groups}
            for space in problem.spaces
            for relation in space.relationships
        )
        if not has_group_relationship:
            uncertainties.append(
                UncertaintyRecord(
                    id="uncertainty-group-circulation",
                    topic="user-group circulation relationship",
                    description="Multiple user groups exist without a declared shared or independent circulation relationship.",
                    materiality=UncertaintyMateriality.MATERIAL,
                    affected_dimensions=[
                        DecisionDimension.CIRCULATION,
                        DecisionDimension.ENTRANCE_STRATEGY,
                        DecisionDimension.SHARED_PRIVATE_STRATEGY,
                    ],
                    required_for_strategy=True,
                    clarification_question="Should user groups share or have independent entrances and circulation?",
                )
            )
    return uncertainties


def _dependencies(dimensions: set[DecisionDimension]) -> list[DependencyRecord]:
    dependencies: list[DependencyRecord] = []
    if DecisionDimension.VERTICAL_CIRCULATION in dimensions:
        dependencies.append(
            DependencyRecord(
                id="dependency-vertical-circulation",
                source_dimension=DecisionDimension.VERTICAL_CIRCULATION,
                affected_dimensions=[
                    DecisionDimension.CIRCULATION,
                    DecisionDimension.FLOOR_ALLOCATION,
                    DecisionDimension.SERVICE_CORE_STRATEGY,
                ],
                relationship="affects",
                explanation="Vertical circulation influences access between levels and service-core organization.",
            )
        )
    if DecisionDimension.UNIT_ORGANIZATION in dimensions:
        dependencies.append(
            DependencyRecord(
                id="dependency-unit-organization",
                source_dimension=DecisionDimension.UNIT_ORGANIZATION,
                affected_dimensions=[
                    DecisionDimension.ENTRANCE_STRATEGY,
                    DecisionDimension.SHARED_PRIVATE_STRATEGY,
                    DecisionDimension.CIRCULATION,
                ],
                relationship="affects",
                explanation="Unit organization influences entrances, privacy boundaries, and circulation.",
            )
        )
    return dependencies


def _feasibility_concerns(problem: DesignProblem) -> list[FeasibilityConcern]:
    setbacks = problem.site.setbacks
    buildable_width = problem.site.plot_width - setbacks.get("left", 0.0) - setbacks.get("right", 0.0)
    buildable_depth = problem.site.plot_depth - setbacks.get("bottom", 0.0) - setbacks.get("top", 0.0)
    required_area = sum(
        (space.room.min_area_sqft or 0) * space.quantity
        for space in problem.spaces
        if not space.optional
    )
    available_area = max(0.0, buildable_width) * max(0.0, buildable_depth)
    if required_area > available_area:
        return [
            FeasibilityConcern(
                id="concern-program-area",
                dimension=DecisionDimension.SPACE_QUANTITY,
                description=(
                    f"Required non-optional program area ({required_area:.1f} sqft) exceeds "
                    f"the setback-adjusted site area ({available_area:.1f} sqft)."
                ),
                severity=AnalysisSeverity.BLOCKING,
                source_ids=[space.id for space in problem.spaces if not space.optional],
            )
        ]
    return []


def analyze_design_problem(
    problem: DesignProblem,
    catalog: dict[str, Any] | None = None,
) -> ArchitecturalAnalysis:
    """
    Build a deterministic, non-geometric analysis of a DesignProblem.
    Generically integrates candidate decision alternatives, incompatibilities, and relationships
    from the declarative Decision Catalog.
    """
    if catalog is None:
        try:
            catalog = load_decision_catalog()
        except (FileNotFoundError, ValueError):
            catalog = {}

    fixed_decisions = _explicit_decisions(problem)
    flexible_decisions = _flexible_decisions(problem, fixed_decisions, catalog=catalog)

    # Attach catalog alternatives generically if not already present
    for record in flexible_decisions:
        if not record.alternatives:
            record.alternatives = get_catalog_alternatives(record.dimension, catalog=catalog)

    dimensions = _unique_in_order(
        [decision.dimension for decision in fixed_decisions]
        + [decision.dimension for decision in flexible_decisions]
    )
    hard_constraints: list[Constraint | Requirement] = [
        constraint
        for constraint in problem.constraints
        if constraint.strength is RequirementStrength.HARD
    ] + [
        requirement
        for requirement in problem.requirements
        if requirement.strength is RequirementStrength.HARD
    ]
    soft_preferences: list[Preference | Requirement] = list(problem.preferences) + [
        requirement
        for requirement in problem.requirements
        if requirement.strength is RequirementStrength.SOFT
    ]
    conflicts = _conflicts(problem)
    uncertainties = _uncertainties(problem, flexible_decisions)
    dependencies = _dependencies(set(dimensions))
    feasibility_concerns = _feasibility_concerns(problem)

    incompatibilities = get_catalog_incompatibilities(catalog=catalog)
    relationships = get_catalog_relationships(catalog=catalog)

    return ArchitecturalAnalysis(
        problem_id=problem.id,
        problem_version=problem.version,
        summary=(
            f"Identified {len(fixed_decisions)} fixed decisions, "
            f"{len(flexible_decisions)} flexible decisions, and "
            f"{len(conflicts)} explicit conflicts."
        ),
        fixed_decisions=fixed_decisions,
        flexible_decisions=flexible_decisions,
        hard_constraints=hard_constraints,
        soft_preferences=soft_preferences,
        objectives=list(problem.objectives),
        conflicts=conflicts,
        uncertainties=uncertainties,
        decision_dimensions=dimensions,
        dependencies=dependencies,
        feasibility_concerns=feasibility_concerns,
        incompatibilities=incompatibilities,
        relationships=relationships,
        provenance={
            "analyzer": "deterministic-rule-based",
            "source_problem_id": problem.id,
            "source_problem_version": problem.version,
        },
    )