"""
CandidateOrganizer module for Stage 3B.4C-2.

Enriches non-geometric DesignCandidate objects with abstract spatial topology by executing
declarative OrganizationRule objects.

Stage 3B.4C-2 Architecture:
Pure Generic Data-Driven Organization Derivation Engine.
Zero geometry, zero solver calls, zero LLM integration.
Zero Python dimension/value branches (no 'if dimension == ...' or 'if value == ...').

Pipeline:
1. Decision Pattern Matching (matches selected_decisions against OrganizationRule triggers)
2. Generic Action Execution (group_by_attribute, assign_floor_tier, create_circulation_node, create_service_stack)
3. Duplicate ID Prevention & Topological Collection Validation
4. Provenance Preservation & Deterministic Model Assembly
"""

from typing import Any

from app.schemas.architectural_analysis import (
    DecisionRecord,
    OrganizationAction,
    OrganizationRule,
)
from app.schemas.design_candidate import (
    AbstractCirculationNode,
    AbstractServiceStack,
    DesignCandidate,
)
from app.schemas.design_problem import DesignProblem


def _dim_to_str(dim: Any) -> str:
    """Convert a decision dimension (Enum or str) to string representation."""
    if hasattr(dim, "value"):
        return str(dim.value)
    return str(dim)


def _matches_trigger(dec: DecisionRecord, rule: OrganizationRule) -> bool:
    """Check if a selected decision record matches an organization rule trigger."""
    dec_dim = _dim_to_str(dec.dimension)
    rule_dim = _dim_to_str(rule.trigger_dimension)

    if dec_dim != rule_dim:
        return False

    if dec.value == rule.trigger_value:
        return True

    # If trigger_value is a dict, check if dec.value is a dict containing matching subset
    if isinstance(rule.trigger_value, dict) and isinstance(dec.value, dict):
        return all(dec.value.get(k) == v for k, v in rule.trigger_value.items())

    return False


def _execute_group_by_attribute(
    rule: OrganizationRule,
    problem: DesignProblem | None,
    unit_org: dict[str, list[str]],
) -> None:
    """
    Execute GROUP_BY_ATTRIBUTE action generically.
    Groups space IDs into unit containers based on space attributes or metadata.
    """
    params = rule.parameters or {}
    attr_name = params.get("attribute", "owner_id")
    prefix = params.get("fallback_prefix", "unit_")

    if problem and problem.spaces:
        for space in problem.spaces:
            raw_val = getattr(space, attr_name, None)
            if raw_val is None:
                metadata = getattr(space, "metadata", None)
                if isinstance(metadata, dict):
                    raw_val = metadata.get(attr_name)
            if raw_val is None and attr_name == "owner_id":
                raw_val = getattr(space, "owner_id", None)

            if raw_val is not None and str(raw_val).strip():
                unit_key = f"{prefix}{raw_val}"
            else:
                unit_key = f"{prefix}default"

            if unit_key not in unit_org:
                unit_org[unit_key] = []
            if space.id not in unit_org[unit_key]:
                unit_org[unit_key].append(space.id)
    elif "explicit_units" in params and isinstance(params["explicit_units"], dict):
        for ukey, spaces in params["explicit_units"].items():
            if ukey not in unit_org:
                unit_org[ukey] = []
            for s in spaces:
                if s not in unit_org[ukey]:
                    unit_org[ukey].append(s)


