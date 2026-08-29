"""
Test suite for Spatial Realization Schema Contract (Stage 3B.4D-1).

Verifies 20 points:
1. Minimal valid SpatialLayoutPlan
2. SpatialRoomSpec validation
3. SpatialCoreSpec validation
4. Room collections & duplicate ID rejection
5. Core collections & duplicate ID rejection
6. Source traceability
7. Problem/version traceability
8. Arbitrary/custom decision dimensions in realization_parameters
9. Unresolved decisions handling
10. Provenance preservation
11. Invalid/empty IDs rejection
12. Invalid versions rejection
13. Invalid/negative area/dimensions rejection
14. Deterministic serialization
15. JSON round-trip
16. Empty optional collections
17. Non-geometric boundary assertion
18. Benchmark fixture representation without geometry
19. Single-family fixture representation without geometry
20. Repeated construction produces identical serialized output
"""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.spatial_realization import (
    RealizationResult,
    RealizationStatus,
    SpatialAdjacencySpec,
    SpatialCoreSpec,
    SpatialLayoutPlan,
    SpatialRoomSpec,
)
from tests.fixtures.golden_organization_fixtures import (
    get_benchmark_44x42_candidate,
    get_benchmark_44x42_problem,
    get_single_family_candidate,
    get_single_family_problem,
)


def _sample_plan() -> SpatialLayoutPlan:
    return SpatialLayoutPlan(
        id="plan-1",
        source_candidate_id="candidate-1",
        source_strategy_id="strategy-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        plot_width=40.0,
        plot_depth=40.0,
        setbacks={"left": 2.0, "right": 2.0, "top": 2.0, "bottom": 2.0},
        floors=2,
        rooms=[
            SpatialRoomSpec(
                id="room_living",
                name="Living Room",
                room_type="living",
                target_area=250.0,
                aspect_ratio_range=(0.6, 1.8),
                floor_assignment=1,
                unit_id="unit_1",
            ),
            SpatialRoomSpec(
                id="room_bedroom",
                name="Master Bedroom",
                room_type="bedroom",
                target_area=150.0,
                aspect_ratio_range=(0.7, 1.5),
                floor_assignment=2,
                unit_id="unit_1",
            ),
        ],
        adjacencies=[
            SpatialAdjacencySpec(
                source_space_id="room_living",
                target_space_id="room_bedroom",
                strength="soft",
                weight=0.8,
            )
        ],
        cores=[
            SpatialCoreSpec(
                id="core_stairwell",
                core_type="vertical_stairwell",
                access_type="shared",
                floors=[1, 2],
                connected_space_ids=["room_living", "room_bedroom"],
            )
        ],
        realization_parameters={"custom_dimension": "solar_shading", "grid_snap": 0.5},
        provenance={"generator": "sample-plan-builder"},
    )


def test_01_minimal_valid_spatial_layout_plan():
    """Point 1: Verify minimal valid SpatialLayoutPlan builds with required fields."""
    plan = SpatialLayoutPlan(
        id="plan-min",
        source_candidate_id="cand-min",
        source_strategy_id="strat-min",
        source_problem_id="prob-min",
        source_problem_version=1,
        plot_width=30.0,
        plot_depth=40.0,
    )
    assert plan.id == "plan-min"
    assert plan.plot_width == 30.0
    assert plan.rooms == []
    assert plan.cores == []


def test_02_spatial_room_spec_validation():
    """Point 2: Verify SpatialRoomSpec field constraints and aspect ratio validations."""
    room = SpatialRoomSpec(
        id="r-1",
        name="Kitchen",
        room_type="kitchen",
        target_area=120.0,
        aspect_ratio_range=(0.5, 2.0),
        floor_assignment=1,
    )
    assert room.id == "r-1"
    assert room.target_area == 120.0

    # Negative area rejection
    with pytest.raises(ValidationError):
        SpatialRoomSpec(id="r-bad", name="Bad", room_type="living", target_area=-50.0)

    # Invalid aspect ratio range (min > max)
    with pytest.raises(ValidationError):
        SpatialRoomSpec(id="r-bad", name="Bad", room_type="living", target_area=100.0, aspect_ratio_range=(2.0, 0.5))


def test_03_spatial_core_spec_validation():
    """Point 3: Verify SpatialCoreSpec validation."""
    core = SpatialCoreSpec(
        id="c-1",
        core_type="plumbing_wet_core",
        access_type="shared",
        floors=[1, 2, 3],
        connected_space_ids=["r-1", "r-2"],
    )
    assert core.id == "c-1"
    assert len(core.floors) == 3

    # Empty core ID rejection
    with pytest.raises(ValidationError):
        SpatialCoreSpec(id="", core_type="vertical_stairwell")


