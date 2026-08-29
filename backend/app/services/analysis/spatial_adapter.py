"""
Spatial Adapter module for Stage 3B.4D-2.

Translates abstract DesignCandidate and DesignProblem models into a non-geometric SpatialLayoutPlan.
Pure data-driven translation engine. ZERO Python 'if dimension == ...' or 'if value == ...' domain branches.

STRICT NON-GEOMETRIC BOUNDARY:
MUST NOT create Shapely objects, X/Y coordinates, bounding box tuples, polygon vertices,
or call solver/compiler functions (solve_layout, compile_blueprint).
"""

from typing import Any

from app.schemas.design_candidate import DesignCandidate
from app.schemas.design_problem import DesignProblem, SpaceRequirement
from app.schemas.spatial_realization import (
    SpatialAdjacencySpec,
    SpatialCoreSpec,
    SpatialLayoutPlan,
    SpatialRoomSpec,
)


def _dim_to_str(dim: Any) -> str:
    """Convert a decision dimension (Enum or str) to string representation."""
    if hasattr(dim, "value"):
        return str(dim.value)
    return str(dim)


def _parse_floor_assignment(floor_key: str) -> int:
    """Parse floor tier key (e.g., 'floor_1', 'floor_2') to integer (1-indexed)."""
    digits = "".join([c for c in str(floor_key) if c.isdigit()])
    if digits:
        try:
            return max(1, int(digits))
        except ValueError:
            return 1
    return 1


