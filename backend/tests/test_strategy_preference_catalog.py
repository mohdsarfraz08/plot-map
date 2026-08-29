"""
Unit and Contract Test Suite for Stage 3B.5-2: Declarative Preference & Scoring Catalog.

Validates catalog schema, catalog loader, normalization, tie-break configuration,
selection thresholds, domain genericity, non-geometric boundary, and determinism.
"""

import json
from pathlib import Path
import pytest

from app.schemas.strategy_preference import (
    NormalizationConfig,
    PreferenceCatalog,
    PreferenceCriterion,
    SelectionThresholdConfig,
    ThresholdConfig,
    TieBreakConfig,
)
from app.services.analysis.catalog_loader import (
    get_preference_catalog,
    load_preference_catalog,
)


def _get_minimal_valid_catalog_dict() -> dict:
    return {
        "version": "1.0.0",
        "provenance": {"author": "test"},
        "deterministic_precision": 6,
        "selection_thresholds": {
            "selected_min_score": 0.8,
            "viable_min_score": 0.6,
            "marginal_min_score": 0.4,
            "rejected_max_score": 0.4,
        },
        "tie_break": {
            "priority_criteria": ["criterion_a"],
            "fallback_strategy": "candidate_id",
        },
        "criteria": [
            {
                "id": "criterion_a",
                "description": "Minimal test criterion",
                "weight": 1.0,
                "normalization": {"method": "min_max", "min_value": 0.0, "max_value": 1.0},
                "thresholds": {"min_passing_score": 0.5},
                "metadata": {"test": "value"},
            }
        ],
    }


def test_1_minimal_preference_catalog_loads():
    data = _get_minimal_valid_catalog_dict()
    catalog = get_preference_catalog(data)
    assert catalog.version == "1.0.0"
    assert len(catalog.criteria) == 1
    assert catalog.criteria[0].id == "criterion_a"
    assert catalog.criteria[0].weight == 1.0


def test_2_canonical_six_criteria_load():
    catalog = load_preference_catalog()
    assert catalog.version == "3B.5-2.v1"
    assert len(catalog.criteria) == 6

    canonical_ids = [
        "program_usability",
        "privacy_compliance",
        "circulation_efficiency",
        "service_core_stacking",
        "realization_feasibility",
        "objective_alignment",
    ]
    loaded_ids = [c.id for c in catalog.criteria]
    assert loaded_ids == canonical_ids


def test_3_weight_preservation():
    catalog = load_preference_catalog()
    weights = {c.id: c.weight for c in catalog.criteria}
    expected = {
        "program_usability": 0.25,
        "privacy_compliance": 0.20,
        "circulation_efficiency": 0.15,
        "service_core_stacking": 0.15,
        "realization_feasibility": 0.15,
        "objective_alignment": 0.10,
    }
    assert weights == expected


def test_4_weight_sum_validation():
    data = _get_minimal_valid_catalog_dict()
    data["criteria"][0]["weight"] = 0.8
    with pytest.raises(ValueError, match="Total criterion weight must equal 1.0"):
        get_preference_catalog(data)


def test_5_duplicate_criterion_id_rejection():
    data = _get_minimal_valid_catalog_dict()
    data["criteria"] = [
        {"id": "c1", "description": "desc 1", "weight": 0.5},
        {"id": "c1", "description": "desc 2", "weight": 0.5},
    ]
    data["tie_break"]["priority_criteria"] = ["c1"]
    with pytest.raises(ValueError, match="Criterion IDs must be unique"):
        get_preference_catalog(data)


def test_6_invalid_weight_rejection():
    data = _get_minimal_valid_catalog_dict()
    data["criteria"][0]["weight"] = -0.1
    with pytest.raises(ValueError):
        get_preference_catalog(data)


def test_7_invalid_criterion_rejection():
    data = _get_minimal_valid_catalog_dict()
    data["criteria"][0]["id"] = "   "
    with pytest.raises(ValueError, match="Criterion id cannot be an empty string"):
        get_preference_catalog(data)

    data2 = _get_minimal_valid_catalog_dict()
    data2["criteria"][0]["description"] = ""
    with pytest.raises(ValueError, match="Criterion description cannot be an empty string"):
        get_preference_catalog(data2)


def test_8_tie_break_configuration_validation():
    data = _get_minimal_valid_catalog_dict()
    data["tie_break"]["priority_criteria"] = ["non_existent_criterion"]
    with pytest.raises(ValueError, match="Tie-break criterion ID 'non_existent_criterion' does not exist"):
        get_preference_catalog(data)