def test_04_room_collections_and_duplicate_id_rejection():
    """Point 4: Verify duplicate room IDs are rejected by SpatialLayoutPlan."""
    r1 = SpatialRoomSpec(id="dup_room", name="Room A", room_type="living", target_area=100.0)
    r2 = SpatialRoomSpec(id="dup_room", name="Room B", room_type="bedroom", target_area=100.0)

    with pytest.raises(ValidationError) as exc:
        SpatialLayoutPlan(
            id="plan-dup-room",
            source_candidate_id="cand-1",
            source_strategy_id="strat-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            plot_width=30.0,
            plot_depth=40.0,
            rooms=[r1, r2],
        )
    assert "Room IDs must be unique" in str(exc.value)


def test_05_core_collections_and_duplicate_id_rejection():
    """Point 5: Verify duplicate core IDs are rejected by SpatialLayoutPlan."""
    c1 = SpatialCoreSpec(id="dup_core", core_type="vertical_stairwell")
    c2 = SpatialCoreSpec(id="dup_core", core_type="plumbing_wet_core")

    with pytest.raises(ValidationError) as exc:
        SpatialLayoutPlan(
            id="plan-dup-core",
            source_candidate_id="cand-1",
            source_strategy_id="strat-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            plot_width=30.0,
            plot_depth=40.0,
            cores=[c1, c2],
        )
    assert "Core IDs must be unique" in str(exc.value)


def test_06_source_traceability():
    """Point 6: Verify source strategy and candidate traceability fields are enforced."""
    plan = _sample_plan()
    assert plan.source_candidate_id == "candidate-1"
    assert plan.source_strategy_id == "strategy-1"


def test_07_problem_and_version_traceability():
    """Point 7: Verify source problem ID and version traceability fields are enforced."""
    plan = _sample_plan()
    assert plan.source_problem_id == "prob-1"
    assert plan.source_problem_version == 1


def test_08_arbitrary_custom_decision_dimensions():
    """Point 8: Verify custom/unseen decision dimensions are preserved in realization_parameters."""
    plan = SpatialLayoutPlan(
        id="plan-custom",
        source_candidate_id="cand-custom",
        source_strategy_id="strat-custom",
        source_problem_id="prob-custom",
        source_problem_version=1,
        plot_width=44.0,
        plot_depth=42.0,
        realization_parameters={
            "solar_shading_strategy": "external_screen",
            "facade_transparency": "fully_glazed",
            "custom_numeric_param": 42.5,
        },
    )
    assert plan.realization_parameters["solar_shading_strategy"] == "external_screen"
    assert plan.realization_parameters["facade_transparency"] == "fully_glazed"
    assert plan.realization_parameters["custom_numeric_param"] == 42.5


def test_09_unresolved_decisions_handling():
    """Point 9: Verify unresolved decision dimensions can be captured in realization metadata."""
    plan = _sample_plan()
    plan.realization_parameters["unresolved_decisions"] = ["orientation", "zoning"]
    assert "orientation" in plan.realization_parameters["unresolved_decisions"]


def test_10_provenance_preservation():
    """Point 10: Verify provenance metadata is preserved."""
    plan = _sample_plan()
    assert plan.provenance["generator"] == "sample-plan-builder"


def test_11_invalid_empty_ids_rejection():
    """Point 11: Verify empty or whitespace string IDs are rejected."""
    with pytest.raises(ValidationError):
        SpatialLayoutPlan(
            id="  ",
            source_candidate_id="cand-1",
            source_strategy_id="strat-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            plot_width=30.0,
            plot_depth=40.0,
        )

    with pytest.raises(ValidationError):
        SpatialLayoutPlan(
            id="plan-1",
            source_candidate_id="",
            source_strategy_id="strat-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            plot_width=30.0,
            plot_depth=40.0,
        )


def test_12_invalid_versions_rejection():
    """Point 12: Verify invalid/zero/negative problem version numbers are rejected."""
    with pytest.raises(ValidationError):
        SpatialLayoutPlan(
            id="plan-bad-ver",
            source_candidate_id="cand-1",
            source_strategy_id="strat-1",
            source_problem_id="prob-1",
            source_problem_version=0,
            plot_width=30.0,
            plot_depth=40.0,
        )


def test_13_invalid_negative_dimensions_rejection():
    """Point 13: Verify negative or zero plot width/depth dimensions are rejected."""
    with pytest.raises(ValidationError):
        SpatialLayoutPlan(
            id="plan-neg-plot",
            source_candidate_id="cand-1",
            source_strategy_id="strat-1",
            source_problem_id="prob-1",
            source_problem_version=1,
            plot_width=-10.0,
            plot_depth=40.0,
        )


def test_14_deterministic_serialization():
    """Point 14: Verify deterministic serialization to dict."""
    plan = _sample_plan()
    dump_1 = plan.model_dump()
    dump_2 = plan.model_dump()
    assert dump_1 == dump_2


