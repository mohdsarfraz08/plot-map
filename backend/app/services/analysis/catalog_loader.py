"""
Catalog loader module for Stage 3B.3C-2.

Loads and parses declarative architectural decision catalog data from JSON files.
Purely data-driven; no network calls, no LLMs, no hardcoded domain logic.
"""

import json
from pathlib import Path
from typing import Any

from app.schemas.architectural_analysis import (
    AnalysisSeverity,
    DecisionDimension,
    DimensionRelationship,
    IncompatibilityRule,
    OrganizationAction,
    OrganizationRule,
    RelationshipImpact,
)

_DEFAULT_CATALOG_PATH = Path(__file__).parent / "decision_catalog.json"


def _dim_to_str(dim: Any) -> str:
    if hasattr(dim, "value"):
        return str(dim.value)
    return str(dim)


def load_decision_catalog(catalog_path: str | Path | None = None) -> dict[str, Any]:
    """
    Load, parse, and validate declarative decision catalog from JSON file.
    Raises FileNotFoundError if missing, ValueError if malformed.
    """
    target_path = Path(catalog_path) if catalog_path else _DEFAULT_CATALOG_PATH

    if not target_path.exists():
        raise FileNotFoundError(f"Decision catalog file not found at: {target_path}")

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as err:
        raise ValueError(f"Malformed JSON in decision catalog '{target_path}': {err}") from err

    if not isinstance(data, dict):
        raise ValueError(f"Decision catalog root must be a JSON object, got {type(data).__name__}")

    if "dimensions" in data and not isinstance(data["dimensions"], dict):
        raise ValueError("Decision catalog 'dimensions' key must be a JSON object")

    return data


def get_catalog_alternatives(
    dimension: str | DecisionDimension,
    catalog: dict[str, Any] | None = None,
) -> list[Any]:
    """
    Retrieve list of candidate alternatives for a given dimension from catalog.
    Returns empty list if dimension is unknown or not present in catalog.
    """
    if catalog is None:
        catalog = load_decision_catalog()

    dim_str = _dim_to_str(dimension)
    dimensions_map = catalog.get("dimensions", {})

    if dim_str in dimensions_map and isinstance(dimensions_map[dim_str], dict):
        alts = dimensions_map[dim_str].get("alternatives", [])
        if isinstance(alts, list):
            return list(alts)

    return []


def get_catalog_incompatibilities(
    catalog: dict[str, Any] | None = None,
) -> list[IncompatibilityRule]:
    """Extract validated IncompatibilityRule objects declared in decision catalog."""
    if catalog is None:
        catalog = load_decision_catalog()

    rules: list[IncompatibilityRule] = []
    raw_list = catalog.get("incompatibilities", [])
    if not isinstance(raw_list, list):
        return rules

    for raw in raw_list:
        if isinstance(raw, dict):
            rules.append(
                IncompatibilityRule(
                    id=str(raw.get("id", f"incompat-{len(rules)+1}")),
                    dimension_a=str(raw["dimension_a"]),
                    value_a=raw["value_a"],
                    dimension_b=str(raw["dimension_b"]),
                    value_b=raw["value_b"],
                    explanation=str(raw.get("explanation", "")),
                    source_ids=list(raw.get("source_ids", [])),
                )
            )

    return rules


def get_catalog_relationships(
    catalog: dict[str, Any] | None = None,
) -> list[DimensionRelationship]:
    """Extract validated DimensionRelationship objects declared in decision catalog."""
    if catalog is None:
        catalog = load_decision_catalog()

    relationships: list[DimensionRelationship] = []
    raw_list = catalog.get("relationships", [])
    if not isinstance(raw_list, list):
        return relationships

    for raw in raw_list:
        if isinstance(raw, dict):
            impact_val = RelationshipImpact(str(raw.get("impact", "improves")))
            severity_val = AnalysisSeverity(str(raw.get("severity", "info")))
            relationships.append(
                DimensionRelationship(
                    id=str(raw.get("id", f"rel-{len(relationships)+1}")),
                    source_dimension=str(raw["source_dimension"]),
                    source_value=raw["source_value"],
                    target=str(raw["target"]),
                    impact=impact_val,
                    explanation=str(raw.get("explanation", "")),
                    severity=severity_val,
                    source_ids=list(raw.get("source_ids", [])),
                )
            )

    return relationships


def get_catalog_organization_rules(
    catalog: dict[str, Any] | None = None,
) -> list[OrganizationRule]:
    """Extract validated OrganizationRule objects declared in decision catalog."""
    if catalog is None:
        catalog = load_decision_catalog()

    rules: list[OrganizationRule] = []
    raw_list = catalog.get("organization_rules", [])
    if not isinstance(raw_list, list):
        return rules

    for raw in raw_list:
        if isinstance(raw, dict):
            try:
                action_val = OrganizationAction(str(raw["action"]))
            except (KeyError, ValueError) as err:
                raise ValueError(f"Invalid OrganizationAction in catalog rule '{raw.get('id')}': {err}") from err

            rules.append(
                OrganizationRule(
                    id=str(raw.get("id", f"org-rule-{len(rules)+1}")),
                    trigger_dimension=str(raw["trigger_dimension"]),
                    trigger_value=raw["trigger_value"],
                    action=action_val,
                    target_collection=str(raw["target_collection"]),
                    parameters=dict(raw.get("parameters", {})),
                    explanation=str(raw.get("explanation", "")),
                    source_ids=list(raw.get("source_ids", [])),
                )
            )

    return rules

