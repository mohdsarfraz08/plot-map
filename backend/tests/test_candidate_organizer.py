from typing import Any, cast

import pytest

from app.schemas.architectural_analysis import (
    DecisionDimension,
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
    UserGroup,
)
from app.schemas.intent import RoomCategory, RoomIntent
from app.services.analysis.candidate_organizer import (
    organize_candidate,
    organize_candidates,
)
from app.services.analysis.catalog_loader import get_catalog_organization_rules


def _sample_candidate(
    cand_id: str = "cand-1",
    decisions: list[DecisionRecord] | None = None,
) -> DesignCandidate:
    if decisions is None:
        decisions = [
            DecisionRecord(
                id="dec-unit",
                dimension="unit_organization",
                subject="building",
                value="grouped",
                status=DecisionStatus.DERIVED,
            ),
            DecisionRecord(
                id="dec-circ",
                dimension="vertical_circulation",
                subject="building",
                value="shared",
                status=DecisionStatus.DERIVED,
            ),
        ]
    return DesignCandidate(
        id=cand_id,
        source_strategy_id="strat-1",
        source_analysis_id="analysis-1",
        source_problem_id="prob-1",
        source_problem_version=1,
        name="Sample Candidate",
        selected_decisions=decisions,
    )


def test_1_minimal_candidate_unchanged_when_no_rules_match():
    cand = _sample_candidate(decisions=[])
    rules = [
        OrganizationRule(
            id="rule-unmatched",
            trigger_dimension="some_other_dim",
            trigger_value="other_val",
            action=OrganizationAction.GROUP_BY_ATTRIBUTE,
            target_collection="unit_organization",
            explanation="Unmatched rule",
        )
    ]
    enriched = organize_candidate(cand, rules)
    assert enriched.floor_organization == {}
    assert enriched.unit_organization == {}
    assert enriched.circulation_intent == []
    assert enriched.service_organization == []


def test_2_matching_rule_execution():
    cand = _sample_candidate()
    rule = OrganizationRule(
        id="rule-circ",
        trigger_dimension="vertical_circulation",
        trigger_value="shared",
        action=OrganizationAction.CREATE_CIRCULATION_NODE,
        target_collection="circulation_intent",
        parameters={"node_id": "circ-stair-1", "type": "vertical_stair", "access_type": "shared"},
        explanation="Create shared stair core",
    )
    enriched = organize_candidate(cand, [rule])
    assert len(enriched.circulation_intent) == 1
    assert enriched.circulation_intent[0].id == "circ-stair-1"


def test_3_non_matching_rule_safely_ignored():
    cand = _sample_candidate()
    rule = OrganizationRule(
        id="rule-ignore",
        trigger_dimension="vertical_circulation",
        trigger_value="independent",  # Candidate has "shared"
        action=OrganizationAction.CREATE_CIRCULATION_NODE,
        target_collection="circulation_intent",
        parameters={"node_id": "circ-indep"},
        explanation="Independent circ rule",
    )
    enriched = organize_candidate(cand, [rule])
    assert enriched.circulation_intent == []


def test_4_group_by_attribute_action():
    cand = _sample_candidate()
    rule = OrganizationRule(
        id="rule-group",
        trigger_dimension="unit_organization",
        trigger_value="grouped",
        action=OrganizationAction.GROUP_BY_ATTRIBUTE,
        target_collection="unit_organization",
        parameters={"attribute": "owner_id", "fallback_prefix": "unit_"},
        explanation="Group by owner_id",
    )
    problem = DesignProblem(
        id="prob-1",
        version=1,
        site=SiteDefinition(plot_width=30, plot_depth=40),
        spaces=[
            SpaceRequirement(id="space_liv", room=RoomIntent(room_type=RoomCategory.LIVING), owner_id="fam1"),
            SpaceRequirement(id="space_bed", room=RoomIntent(room_type=RoomCategory.BEDROOM), owner_id="fam2"),
        ],
    )
    enriched = organize_candidate(cand, [rule], problem=problem)
    assert enriched.unit_organization == {
        "unit_fam1": ["space_liv"],
        "unit_fam2": ["space_bed"],
    }