def test_15_json_round_trip():
    """Point 15: Verify JSON round-trip serialization and deserialization."""
    plan = _sample_plan()
    json_str = plan.model_dump_json()
    deserialized = SpatialLayoutPlan.model_validate_json(json_str)

    assert deserialized.id == plan.id
    assert len(deserialized.rooms) == len(plan.rooms)
    assert deserialized.rooms[0].target_area == plan.rooms[0].target_area


def test_16_empty_optional_collections():
    """Point 16: Verify plan builds with empty optional collections."""
    plan = SpatialLayoutPlan(
        id="plan-empty-colls",
        source_candidate_id="cand-1",
        source_strategy_id="strat-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        plot_width=30.0,
        plot_depth=40.0,
    )
    assert plan.rooms == []
    assert plan.adjacencies == []
    assert plan.cores == []
    assert plan.setbacks == {}


def test_17_non_geometric_boundary_assertion():
    """Point 17: Assert schema contains ZERO geometric coordinate fields or polygon objects."""
    plan = _sample_plan()
    dump_str = json.dumps(plan.model_dump()).lower()

    for geo_kw in ["polygon", "mesh", "coordinate", "cad_layer", "vertex", "bounding_box", "vector3"]:
        assert geo_kw not in dump_str


def test_18_benchmark_fixture_representation_without_geometry():
    """Point 18: Verify 44x42 benchmark scenario can be represented as a SpatialLayoutPlan without geometry."""
    prob = get_benchmark_44x42_problem()
    cand = get_benchmark_44x42_candidate(prob)

    # Convert spaces into SpatialRoomSpecs conceptually
    rooms = [
        SpatialRoomSpec(
            id=s.id,
            name=s.id.replace("_", " ").title(),
            room_type=s.room.room_type.value if hasattr(s.room.room_type, "value") else str(s.room.room_type),
            target_area=120.0,
            unit_id=s.owner_id,
        )
        for s in prob.spaces
    ]

    cores = [
        SpatialCoreSpec(
            id="circ-shared-vertical-core",
            core_type="vertical_stairwell",
            access_type="shared",
            floors=[1, 2, 3, 4],
            connected_space_ids=[s.id for s in prob.spaces],
        )
    ]

    plan = SpatialLayoutPlan(
        id="plan-44x42-benchmark",
        source_candidate_id=cand.id,
        source_strategy_id=cand.source_strategy_id,
        source_problem_id=prob.id,
        source_problem_version=prob.version,
        plot_width=prob.site.plot_width,
        plot_depth=prob.site.plot_depth,
        floors=prob.site.floors,
        rooms=rooms,
        cores=cores,
    )

    assert plan.plot_width == 44.0
    assert len(plan.rooms) == 16
    assert len(plan.cores) == 1


def test_19_single_family_fixture_representation_without_geometry():
    """Point 19: Verify single-family scenario can be represented as a SpatialLayoutPlan without geometry."""
    prob = get_single_family_problem()
    cand = get_single_family_candidate(prob)

    rooms = [
        SpatialRoomSpec(
            id=s.id,
            name=s.id.replace("_", " ").title(),
            room_type=s.room.room_type.value if hasattr(s.room.room_type, "value") else str(s.room.room_type),
            target_area=150.0,
            floor_assignment=1,
            unit_id=s.owner_id,
        )
        for s in prob.spaces
    ]

    plan = SpatialLayoutPlan(
        id="plan-sf",
        source_candidate_id=cand.id,
        source_strategy_id=cand.source_strategy_id,
        source_problem_id=prob.id,
        source_problem_version=prob.version,
        plot_width=prob.site.plot_width,
        plot_depth=prob.site.plot_depth,
        floors=1,
        rooms=rooms,
    )

    assert plan.plot_width == 30.0
    assert plan.plot_depth == 40.0
    assert len(plan.rooms) == 5


def test_20_repeated_construction_stability():
    """Point 20: Verify repeated construction produces identical serialized output across 100 iterations."""
    baseline = _sample_plan().model_dump()
    for _ in range(100):
        dump = _sample_plan().model_dump()
        assert dump == baseline


def test_realization_result_schema():
    """Verify RealizationResult captures success and failure statuses."""
    plan = _sample_plan()
    res_success = RealizationResult(
        status=RealizationStatus.SUCCESS,
        success=True,
        candidate_id="cand-1",
        layout_plan=plan,
    )
    assert res_success.success is True
    assert res_success.status == RealizationStatus.SUCCESS

    res_fail = RealizationResult(
        status=RealizationStatus.SPATIALLY_INFEASIBLE,
        success=False,
        candidate_id="cand-1",
        error_message="Buildable envelope exceeded",
        infeasible_constraints=["req-setback-left"],
    )
    assert res_fail.success is False
    assert res_fail.status == RealizationStatus.SPATIALLY_INFEASIBLE
    assert "req-setback-left" in res_fail.infeasible_constraints
