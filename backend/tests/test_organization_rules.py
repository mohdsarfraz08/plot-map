import json
import pytest
from pydantic import ValidationError

from app.schemas.architectural_analysis import (
    ArchitecturalAnalysis,
    DecisionDimension,
    OrganizationAction,
    OrganizationRule,
)
from app.services.analysis.catalog_loader import (
    get_catalog_organization_rules,
    load_decision_catalog,
)


def test_organization_action_enum_values():
    assert OrganizationAction.GROUP_BY_ATTRIBUTE.value == "group_by_attribute"
    assert OrganizationAction.ASSIGN_FLOOR_TIER.value == "assign_floor_tier"
    assert OrganizationAction.CREATE_CIRCULATION_NODE.value == "create_circulation_node"
    assert OrganizationAction.CREATE_SERVICE_STACK.value == "create_service_stack"


def test_minimal_organization_rule():
    rule = OrganizationRule(
        id="org-rule-1",
        trigger_dimension=DecisionDimension.VERTICAL_CIRCULATION,
        trigger_value="shared",
        action=OrganizationAction.CREATE_CIRCULATION_NODE,
        target_collection="circulation_intent",
        explanation="Shared stair core rule",
    )
    assert rule.id == "org-rule-1"
    assert rule.action == OrganizationAction.CREATE_CIRCULATION_NODE
    assert rule.target_collection == "circulation_intent"
    assert rule.parameters == {}


def test_unseen_custom_trigger_dimension():
    # Critical generality test: unseen dimension brand_new_architectural_dimension
    rule = OrganizationRule(
        id="org-custom-test",
        trigger_dimension="brand_new_architectural_dimension",
        trigger_value="alpha",
        action=OrganizationAction.CREATE_SERVICE_STACK,
        target_collection="service_organization",
        parameters={
            "stack_id": "custom-stack",
            "service_type": "custom_service",
            "target_scope": "custom_scope",
        },
        explanation="Custom declarative organization rule.",
    )
    assert rule.trigger_dimension == "brand_new_architectural_dimension"
    assert rule.trigger_value == "alpha"
    assert rule.parameters["stack_id"] == "custom-stack"


def test_trigger_value_types():
    # Test string, numeric, boolean, and structured dict trigger values
    r_str = OrganizationRule(
        id="r-str",
        trigger_dimension="dim_a",
        trigger_value="shared",
        action=OrganizationAction.GROUP_BY_ATTRIBUTE,
        target_collection="unit_organization",
        explanation="string trigger",
    )
    assert r_str.trigger_value == "shared"

    r_num = OrganizationRule(
        id="r-num",
        trigger_dimension="dim_b",
        trigger_value=4,
        action=OrganizationAction.ASSIGN_FLOOR_TIER,
        target_collection="floor_organization",
        explanation="numeric trigger",
    )
    assert r_num.trigger_value == 4

    r_bool = OrganizationRule(
        id="r-bool",
        trigger_dimension="dim_c",
        trigger_value=True,
        action=OrganizationAction.CREATE_SERVICE_STACK,
        target_collection="service_organization",
        explanation="boolean trigger",
    )
    assert r_bool.trigger_value is True

    r_dict = OrganizationRule(
        id="r-dict",
        trigger_dimension="dim_d",
        trigger_value={"tier": 1, "active": True},
        action=OrganizationAction.CREATE_CIRCULATION_NODE,
        target_collection="circulation_intent",
        explanation="dict trigger",
    )
    assert r_dict.trigger_value == {"tier": 1, "active": True}


def test_parameter_serialization_and_non_serializable_rejection():
    class CustomNonSerializable:
        pass

    with pytest.raises(ValidationError):
        OrganizationRule(
            id="r-invalid-param",
            trigger_dimension="dim_a",
            trigger_value="val",
            action=OrganizationAction.GROUP_BY_ATTRIBUTE,
            target_collection="unit_organization",
            parameters={"invalid_obj": CustomNonSerializable()},
            explanation="Invalid non-serializable param",
        )