def test_5_assign_floor_tier_action():
    cand = _sample_candidate()
    rule = OrganizationRule(
        id="rule-floor",
        trigger_dimension="unit_organization",
        trigger_value="grouped",
        action=OrganizationAction.ASSIGN_FLOOR_TIER,
        target_collection="floor_organization",
        parameters={"tier_mapping": {"all_spaces": "floor_1"}},
        explanation="Assign all spaces to floor_1",
    )
    problem = DesignProblem(
        id="prob-1",
        version=1,
        site=SiteDefinition(plot_width=30, plot_depth=40, floors=1),
        spaces=[
            SpaceRequirement(id="space_liv", room=RoomIntent(room_type=RoomCategory.LIVING)),
        ],
    )
    enriched = organize_candidate(cand, [rule], problem=problem)
    assert enriched.floor_organization == {"floor_1": ["space_liv"]}


def test_6_create_circulation_node_action():
    cand = _sample_candidate()
    rule = OrganizationRule(
        id="rule-circ-node",
        trigger_dimension="vertical_circulation",
        trigger_value="shared",
        action=OrganizationAction.CREATE_CIRCULATION_NODE,
        target_collection="circulation_intent",
        parameters={"node_id": "core-stair", "type": "stairwell", "access_type": "shared", "target_scope": ["u1", "u2"]},
        explanation="Create stair core node",
    )
    enriched = organize_candidate(cand, [rule])
    assert len(enriched.circulation_intent) == 1
    assert enriched.circulation_intent[0].id == "core-stair"
    assert enriched.circulation_intent[0].connected_space_ids == ["u1", "u2"]


def test_7_create_service_stack_action():
    cand = DecisionRecord(
        id="dec-serv",
        dimension="service_core_strategy",
        subject="building",
        value="centralized",
        status=DecisionStatus.DERIVED,
    )
    cand_obj = _sample_candidate(decisions=[cand])
    rule = OrganizationRule(
        id="rule-service",
        trigger_dimension="service_core_strategy",
        trigger_value="centralized",
        action=OrganizationAction.CREATE_SERVICE_STACK,
        target_collection="service_organization",
        parameters={
            "stack_id": "stack-wet",
            "service_type": "plumbing_stack",
            "target_scope": "by_category",
            "categories": ["bathroom", "kitchen"],
        },
        explanation="Centralized wet core stack",
    )
    problem = DesignProblem(
        id="prob-1",
        version=1,
        site=SiteDefinition(plot_width=30, plot_depth=40),
        spaces=[
            SpaceRequirement(id="bath_1", room=RoomIntent(room_type=RoomCategory.BATHROOM)),
            SpaceRequirement(id="kit_1", room=RoomIntent(room_type=RoomCategory.KITCHEN)),
            SpaceRequirement(id="liv_1", room=RoomIntent(room_type=RoomCategory.LIVING)),
        ],
    )
    enriched = organize_candidate(cand_obj, [rule], problem=problem)
    assert len(enriched.service_organization) == 1
    assert enriched.service_organization[0].id == "stack-wet"
    assert enriched.service_organization[0].assigned_space_ids == ["bath_1", "kit_1"]


def test_8_multiple_rules_execution():
    cand = _sample_candidate()
    r1 = OrganizationRule(
        id="r-unit",
        trigger_dimension="unit_organization",
        trigger_value="grouped",
        action=OrganizationAction.GROUP_BY_ATTRIBUTE,
        target_collection="unit_organization",
        parameters={"attribute": "owner_id", "fallback_prefix": "unit_"},
        explanation="Group by unit",
    )
    r2 = OrganizationRule(
        id="r-circ",
        trigger_dimension="vertical_circulation",
        trigger_value="shared",
        action=OrganizationAction.CREATE_CIRCULATION_NODE,
        target_collection="circulation_intent",
        parameters={"node_id": "stair-core", "type": "stair"},
        explanation="Create stair node",
    )
    problem = DesignProblem(
        id="prob-1",
        version=1,
        site=SiteDefinition(plot_width=30, plot_depth=40),
        spaces=[SpaceRequirement(id="liv", room=RoomIntent(room_type=RoomCategory.LIVING), owner_id="fam1")],
    )
    enriched = organize_candidate(cand, [r1, r2], problem=problem)
    assert len(enriched.unit_organization) == 1
    assert len(enriched.circulation_intent) == 1