class CandidateToLayoutAdapter:
    """
    Adapter converting an enriched DesignCandidate and DesignProblem into a SpatialLayoutPlan.
    """

    @classmethod
    def adapt(
        cls,
        candidate: DesignCandidate,
        problem: DesignProblem,
        plan_id: str | None = None,
    ) -> SpatialLayoutPlan:
        """
        Deterministically translate DesignCandidate + DesignProblem into SpatialLayoutPlan.
        """
        pid = plan_id or f"plan-{candidate.id}"

        # 1. Build floor assignment mapping (space_id -> floor_int)
        space_to_floor: dict[str, int] = {}
        for floor_key, space_ids in candidate.floor_organization.items():
            floor_int = _parse_floor_assignment(floor_key)
            for sid in space_ids:
                space_to_floor[sid] = floor_int

        # 2. Build unit container mapping (space_id -> unit_id)
        space_to_unit: dict[str, str] = {}
        for unit_key, space_ids in candidate.unit_organization.items():
            for sid in space_ids:
                space_to_unit[sid] = unit_key

        # 3. Build SpatialRoomSpecs from problem.spaces (or fallback to candidate space IDs)
        spatial_rooms: list[SpatialRoomSpec] = []
        spatial_adjacencies: list[SpatialAdjacencySpec] = []

        problem_space_map: dict[str, SpaceRequirement] = {s.id: s for s in problem.spaces} if problem.spaces else {}

        # Collect space IDs from problem spaces and candidate organizations
        all_space_ids: set[str] = set(problem_space_map.keys())
        for sids in candidate.floor_organization.values():
            all_space_ids.update(sids)
        for sids in candidate.unit_organization.values():
            all_space_ids.update(sids)

        for sid in sorted(list(all_space_ids)):
            space_req = problem_space_map.get(sid)
            if space_req:
                r_type = (
                    space_req.room.room_type.value
                    if hasattr(space_req.room.room_type, "value")
                    else str(space_req.room.room_type)
                )
                if hasattr(space_req.room, "min_area_sqft") and space_req.room.min_area_sqft:
                    target_area = float(space_req.room.min_area_sqft)
                elif hasattr(space_req, "metadata") and isinstance(space_req.metadata, dict):
                    target_area = float(space_req.metadata.get("target_area", 120.0))
                else:
                    target_area = 120.0

                meta_dict = getattr(space_req, "metadata", {}) if isinstance(getattr(space_req, "metadata", None), dict) else {}
                name = str(meta_dict.get("name", sid.replace("_", " ").title()))
                owner_id = space_req.owner_id or space_to_unit.get(sid)

                # Convert space relationships to spatial adjacencies
                for rel in space_req.relationships:
                    rel_type = rel.relation.value if hasattr(rel.relation, "value") else str(rel.relation)
                    if rel_type in ("adjacent", "connected") and rel.target_id:
                        source_id, target_id = sorted([sid, rel.target_id])
                        spatial_adjacencies.append(
                            SpatialAdjacencySpec(
                                source_space_id=source_id,
                                target_space_id=target_id,
                                strength="hard" if rel_type == "adjacent" else "soft",
                                weight=1.0,
                            )
                        )
            else:
                r_type = "general_space"
                target_area = 120.0
                name = sid.replace("_", " ").title()
                owner_id = space_to_unit.get(sid)

            floor_idx = space_to_floor.get(sid, 1)

            spatial_rooms.append(
                SpatialRoomSpec(
                    id=sid,
                    name=name,
                    room_type=r_type,
                    target_area=max(10.0, target_area),
                    aspect_ratio_range=(0.5, 2.0),
                    floor_assignment=floor_idx,
                    unit_id=owner_id,
                )
            )

        # Deduplicate spatial adjacencies deterministically
        unique_adjacencies: list[SpatialAdjacencySpec] = []
        seen_adj_keys: set[str] = set()
        for adj in sorted(spatial_adjacencies, key=lambda a: (a.source_space_id, a.target_space_id)):
            key = f"{adj.source_space_id}:{adj.target_space_id}"
            if key not in seen_adj_keys:
                seen_adj_keys.add(key)
                unique_adjacencies.append(adj)

        # 4. Build SpatialCoreSpecs from candidate circulation_intent & service_organization
        spatial_cores: list[SpatialCoreSpec] = []
        total_floors = problem.site.floors if (problem.site and problem.site.floors) else 1
        all_floors_list = list(range(1, total_floors + 1))

        for node in sorted(candidate.circulation_intent, key=lambda n: n.id):
            spatial_cores.append(
                SpatialCoreSpec(
                    id=node.id,
                    core_type=node.type,
                    access_type=node.access_type,
                    floors=all_floors_list,
                    connected_space_ids=sorted(list(node.connected_space_ids)),
                )
            )

        for stack in sorted(candidate.service_organization, key=lambda s: s.id):
            spatial_cores.append(
                SpatialCoreSpec(
                    id=stack.id,
                    core_type=stack.service_type,
                    access_type="service",
                    floors=all_floors_list,
                    connected_space_ids=sorted(list(stack.assigned_space_ids)),
                )
            )

        # 5. Extract generic realization parameters (decisions, unresolved decisions, custom dimensions)
        selected_dec_map: dict[str, Any] = {}
        custom_dimensions: dict[str, Any] = {}
        for dec in candidate.selected_decisions:
            dim_str = _dim_to_str(dec.dimension)
            selected_dec_map[dim_str] = dec.value

        unresolved_decs: list[dict[str, Any]] = [
            {"dimension": _dim_to_str(d.dimension), "rationale": d.rationale} for d in candidate.unresolved_decisions
        ]

        realization_params: dict[str, Any] = {
            "selected_decisions": selected_dec_map,
            "unresolved_decisions": unresolved_decs,
        }

        # 6. Preserve complete provenance
        provenance = dict(candidate.provenance or {})
        provenance["adapter"] = "CandidateToLayoutAdapter"
        provenance["assumptions"] = list(candidate.assumptions)
        provenance["risks"] = [r.model_dump() if hasattr(r, "model_dump") else r for r in candidate.risks]
        provenance["confidence"] = candidate.confidence
        provenance["feasibility_expectation"] = (
            candidate.feasibility_expectation.value
            if hasattr(candidate.feasibility_expectation, "value")
            else str(candidate.feasibility_expectation)
        )

        return SpatialLayoutPlan(
            id=pid,
            source_candidate_id=candidate.id,
            source_strategy_id=candidate.source_strategy_id,
            source_problem_id=candidate.source_problem_id,
            source_problem_version=candidate.source_problem_version,
            plot_width=problem.site.plot_width,
            plot_depth=problem.site.plot_depth,
            setbacks=dict(problem.site.setbacks or {}),
            floors=total_floors,
            rooms=spatial_rooms,
            adjacencies=unique_adjacencies,
            cores=spatial_cores,
            realization_parameters=realization_params,
            provenance=provenance,
        )


def adapt_candidate_to_spatial_layout_plan(
    candidate: DesignCandidate,
    problem: DesignProblem,
    plan_id: str | None = None,
) -> SpatialLayoutPlan:
    """Standalone functional wrapper for CandidateToLayoutAdapter."""
    return CandidateToLayoutAdapter.adapt(candidate, problem, plan_id=plan_id)