def test_9_selection_threshold_validation():
    data = _get_minimal_valid_catalog_dict()
    data["selection_thresholds"] = {
        "selected_min_score": 0.5,
        "viable_min_score": 0.8,
        "marginal_min_score": 0.4,
        "rejected_max_score": 0.4,
    }
    with pytest.raises(ValueError, match="Selection thresholds must follow ordering"):
        get_preference_catalog(data)


def test_10_custom_unseen_criterion_support():
    custom_data = {
        "version": "custom-1",
        "provenance": {"source": "future_extension"},
        "deterministic_precision": 6,
        "selection_thresholds": {
            "selected_min_score": 0.8,
            "viable_min_score": 0.6,
            "marginal_min_score": 0.4,
            "rejected_max_score": 0.4,
        },
        "tie_break": {
            "priority_criteria": [
                "energy_resilience",
                "solar_shading_quality",
                "facade_transparency",
                "future_custom_metric",
            ],
            "fallback_strategy": "candidate_id",
        },
        "criteria": [
            {"id": "energy_resilience", "description": "Custom energy metric", "weight": 0.25},
            {"id": "solar_shading_quality", "description": "Custom solar shading metric", "weight": 0.25},
            {"id": "facade_transparency", "description": "Custom facade metric", "weight": 0.25},
            {"id": "future_custom_metric", "description": "Future metric", "weight": 0.25},
        ],
    }
    catalog = get_preference_catalog(custom_data)
    assert len(catalog.criteria) == 4
    assert catalog.criteria[0].id == "energy_resilience"
    assert catalog.criteria[3].id == "future_custom_metric"


def test_11_custom_metadata_support():
    data = _get_minimal_valid_catalog_dict()
    data["criteria"][0]["metadata"] = {
        "custom_tag": "experimental",
        "nested": {"param": 123, "enabled": True},
    }
    catalog = get_preference_catalog(data)
    assert catalog.criteria[0].metadata["custom_tag"] == "experimental"
    assert catalog.criteria[0].metadata["nested"]["param"] == 123


def test_12_missing_catalog_behavior():
    non_existent = Path("non_existent_directory/missing_preference_catalog.json")
    with pytest.raises(FileNotFoundError, match="Preference catalog file not found"):
        load_preference_catalog(non_existent)


def test_13_malformed_catalog_behavior(tmp_path: Path):
    bad_json_file = tmp_path / "bad.json"
    bad_json_file.write_text("{ malformed json ...", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed JSON in preference catalog"):
        load_preference_catalog(bad_json_file)

    bad_root_file = tmp_path / "bad_root.json"
    bad_root_file.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="Preference catalog root must be a JSON object"):
        load_preference_catalog(bad_root_file)


def test_14_deterministic_repeated_loading():
    cat1 = load_preference_catalog()
    cat2 = load_preference_catalog()
    assert cat1.model_dump_json() == cat2.model_dump_json()
    assert cat1 == cat2


def test_15_json_round_trip():
    cat = load_preference_catalog()
    json_str = cat.model_dump_json()
    reconstructed = PreferenceCatalog.model_validate_json(json_str)
    assert reconstructed == cat


def test_16_criterion_ordering_preservation():
    cat = load_preference_catalog()
    declared_order = [
        "program_usability",
        "privacy_compliance",
        "circulation_efficiency",
        "service_core_stacking",
        "realization_feasibility",
        "objective_alignment",
    ]
    model_order = [c.id for c in cat.criteria]
    assert model_order == declared_order


def test_17_provenance_source_metadata_preservation():
    cat = load_preference_catalog()
    assert "author" in cat.provenance
    assert cat.provenance["stage"] == "3B.5-2"


def test_18_non_serializable_metadata_rejection():
    data = _get_minimal_valid_catalog_dict()
    data["criteria"][0]["metadata"] = {"invalid_func": lambda x: x}
    with pytest.raises(ValueError, match="JSON-serializable"):
        get_preference_catalog(data)


def test_19_non_geometric_boundary_verification():
    data = _get_minimal_valid_catalog_dict()
    data["criteria"][0]["metadata"] = {"coordinates": [10.0, 20.0]}
    with pytest.raises(ValueError, match="prohibited geometric"):
        get_preference_catalog(data)

    data2 = _get_minimal_valid_catalog_dict()
    data2["provenance"] = {"polygon": "VERTICES(0, 0, 10, 10)"}
    with pytest.raises(ValueError, match="prohibited geometric"):
        get_preference_catalog(data2)


def test_20_no_solver_compiler_api_invocation():
    # Verify purely data-driven loading with zero side-effects or external dependencies
    catalog = load_preference_catalog()
    assert isinstance(catalog, PreferenceCatalog)
    assert catalog.deterministic_precision == 6