def test_9_rule_ordering_determinism():
    cand = _sample_candidate()
    r1 = OrganizationRule(
        id="r-a",
        trigger_dimension="unit_organization",
        trigger_value="grouped",
        action=OrganizationAction.CREATE_CIRCULATION_NODE,
        target_collection="circulation_intent",
        parameters={"node_id": "node-a"},
        explanation="Node A",
    )
    r2 = OrganizationRule(
        id="r-b",
        trigger_dimension="vertical_circulation",
        trigger_value="shared",
        action=OrganizationAction.CREATE_CIRCULATION_NODE,
        target_collection="circulation_intent",
        parameters={"node_id": "node-b"},
        explanation="Node B",
    )
    res1 = organize_candidate(cand, [r1, r2])
    res2 = organize_candidate(cand, [r2, r1])
    assert res1.model_dump_json() == res2.model_dump_json()


def test_10_custom_unseen_dimensions():
    custom_dec = DecisionRecord(
        id="dec-custom-unseen",
        dimension="brand_new_architectural_dimension",
        subject="facade",
        value="alpha",
        status=DecisionStatus.DERIVED,
    )
    cand = _sample_candidate(decisions=[custom_dec])
    rule = OrganizationRule(
        id="org-custom-test",
        trigger_dimension="brand_new_architectural_dimension",
        trigger_value="alpha",
        action=OrganizationAction.CREATE_SERVICE_STACK,
        target_collection="service_organization",
        parameters={"stack_id": "custom-stack", "service_type": "custom_service", "target_scope": ["space_1"]},
        explanation="Custom declarative organization rule",
    )
    enriched = organize_candidate(cand, [rule])
    assert len(enriched.service_organization) == 1
    assert enriched.service_organization[0].id == "custom-stack"
    assert enriched.service_organization[0].service_type == "custom_service"


def test_11_custom_trigger_values():
    dec_int = DecisionRecord(id="d1", dimension="dim_int", subject="s", value=4, status=DecisionStatus.DERIVED)
    dec_bool = DecisionRecord(id="d2", dimension="dim_bool", subject="s", value=True, status=DecisionStatus.DERIVED)
    dec_dict = DecisionRecord(id="d3", dimension="dim_dict", subject="s", value={"tier": 1}, status=DecisionStatus.DERIVED)

    cand = _sample_candidate(decisions=[dec_int, dec_bool, dec_dict])

    r_int = OrganizationRule(
        id="r-int",
        trigger_dimension="dim_int",
        trigger_value=4,
        action=OrganizationAction.CREATE_CIRCULATION_NODE,
        target_collection="circulation_intent",
        parameters={"node_id": "n-int"},
        explanation="int trigger",
    )
    r_bool = OrganizationRule(
        id="r-bool",
        trigger_dimension="dim_bool",
        trigger_value=True,
        action=OrganizationAction.CREATE_SERVICE_STACK,
        target_collection="service_organization",
        parameters={"stack_id": "s-bool", "target_scope": ["sp1"]},
        explanation="bool trigger",
    )
    r_dict = OrganizationRule(
        id="r-dict",
        trigger_dimension="dim_dict",
        trigger_value={"tier": 1},
        action=OrganizationAction.CREATE_CIRCULATION_NODE,
        target_collection="circulation_intent",
        parameters={"node_id": "n-dict"},
        explanation="dict trigger",
    )

    enriched = organize_candidate(cand, [r_int, r_bool, r_dict])
    node_ids = [n.id for n in enriched.circulation_intent]
    assert "n-int" in node_ids
    assert "n-dict" in node_ids
    assert len(enriched.service_organization) == 1


def test_12_parameter_preservation():
    cand = _sample_candidate()
    rule = OrganizationRule(
        id="r-param",
        trigger_dimension="vertical_circulation",
        trigger_value="shared",
        action=OrganizationAction.CREATE_CIRCULATION_NODE,
        target_collection="circulation_intent",
        parameters={"node_id": "node-custom", "type": "special_core", "access_type": "restricted"},
        explanation="Preserve params",
    )
    enriched = organize_candidate(cand, [rule])
    assert enriched.circulation_intent[0].type == "special_core"
    assert enriched.circulation_intent[0].access_type == "restricted"


