"""
CandidateGenerator module for Stage 3B.4B.

Transforms DesignStrategy objects into abstract, non-geometric DesignCandidate objects.

Stage 3B.4B Architecture:
Pure Generic Data-Driven Candidate Generator Engine.
Zero geometry, zero solver calls, zero LLM integration, zero semantic organization inference.

Pipeline:
1. Strategy Mapping (1 Strategy -> 1 Candidate)
2. Bounded Candidate Generation (respecting max_candidates)
3. Data-Driven Attribute Preservation (selected decisions, unresolved choices, risks, assumptions, feasibility, provenance)
4. Explicit Structured Organization Preservation (preserves floor/unit/circulation/service topology ONLY when explicitly structured in strategy decision values or provenance; leaves empty otherwise)
5. Deterministic ID Assignment & Bounding
"""

from typing import Any

from app.schemas.architectural_analysis import (
    DecisionRecord,
    DecisionStatus,
)
from app.schemas.design_candidate import (
    AbstractCirculationNode,
    AbstractServiceStack,
    DesignCandidate,
)
from app.schemas.design_strategy import DesignStrategy

DEFAULT_MAX_CANDIDATES = 10


def _dim_to_str(dim: Any) -> str:
    """Convert a decision dimension (Enum or str) to string representation."""
    if hasattr(dim, "value"):
        return str(dim.value)
    return str(dim)


def _extract_explicit_abstract_organization(
    strategy: DesignStrategy,
) -> tuple[
    dict[str, list[str]],
    dict[str, list[str]],
    list[AbstractCirculationNode],
    list[AbstractServiceStack],
]:
    """
    Extract structured abstract spatial organization ONLY if explicitly provided in strategy decision values or provenance.
    STRICT NON-INFERENCE BOUNDARY: Must NOT infer topology from semantic strings (e.g. 'shared', 'distributed', 'centralized').
    """
    floor_org: dict[str, list[str]] = {}
    unit_org: dict[str, list[str]] = {}
    circ_intent: list[AbstractCirculationNode] = []
    serv_org: list[AbstractServiceStack] = []

    # 1. Check decision values for explicit structured organization dicts
    for dec in strategy.decisions:
        if isinstance(dec.value, dict):
            val_dict = dec.value
            if "floor_organization" in val_dict and isinstance(val_dict["floor_organization"], dict):
                floor_org.update(val_dict["floor_organization"])
            if "unit_organization" in val_dict and isinstance(val_dict["unit_organization"], dict):
                unit_org.update(val_dict["unit_organization"])
            if "circulation_intent" in val_dict and isinstance(val_dict["circulation_intent"], list):
                for item in val_dict["circulation_intent"]:
                    if isinstance(item, AbstractCirculationNode):
                        circ_intent.append(item)
                    elif isinstance(item, dict):
                        circ_intent.append(AbstractCirculationNode.model_validate(item))
            if "service_organization" in val_dict and isinstance(val_dict["service_organization"], list):
                for item in val_dict["service_organization"]:
                    if isinstance(item, AbstractServiceStack):
                        serv_org.append(item)
                    elif isinstance(item, dict):
                        serv_org.append(AbstractServiceStack.model_validate(item))

    # 2. Check strategy provenance for explicit structured organization overrides
    prov = strategy.provenance or {}
    if "floor_organization" in prov and isinstance(prov["floor_organization"], dict):
        floor_org.update(prov["floor_organization"])
    if "unit_organization" in prov and isinstance(prov["unit_organization"], dict):
        unit_org.update(prov["unit_organization"])
    if "circulation_intent" in prov and isinstance(prov["circulation_intent"], list):
        for item in prov["circulation_intent"]:
            if isinstance(item, AbstractCirculationNode):
                circ_intent.append(item)
            elif isinstance(item, dict):
                circ_intent.append(AbstractCirculationNode.model_validate(item))
    if "service_organization" in prov and isinstance(prov["service_organization"], list):
        for item in prov["service_organization"]:
            if isinstance(item, AbstractServiceStack):
                serv_org.append(item)
            elif isinstance(item, dict):
                serv_org.append(AbstractServiceStack.model_validate(item))

    return floor_org, unit_org, circ_intent, serv_org


def generate_candidate_from_strategy(
    strategy: DesignStrategy,
    candidate_id: str | None = None,
) -> DesignCandidate:
    """
    Convert a single DesignStrategy object into a DesignCandidate object deterministically.
    """
    cid = candidate_id or f"candidate-{strategy.id}"

    selected_decisions = list(strategy.decisions)
    assigned_dims = {_dim_to_str(d.dimension) for d in selected_decisions if d.status != DecisionStatus.UNRESOLVED}

    unresolved_decisions: list[DecisionRecord] = [
        d for d in selected_decisions if d.status == DecisionStatus.UNRESOLVED
    ]
    seen_unresolved_dims = {_dim_to_str(d.dimension) for d in unresolved_decisions}

    for flex_dim in strategy.flexible_decisions:
        dim_str = _dim_to_str(flex_dim)
        if dim_str not in assigned_dims and dim_str not in seen_unresolved_dims:
            unresolved_decisions.append(
                DecisionRecord(
                    id=f"unresolved-{dim_str}",
                    dimension=flex_dim,
                    subject="building",
                    status=DecisionStatus.UNRESOLVED,
                    rationale=f"Decision dimension '{dim_str}' left flexible by strategy '{strategy.id}'.",
                )
            )
            seen_unresolved_dims.add(dim_str)

    # Extract explicit abstract spatial organization (NO SEMANTIC STRING INFERENCE)
    floor_org, unit_org, circ_intent, serv_org = _extract_explicit_abstract_organization(strategy)

    provenance = {
        "generator": "deterministic-data-driven-candidate",
        "source_strategy_id": strategy.id,
        "source_analysis_id": strategy.source_analysis_id,
        "source_problem_id": strategy.source_problem_id,
        "source_problem_version": strategy.source_problem_version,
        "fingerprint": strategy.provenance.get("fingerprint", f"candidate-fingerprint-{strategy.id}"),
    }

    return DesignCandidate(
        id=cid,
        source_strategy_id=strategy.id,
        source_analysis_id=strategy.source_analysis_id,
        source_problem_id=strategy.source_problem_id,
        source_problem_version=strategy.source_problem_version,
        candidate_version=1,
        name=f"Candidate for {strategy.name}",
        selected_decisions=selected_decisions,
        floor_organization=floor_org,
        unit_organization=unit_org,
        circulation_intent=circ_intent,
        service_organization=serv_org,
        unresolved_decisions=unresolved_decisions,
        assumptions=list(strategy.assumptions),
        risks=list(strategy.risks),
        feasibility_expectation=strategy.feasibility_expectation,
        confidence=strategy.confidence,
        provenance=provenance,
    )


def generate_candidates(
    strategies: list[DesignStrategy],
    *,
    max_candidates: int = DEFAULT_MAX_CANDIDATES,
) -> list[DesignCandidate]:
    """
    Transform a list of DesignStrategy objects into a bounded list of DesignCandidate objects deterministically.
    """
    candidates: list[DesignCandidate] = []
    for idx, strategy in enumerate(strategies[:max_candidates], start=1):
        cid = f"candidate-{idx}"
        candidate = generate_candidate_from_strategy(strategy, candidate_id=cid)
        candidates.append(candidate)
    return candidates
