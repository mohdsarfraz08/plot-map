from app.schemas.design_problem import (
    DesignProblem,
    Requirement,
    RequirementKind,
    RequirementStrength,
    SiteDefinition,
    SpaceRequirement,
    UserGroup,
)
from app.schemas.intent import CompilerIntent


def to_design_problem(
    intent: CompilerIntent,
    problem_id: str = "compiler-intent-adapter",
) -> DesignProblem:
    """Convert the CompilerIntent into the Stage 1 DesignProblem model.

    Preserves explicit site geometry, program space requirements, user groups,
    and architectural decision requirements extracted from the user's intent.
    """
    families_count = getattr(intent, "families_count", 1) or 1

    spaces: list[SpaceRequirement] = []
    user_groups: list[UserGroup] = []

    if families_count > 1:
        # Create user groups for families
        for f_idx in range(1, families_count + 1):
            user_groups.append(UserGroup(id=f"family_{f_idx}", name=f"Family {f_idx}"))

        # Assign spaces round-robin or per unit
        for index, room in enumerate(intent.rooms, start=1):
            assigned_family = f"family_{( (index - 1) % families_count ) + 1}"
            spaces.append(
                SpaceRequirement(
                    id=f"room-{index}",
                    room=room,
                    owner_id=assigned_family,
                )
            )
    else:
        spaces = [
            SpaceRequirement(
                id=f"room-{index}",
                room=room,
            )
            for index, room in enumerate(intent.rooms, start=1)
        ]

    requirements: list[Requirement] = []
    mapped_fields = [
        "plot_width",
        "plot_depth",
        "floors",
        "front_road_setback",
        "rooms",
    ]

    # Map circulation preference
    if getattr(intent, "vertical_circulation", None):
        requirements.append(
            Requirement(
                id="req-circ",
                kind=RequirementKind.CIRCULATION,
                subject="vertical_circulation",
                value=intent.vertical_circulation,
                strength=RequirementStrength.HARD,
                priority=90,
            )
        )
        mapped_fields.append("vertical_circulation")

    # Map floor allocation preference
    if getattr(intent, "floor_allocation", None):
        requirements.append(
            Requirement(
                id="req-floor-alloc",
                kind=RequirementKind.ASSIGNMENT,
                subject="floor_allocation",
                value=intent.floor_allocation,
                strength=RequirementStrength.HARD,
                priority=90,
            )
        )
        mapped_fields.append("floor_allocation")

    # Map entrance strategy
    if getattr(intent, "entrance_strategy", None):
        requirements.append(
            Requirement(
                id="req-entrance",
                kind=RequirementKind.ACCESSIBILITY,
                subject="entrance_strategy",
                value=intent.entrance_strategy,
                strength=RequirementStrength.HARD,
                priority=80,
            )
        )
        mapped_fields.append("entrance_strategy")

    # Map unit organization
    if getattr(intent, "unit_organization", None):
        requirements.append(
            Requirement(
                id="req-unit-org",
                kind=RequirementKind.RELATIONSHIP,
                subject="unit_organization",
                value=intent.unit_organization,
                strength=RequirementStrength.HARD,
                priority=80,
            )
        )
        mapped_fields.append("unit_organization")

    return DesignProblem(
        id=problem_id,
        site=SiteDefinition(
            plot_width=intent.plot_width,
            plot_depth=intent.plot_depth,
            floors=intent.floors,
            setbacks={"bottom": intent.front_road_setback},
        ),
        spaces=spaces,
        user_groups=user_groups,
        requirements=requirements,
        provenance={
            "source_type": "CompilerIntent",
            "confidence_score": intent.confidence_score,
            "mapped_fields": mapped_fields,
            "unmapped_fields": [
                "constraints",
                "objectives",
                "relationships",
            ],
        },
    )