def test_13_duplicate_id_prevention():
    cand = _sample_candidate()
    rule = OrganizationRule(
        id="r-dup",
        trigger_dimension="vertical_circulation",
        trigger_value="shared",
        action=OrganizationAction.CREATE_CIRCULATION_NODE,
        target_collection="circulation_intent",
        parameters={"node_id": "duplicate-node-id"},
        explanation="Duplicate test rule",
    )
    enriched = organize_candidate(cand, [rule, rule])
    assert len(enriched.circulation_intent) == 1
    assert enriched.circulation_intent[0].id == "duplicate-node-id"


def test_14_idempotency_repeated_execution():
    cand = _sample_candidate()
    rules = get_catalog_organization_rules()
    problem = DesignProblem(
        id="prob-1",
        version=1,
        site=SiteDefinition(plot_width=30, plot_depth=40, floors=2),
        spaces=[
            SpaceRequirement(id="liv", room=RoomIntent(room_type=RoomCategory.LIVING), owner_id="fam1"),
            SpaceRequirement(id="bath", room=RoomIntent(room_type=RoomCategory.BATHROOM), owner_id="fam1"),
        ],
    )
    run1 = organize_candidate(cand, rules, problem=problem)
    run2 = organize_candidate(run1, rules, problem=problem)
    assert run1.model_dump_json() == run2.model_dump_json()


def test_15_provenance_preservation():
    cand = _sample_candidate()
    rule = OrganizationRule(
        id="r-prov",
        trigger_dimension="vertical_circulation",
        trigger_value="shared",
        action=OrganizationAction.CREATE_CIRCULATION_NODE,
        target_collection="circulation_intent",
        parameters={"node_id": "n1"},
        explanation="Prov test",
    )
    enriched = organize_candidate(cand, [rule])
    assert enriched.provenance["organizer"] == "generic-data-driven-organizer"
    assert "r-prov" in enriched.provenance["matched_rule_ids"]


def test_16_no_geometry():
    cand = _sample_candidate()
    rules = get_catalog_organization_rules()
    enriched = organize_candidate(cand, rules)
    cand_dict = enriched.model_dump()
    prohibited = {"coordinates", "polygon", "rectangle", "bounding_box", "x", "y", "z", "wall", "door", "window", "mesh", "cad"}
    for key in cand_dict.keys():
        assert key.lower() not in prohibited


def test_17_no_solver_invocation():
    import app.services.analysis.candidate_organizer as co_mod
    mod_dict = dir(co_mod)
    assert "solve_layout" not in mod_dict
    assert "PuLP" not in mod_dict
    assert "CBC" not in mod_dict
    assert "compile_blueprint" not in mod_dict


def test_18_benchmark_fixture_abstract_organization():
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
            SpaceRequirement(id="liv_1", room=RoomIntent(room_type=RoomCategory.LIVING), owner_id="fam1"),
            SpaceRequirement(id="bath_1", room=RoomIntent(room_type=RoomCategory.BATHROOM), owner_id="fam1"),
            SpaceRequirement(id="liv_2", room=RoomIntent(room_type=RoomCategory.LIVING), owner_id="fam2"),
            SpaceRequirement(id="bath_2", room=RoomIntent(room_type=RoomCategory.BATHROOM), owner_id="fam2"),
        ],
    )
    decisions = [
        DecisionRecord(id="d1", dimension="unit_organization", subject="building", value="grouped", status=DecisionStatus.DERIVED),
        DecisionRecord(id="d2", dimension="vertical_circulation", subject="building", value="shared", status=DecisionStatus.DERIVED),
        DecisionRecord(id="d3", dimension="service_core_strategy", subject="building", value="centralized", status=DecisionStatus.DERIVED),
    ]
    cand = _sample_candidate("cand-44x42", decisions=decisions)
    rules = get_catalog_organization_rules()

    enriched = organize_candidate(cand, rules, problem=problem)

    assert "unit_fam1" in enriched.unit_organization
    assert "unit_fam2" in enriched.unit_organization
    assert len(enriched.circulation_intent) == 1
    assert enriched.circulation_intent[0].id == "circ-shared-vertical-core"
    assert len(enriched.service_organization) == 1
    assert enriched.service_organization[0].id == "stack-central-wet-core"