def _execute_assign_floor_tier(
    rule: OrganizationRule,
    problem: DesignProblem | None,
    unit_org: dict[str, list[str]],
    floor_org: dict[str, list[str]],
) -> None:
    """
    Execute ASSIGN_FLOOR_TIER action generically.
    Maps spaces or unit containers to floor level/tier IDs.
    """
    params = rule.parameters or {}
    mapping = params.get("tier_mapping", {})

    if "all_spaces" in mapping:
        tier_id = str(mapping["all_spaces"])
        if tier_id not in floor_org:
            floor_org[tier_id] = []

        if problem and problem.spaces:
            for space in problem.spaces:
                if space.id not in floor_org[tier_id]:
                    floor_org[tier_id].append(space.id)
        elif unit_org:
            for ukey, spaces in unit_org.items():
                for s in spaces:
                    if s not in floor_org[tier_id]:
                        floor_org[tier_id].append(s)

    elif "by_unit" in mapping and mapping["by_unit"] == "even_distribution":
        num_floors = problem.site.floors if (problem and problem.site) else 1
        unit_keys = sorted(unit_org.keys())

        if not unit_keys and problem and problem.spaces:
            all_spaces = [s.id for s in problem.spaces]
            unit_keys = ["unit_default"]
            unit_org["unit_default"] = all_spaces

        for idx, ukey in enumerate(unit_keys):
            floor_idx = (idx % num_floors) + 1
            tier_id = f"floor_{floor_idx}"
            if tier_id not in floor_org:
                floor_org[tier_id] = []
            for s in unit_org[ukey]:
                if s not in floor_org[tier_id]:
                    floor_org[tier_id].append(s)

    elif "explicit_floors" in params and isinstance(params["explicit_floors"], dict):
        for ftier, spaces in params["explicit_floors"].items():
            if ftier not in floor_org:
                floor_org[ftier] = []
            for s in spaces:
                if s not in floor_org[ftier]:
                    floor_org[ftier].append(s)


def _execute_create_circulation_node(
    rule: OrganizationRule,
    problem: DesignProblem | None,
    unit_org: dict[str, list[str]],
    circ_intent: list[AbstractCirculationNode],
) -> None:
    """
    Execute CREATE_CIRCULATION_NODE action generically.
    Instantiates an AbstractCirculationNode connecting spaces or units.
    """
    params = rule.parameters or {}
    node_id = str(params.get("node_id", f"circ-node-{len(circ_intent)+1}"))
    node_type = str(params.get("type", "circulation_core"))
    access_type = str(params.get("access_type", "shared"))
    scope = params.get("target_scope", "all_units")

    existing_ids = {n.id for n in circ_intent}
    if node_id in existing_ids:
        return

    connected: list[str] = []
    if scope == "all_units" and unit_org:
        connected = sorted(unit_org.keys())
    elif scope == "all_spaces" and problem and problem.spaces:
        connected = sorted([s.id for s in problem.spaces])
    elif isinstance(scope, list):
        connected = sorted(scope)
    else:
        connected = sorted(unit_org.keys()) if unit_org else ["space_all"]

    node = AbstractCirculationNode(
        id=node_id,
        type=node_type,
        connected_space_ids=connected,
        access_type=access_type,
    )
    circ_intent.append(node)


def _execute_create_service_stack(
    rule: OrganizationRule,
    problem: DesignProblem | None,
    serv_org: list[AbstractServiceStack],
) -> None:
    """
    Execute CREATE_SERVICE_STACK action generically.
    Instantiates an AbstractServiceStack grouping spaces by category or scope.
    """
    params = rule.parameters or {}
    stack_id = str(params.get("stack_id", f"stack-core-{len(serv_org)+1}"))
    service_type = str(params.get("service_type", "service_core"))
    scope = params.get("target_scope", "by_category")
    categories = [str(c).lower() for c in params.get("categories", [])]

    existing_ids = {s.id for s in serv_org}
    if stack_id in existing_ids:
        return

    assigned: list[str] = []
    if scope == "by_category" and problem and problem.spaces:
        for space in problem.spaces:
            r_type = str(space.room.room_type.value if hasattr(space.room.room_type, "value") else space.room.room_type).lower()
            if r_type in categories:
                assigned.append(space.id)
    elif isinstance(scope, list):
        assigned = sorted(scope)
    elif problem and problem.spaces:
        assigned = sorted([s.id for s in problem.spaces])

    stack = AbstractServiceStack(
        id=stack_id,
        service_type=service_type,
        assigned_space_ids=sorted(assigned),
    )
    serv_org.append(stack)