def test_non_geometric_boundary_rejection():
    with pytest.raises(ValidationError):
        OrganizationRule(
            id="r-geom-fail",
            trigger_dimension="dim_a",
            trigger_value="val",
            action=OrganizationAction.GROUP_BY_ATTRIBUTE,
            target_collection="unit_organization",
            parameters={"coordinates": [0, 0, 10, 10]},  # Prohibited geometric key
            explanation="Prohibited geometric parameter",
        )

    with pytest.raises(ValidationError):
        OrganizationRule(
            id="r-geom-fail-2",
            trigger_dimension="dim_a",
            trigger_value={"polygon": "0 0, 10 10"},  # Prohibited geometric key in trigger_value
            action=OrganizationAction.ASSIGN_FLOOR_TIER,
            target_collection="floor_organization",
            explanation="Prohibited geometric trigger_value",
        )


def test_duplicate_organization_rule_id_validation():
    r1 = OrganizationRule(
        id="dup-rule-id",
        trigger_dimension="dim_1",
        trigger_value="val_1",
        action=OrganizationAction.GROUP_BY_ATTRIBUTE,
        target_collection="unit_organization",
        explanation="rule 1",
    )
    r2 = OrganizationRule(
        id="dup-rule-id",
        trigger_dimension="dim_2",
        trigger_value="val_2",
        action=OrganizationAction.ASSIGN_FLOOR_TIER,
        target_collection="floor_organization",
        explanation="rule 2",
    )

    with pytest.raises(ValidationError) as exc_info:
        ArchitecturalAnalysis(
            problem_id="prob-dup",
            problem_version=1,
            summary="Duplicate rule ID analysis",
            organization_rules=[r1, r2],
        )
    assert "organization_rules" in str(exc_info.value) or "IDs must be unique" in str(exc_info.value)


def test_architectural_analysis_backward_compatibility():
    analysis = ArchitecturalAnalysis(
        problem_id="prob-compat",
        problem_version=1,
        summary="Backward compatibility test",
    )
    assert analysis.organization_rules == []


def test_catalog_loader_get_organization_rules():
    catalog_data = load_decision_catalog()
    rules = get_catalog_organization_rules(catalog_data)
    assert isinstance(rules, list)
    assert len(rules) >= 4
    rule_ids = [r.id for r in rules]
    assert "org-unit-grouped" in rule_ids
    assert "org-circ-shared-vertical" in rule_ids


def test_malformed_catalog_organization_rules():
    malformed_catalog = {
        "organization_rules": [
            {
                "id": "org-bad-action",
                "trigger_dimension": "dim_a",
                "trigger_value": "val",
                "action": "INVALID_ACTION_NAME",
                "target_collection": "unit_organization",
                "explanation": "Bad action rule",
            }
        ]
    }
    with pytest.raises(ValueError) as exc_info:
        get_catalog_organization_rules(malformed_catalog)
    assert "Invalid OrganizationAction" in str(exc_info.value)


def test_missing_organization_rules_behavior():
    empty_catalog = {"dimensions": {}}
    rules = get_catalog_organization_rules(empty_catalog)
    assert rules == []


def test_json_round_trip_and_deterministic_serialization():
    rule = OrganizationRule(
        id="org-rt-1",
        trigger_dimension=DecisionDimension.SERVICE_CORE_STRATEGY,
        trigger_value="centralized",
        action=OrganizationAction.CREATE_SERVICE_STACK,
        target_collection="service_organization",
        parameters={"stack_id": "wet-core", "service_type": "plumbing"},
        explanation="Centralized wet core stack",
    )
    json_str = rule.model_dump_json()
    reconstructed = OrganizationRule.model_validate_json(json_str)

    assert reconstructed.id == rule.id
    assert reconstructed.trigger_dimension == rule.trigger_dimension
    assert reconstructed.action == rule.action
    assert reconstructed.parameters == rule.parameters
    assert reconstructed.model_dump_json() == json_str