def test_19_single_family_fixture_abstract_organization():
    problem = DesignProblem(
        id="prob-single-family",
        version=1,
        site=SiteDefinition(plot_width=30.0, plot_depth=40.0, floors=1),
        spaces=[
            SpaceRequirement(id="liv", room=RoomIntent(room_type=RoomCategory.LIVING), owner_id="fam_single"),
            SpaceRequirement(id="kit", room=RoomIntent(room_type=RoomCategory.KITCHEN), owner_id="fam_single"),
        ],
    )
    decisions = [
        DecisionRecord(id="d1", dimension="unit_organization", subject="building", value="grouped", status=DecisionStatus.DERIVED),
        DecisionRecord(id="d2", dimension="floor_allocation", subject="building", value="ground_floor_only", status=DecisionStatus.DERIVED),
    ]
    cand = _sample_candidate("cand-single", decisions=decisions)
    rules = get_catalog_organization_rules()

    enriched = organize_candidate(cand, rules, problem=problem)

    assert sorted(enriched.unit_organization["unit_fam_single"]) == ["kit", "liv"]
    assert sorted(enriched.floor_organization["floor_1"]) == ["kit", "liv"]


def test_20_malformed_rule_handling():
    cand = _sample_candidate()
    invalid_rule_dict = {
        "id": "r-invalid-action",
        "trigger_dimension": "vertical_circulation",
        "trigger_value": "shared",
        "action": "INVALID_UNSUPPORTED_ACTION",
        "target_collection": "unit_organization",
        "explanation": "Bad action rule",
    }
    with pytest.raises(ValueError):
        OrganizationRule.model_validate(invalid_rule_dict)


def test_21_space_with_non_dict_metadata():
    """Verify space objects with metadata set to generic object or missing metadata don't crash with AttributeError."""
    cand = _sample_candidate()
    rule = OrganizationRule(
        id="rule-group-meta",
        trigger_dimension="unit_organization",
        trigger_value="grouped",
        action=OrganizationAction.GROUP_BY_ATTRIBUTE,
        target_collection="unit_organization",
        parameters={"attribute": "custom_attr", "fallback_prefix": "unit_"},
        explanation="Group by custom attribute",
    )
    
    class DummySpace:
        def __init__(self, space_id: str, metadata: object):
            self.id = space_id
            self.metadata = metadata

    dummy_problem = DesignProblem(
        id="prob-dummy",
        version=1,
        site=SiteDefinition(plot_width=30, plot_depth=40),
        spaces=[
            SpaceRequirement(id="space_1", room=RoomIntent(room_type=RoomCategory.LIVING)),
        ],
    )
    # Inject dummy space with object() metadata (cast to Any for static type checker)
    dummy_problem.spaces.append(cast(Any, DummySpace("space_2", object())))

    enriched = organize_candidate(cand, [rule], problem=dummy_problem)
    assert "unit_default" in enriched.unit_organization
    assert "space_1" in enriched.unit_organization["unit_default"]
    assert "space_2" in enriched.unit_organization["unit_default"]


def test_22_candidate_organizer_contains_no_legacy_domain_branching():
    """Verify via AST inspection that candidate_organizer.py contains zero hardcoded domain branches."""
    import ast
    from pathlib import Path

    organizer_file = Path(__file__).parent.parent / "app" / "services" / "analysis" / "candidate_organizer.py"
    assert organizer_file.exists()

    with open(organizer_file, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(organizer_file))

    forbidden_strings = {
        "vertical_circulation",
        "unit_organization",
        "service_core_strategy",
        "floor_allocation",
        "shared",
        "independent",
        "hybrid",
    }

    class BranchVisitor(ast.NodeVisitor):
        def __init__(self):
            self.violations: list[str] = []

        def visit_Compare(self, node: ast.Compare):
            for child in ast.walk(node):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    if child.value in forbidden_strings:
                        self.violations.append(f"Hardcoded domain string in AST comparison line {node.lineno}: '{child.value}'")
            self.generic_visit(node)

    visitor = BranchVisitor()
    visitor.visit(tree)

    assert not visitor.violations, f"Found domain-specific branches in candidate_organizer.py: {visitor.violations}"