def organize_candidate(
    candidate: DesignCandidate,
    organization_rules: list[OrganizationRule],
    problem: DesignProblem | None = None,
) -> DesignCandidate:
    """
    Enrich an abstract DesignCandidate with derived spatial organization topologies.
    Pure data-driven rule execution. ZERO Python 'if dimension == ...' or 'if value == ...' domain branches.
    """
    cand_dict = candidate.model_dump()

    floor_org: dict[str, list[str]] = dict(candidate.floor_organization)
    unit_org: dict[str, list[str]] = dict(candidate.unit_organization)

    circ_intent: list[AbstractCirculationNode] = [
        AbstractCirculationNode.model_validate(c) if isinstance(c, dict) else c
        for c in candidate.circulation_intent
    ]
    serv_org: list[AbstractServiceStack] = [
        AbstractServiceStack.model_validate(s) if isinstance(s, dict) else s
        for s in candidate.service_organization
    ]

    # Find matching rules generically by inspecting candidate.selected_decisions
    matched_rules: list[OrganizationRule] = []
    for dec in candidate.selected_decisions:
        for rule in organization_rules:
            if _matches_trigger(dec, rule):
                matched_rules.append(rule)

    # Define generic action execution precedence (Containerization -> Floor Tiering -> Topology)
    _ACTION_PRECEDENCE = {
        OrganizationAction.GROUP_BY_ATTRIBUTE: 10,
        OrganizationAction.ASSIGN_FLOOR_TIER: 20,
        OrganizationAction.CREATE_CIRCULATION_NODE: 30,
        OrganizationAction.CREATE_SERVICE_STACK: 40,
    }

    # Deduplicate matching rules deterministically by action precedence then rule.id
    unique_rules: list[OrganizationRule] = []
    seen_rule_ids: set[str] = set()
    for rule in sorted(matched_rules, key=lambda r: (_ACTION_PRECEDENCE.get(r.action, 99), r.id)):
        if rule.id not in seen_rule_ids:
            seen_rule_ids.add(rule.id)
            unique_rules.append(rule)

    # Execute rules generically by action type
    for rule in unique_rules:
        if rule.action == OrganizationAction.GROUP_BY_ATTRIBUTE:
            _execute_group_by_attribute(rule, problem, unit_org)
        elif rule.action == OrganizationAction.ASSIGN_FLOOR_TIER:
            _execute_assign_floor_tier(rule, problem, unit_org, floor_org)
        elif rule.action == OrganizationAction.CREATE_CIRCULATION_NODE:
            _execute_create_circulation_node(rule, problem, unit_org, circ_intent)
        elif rule.action == OrganizationAction.CREATE_SERVICE_STACK:
            _execute_create_service_stack(rule, problem, serv_org)
        else:
            raise ValueError(f"Unsupported OrganizationAction '{rule.action}' in rule '{rule.id}'")

    # Sort dictionary keys and collections deterministically
    sorted_floor_org = {k: sorted(v) for k, v in sorted(floor_org.items())}
    sorted_unit_org = {k: sorted(v) for k, v in sorted(unit_org.items())}
    sorted_circ_intent = sorted(circ_intent, key=lambda n: n.id)
    sorted_serv_org = sorted(serv_org, key=lambda s: s.id)

    provenance = dict(candidate.provenance or {})
    provenance["organizer"] = "generic-data-driven-organizer"
    provenance["matched_rule_ids"] = sorted(list(seen_rule_ids))

    cand_dict["floor_organization"] = sorted_floor_org
    cand_dict["unit_organization"] = sorted_unit_org
    cand_dict["circulation_intent"] = [node.model_dump() for node in sorted_circ_intent]
    cand_dict["service_organization"] = [stack.model_dump() for stack in sorted_serv_org]
    cand_dict["provenance"] = provenance

    return DesignCandidate.model_validate(cand_dict)


def organize_candidates(
    candidates: list[DesignCandidate],
    organization_rules: list[OrganizationRule],
    problem: DesignProblem | None = None,
) -> list[DesignCandidate]:
    """
    Enrich a list of abstract DesignCandidate models with derived spatial organization topologies deterministically.
    """
    enriched: list[DesignCandidate] = []
    for cand in candidates:
        enriched.append(organize_candidate(cand, organization_rules, problem=problem))
    return enriched
