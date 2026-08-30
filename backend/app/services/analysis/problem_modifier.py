"""
Problem Modifier module for Stage 3B Requirement Modification Loop (Task 4).

Applies RequirementDelta operations (add, remove, replace, modify) to an existing DesignProblem,
producing a new versioned DesignProblem ready for architectural re-analysis and strategy re-generation.
"""

from typing import Any
import uuid

from app.schemas.design_problem import (
    DesignProblem,
    Requirement,
    RequirementDelta,
    RequirementKind,
    RequirementStrength,
    SiteDefinition,
    SpaceRequirement,
    UserGroup,
)
from app.services.ai.parser import parse_requirements
from app.services.compiler.intent_adapter import to_design_problem


def parse_prompt_delta_to_requirement_delta(
    delta_prompt: str,
    base_problem: DesignProblem,
) -> list[RequirementDelta]:
    """
    Parses a natural language delta instruction and maps it to structured RequirementDeltas.
    """
    delta_intent = parse_requirements(delta_prompt)
    deltas: list[RequirementDelta] = []
    current_ver = getattr(base_problem, "version", 1)

    if delta_intent.vertical_circulation:
        deltas.append(
            RequirementDelta(
                id=f"delta-circ-{uuid.uuid4().hex[:6]}",
                base_problem_id=base_problem.id,
                parent_version=current_ver,
                operation="replace",
                target_id="req-circ",
                value={
                    "kind": RequirementKind.CIRCULATION,
                    "subject": "vertical_circulation",
                    "value": delta_intent.vertical_circulation,
                    "strength": RequirementStrength.HARD,
                    "priority": 95,
                },
                source_text=delta_prompt,
            )
        )

    if delta_intent.floor_allocation:
        deltas.append(
            RequirementDelta(
                id=f"delta-floor-{uuid.uuid4().hex[:6]}",
                base_problem_id=base_problem.id,
                parent_version=current_ver,
                operation="replace",
                target_id="req-floor-alloc",
                value={
                    "kind": RequirementKind.ASSIGNMENT,
                    "subject": "floor_allocation",
                    "value": delta_intent.floor_allocation,
                    "strength": RequirementStrength.HARD,
                    "priority": 95,
                },
                source_text=delta_prompt,
            )
        )

    if delta_intent.entrance_strategy:
        deltas.append(
            RequirementDelta(
                id=f"delta-entrance-{uuid.uuid4().hex[:6]}",
                base_problem_id=base_problem.id,
                parent_version=current_ver,
                operation="replace",
                target_id="req-entrance",
                value={
                    "kind": RequirementKind.ACCESSIBILITY,
                    "subject": "entrance_strategy",
                    "value": delta_intent.entrance_strategy,
                    "strength": RequirementStrength.HARD,
                    "priority": 85,
                },
                source_text=delta_prompt,
            )
        )

    return deltas


def apply_requirement_delta(
    base_problem: DesignProblem,
    delta: RequirementDelta,
) -> DesignProblem:
    """
    Applies a single RequirementDelta to a DesignProblem, returning a new updated DesignProblem.
    """
    new_requirements = list(base_problem.requirements)
    target_id = delta.target_id

    if delta.operation in ("replace", "modify", "add"):
        # Remove existing target requirement if present
        if target_id:
            new_requirements = [r for r in new_requirements if r.id != target_id and r.subject != target_id]

        if isinstance(delta.value, dict):
            val_dict = delta.value
            req = Requirement(
                id=target_id or f"req-{uuid.uuid4().hex[:6]}",
                kind=val_dict.get("kind", RequirementKind.CIRCULATION),
                subject=val_dict.get("subject", target_id or "custom"),
                value=val_dict.get("value"),
                strength=val_dict.get("strength", RequirementStrength.HARD),
                priority=val_dict.get("priority", 90),
            )
            new_requirements.append(req)
        elif isinstance(delta.value, Requirement):
            new_requirements.append(delta.value)

    elif delta.operation == "remove":
        if target_id:
            new_requirements = [r for r in new_requirements if r.id != target_id and r.subject != target_id]

    new_version = base_problem.version + 1
    new_id = f"{base_problem.id}-v{new_version}"

    # Update provenance
    prov = dict(base_problem.provenance)
    prov["parent_problem_id"] = base_problem.id
    prov["parent_version"] = base_problem.version
    prov["last_delta_id"] = delta.id
    prov["last_delta_source"] = delta.source_text

    return DesignProblem(
        id=new_id,
        version=new_version,
        site=base_problem.site,
        spaces=base_problem.spaces,
        user_groups=base_problem.user_groups,
        requirements=new_requirements,
        constraints=base_problem.constraints,
        preferences=base_problem.preferences,
        objectives=base_problem.objectives,
        deltas=list(base_problem.deltas) + [delta],
        provenance=prov,
    )


def apply_requirement_deltas(
    base_problem: DesignProblem,
    deltas: list[RequirementDelta],
) -> DesignProblem:
    """
    Sequentially applies a list of RequirementDeltas to a DesignProblem.
    """
    current_problem = base_problem
    for delta in deltas:
        current_problem = apply_requirement_delta(current_problem, delta)
    return current_problem
