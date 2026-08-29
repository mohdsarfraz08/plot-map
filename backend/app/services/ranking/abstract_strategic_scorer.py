"""
Abstract Strategic Scorer for Stage 3B.5-3.

Evaluates DesignCandidate objects against DesignProblem specifications and declarative
PreferenceCatalog definitions strictly BEFORE 2D spatial layout realization.

STRICT NON-GEOMETRIC BOUNDARY:
MUST NOT contain Shapely objects, X/Y coordinates, bounding box tuples, polygon vertices,
renderer/solver engine instances, network calls, or LLM integrations.
"""

import math
from typing import Any, Callable

from app.schemas.design_candidate import DesignCandidate
from app.schemas.design_problem import DesignProblem
from app.schemas.strategy_preference import (
    PreferenceCatalog,
    PreferenceCriterion,
)
from app.schemas.strategy_ranking import (
    CriterionScore,
    RankedCandidate,
    ScoreBreakdown,
    SelectionStatus,
)
from app.services.analysis.catalog_loader import get_preference_catalog


def _clamp(val: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(val)))


def _normalize(val: float, criterion: PreferenceCriterion) -> float:
    norm = criterion.normalization
    min_v = norm.min_value if norm.min_value is not None else 0.0
    max_v = norm.max_value if norm.max_value is not None else 1.0
    if math.isclose(max_v, min_v):
        score = 1.0
    else:
        score = (val - min_v) / (max_v - min_v)
    score = _clamp(score, 0.0, 1.0)
    if norm.invert:
        score = 1.0 - score
    return score


def _eval_functional(
    candidate: DesignCandidate, problem: DesignProblem, criterion: PreferenceCriterion
) -> tuple[float, str, list[str]]:
    total_spaces = len(problem.spaces)
    if not total_spaces:
        total_spaces = sum(len(g.spaces) for g in problem.user_groups)

    allocated_spaces: set[str] = set()
    for space_list in candidate.floor_organization.values():
        if isinstance(space_list, list):
            allocated_spaces.update(str(s) for s in space_list)
    for space_list in candidate.unit_organization.values():
        if isinstance(space_list, list):
            allocated_spaces.update(str(s) for s in space_list)

    if total_spaces > 0:
        coverage = len(allocated_spaces) / total_spaces
    else:
        coverage = 1.0 if candidate.selected_decisions else 0.5

    raw_score = _clamp(coverage, 0.0, 1.0)
    final_score = _normalize(raw_score, criterion)
    source_ids = [s.id for s in problem.spaces if s.id] or [r.id for r in problem.requirements if r.id]
    explanation = f"Evaluated program usability: allocated {len(allocated_spaces)} spaces vs total required spaces."
    return final_score, explanation, source_ids


def _eval_zoning(
    candidate: DesignCandidate, problem: DesignProblem, criterion: PreferenceCriterion
) -> tuple[float, str, list[str]]:
    privacy_reqs = [r for r in problem.requirements if getattr(r, "kind", None) == "privacy"]
    source_ids = [r.id for r in privacy_reqs if r.id]

    if not privacy_reqs:
        raw_score = 0.85
        explanation = "Evaluated privacy compliance: no explicit privacy requirements, baseline compliance applied."
    else:
        unresolved_ids = {d.id for d in candidate.unresolved_decisions}
        conflicts = sum(1 for r in privacy_reqs if any(c_id in unresolved_ids for c_id in r.conflicts_with))
        raw_score = _clamp(1.0 - (conflicts / len(privacy_reqs)), 0.0, 1.0)
        explanation = f"Evaluated privacy compliance: {len(privacy_reqs) - conflicts}/{len(privacy_reqs)} privacy requirements satisfied."

    final_score = _normalize(raw_score, criterion)
    return final_score, explanation, source_ids


def _eval_circulation(
    candidate: DesignCandidate, problem: DesignProblem, criterion: PreferenceCriterion
) -> tuple[float, str, list[str]]:
    nodes = candidate.circulation_intent
    source_ids = [n.id for n in nodes if n.id]

    if not nodes:
        raw_score = 0.5
        explanation = "Evaluated circulation efficiency: no explicit circulation nodes declared, baseline applied."
    else:
        connected_spaces = set()
        for n in nodes:
            connected_spaces.update(n.connected_space_ids)
        total_req_spaces = max(1, len(problem.spaces))
        ratio = len(connected_spaces) / total_req_spaces
        raw_score = _clamp(0.5 + (0.5 * min(ratio, 1.0)), 0.0, 1.0)
        explanation = f"Evaluated circulation efficiency: {len(nodes)} circulation nodes connecting {len(connected_spaces)} spaces."

    final_score = _normalize(raw_score, criterion)
    return final_score, explanation, source_ids


def _eval_infrastructure(
    candidate: DesignCandidate, problem: DesignProblem, criterion: PreferenceCriterion
) -> tuple[float, str, list[str]]:
    stacks = candidate.service_organization
    source_ids = [s.id for s in stacks if s.id]

    if not stacks:
        raw_score = 0.5
        explanation = "Evaluated service core stacking: no explicit service stacks declared, baseline applied."
    else:
        assigned_spaces = set()
        for s in stacks:
            assigned_spaces.update(s.assigned_space_ids)
        raw_score = _clamp(0.6 + (0.4 * (1.0 if assigned_spaces else 0.5)), 0.0, 1.0)
        explanation = f"Evaluated service core stacking: {len(stacks)} service stacks serving {len(assigned_spaces)} spaces."

    final_score = _normalize(raw_score, criterion)
    return final_score, explanation, source_ids


def _eval_constructability(
    candidate: DesignCandidate, problem: DesignProblem, criterion: PreferenceCriterion
) -> tuple[float, str, list[str]]:
    exp_str = str(getattr(candidate.feasibility_expectation, "value", candidate.feasibility_expectation)).lower()
    base_map = {
        "expected_feasible": 1.0,
        "conditionally_feasible": 0.75,
        "uncertain": 0.4,
        "blocked": 0.0,
        "not_evaluated": 0.5,
    }
    base_val = base_map.get(exp_str, 0.5)

    unresolved_penalty = len(candidate.unresolved_decisions) * 0.05
    risk_penalty = sum(0.1 if getattr(r, "severity", None) == "high" else 0.04 for r in candidate.risks)
    conf_factor = candidate.confidence if candidate.confidence is not None else 1.0

    raw_score = _clamp((base_val - unresolved_penalty - risk_penalty) * conf_factor, 0.0, 1.0)
    final_score = _normalize(raw_score, criterion)

    source_ids = [d.id for d in candidate.unresolved_decisions if d.id] + [r.id for r in candidate.risks if getattr(r, "id", None)]
    explanation = (
        f"Evaluated realization feasibility: expectation '{exp_str}', "
        f"{len(candidate.unresolved_decisions)} unresolved decisions, {len(candidate.risks)} risks."
    )
    return final_score, explanation, source_ids


def _eval_intent(
    candidate: DesignCandidate, problem: DesignProblem, criterion: PreferenceCriterion
) -> tuple[float, str, list[str]]:
    objectives = problem.objectives
    preferences = problem.preferences
    source_ids = [o.id for o in objectives if o.id] + [p.id for p in preferences if p.id]

    if not objectives and not preferences:
        raw_score = 0.85
        explanation = "Evaluated objective alignment: no explicit objectives or preferences, baseline applied."
    else:
        matched = len(candidate.selected_decisions)
        total_items = max(1, len(objectives) + len(preferences))
        raw_score = _clamp(0.5 + 0.5 * min(matched / total_items, 1.0), 0.0, 1.0)
        explanation = f"Evaluated objective alignment: aligned with {len(objectives)} objectives and {len(preferences)} preferences."

    final_score = _normalize(raw_score, criterion)
    return final_score, explanation, source_ids


def _eval_generic_custom(
    candidate: DesignCandidate, problem: DesignProblem, criterion: PreferenceCriterion
) -> tuple[float, str, list[str]]:
    # Search for explicit decision or metadata matching criterion ID or metadata
    crit_id = criterion.id
    raw_val = None
    source_ids = []

    # Check candidate metadata / provenance
    if isinstance(candidate.provenance, dict) and crit_id in candidate.provenance:
        try:
            raw_val = float(candidate.provenance[crit_id])
            source_ids.append("candidate_provenance")
        except (ValueError, TypeError):
            pass

    # Check selected decisions
    if raw_val is None:
        for dec in candidate.selected_decisions:
            if getattr(dec, "dimension", None) == crit_id or getattr(dec, "id", None) == crit_id:
                raw_val = 0.9
                source_ids.append(dec.id)
                break

    if raw_val is None:
        raw_val = 0.75
        source_ids.append(crit_id)

    final_score = _normalize(raw_val, criterion)
    explanation = f"Evaluated custom criterion '{crit_id}' using declarative data rules."
    return final_score, explanation, source_ids


_CATEGORY_EVALUATORS: dict[str, Callable[[DesignCandidate, DesignProblem, PreferenceCriterion], tuple[float, str, list[str]]]] = {
    "functional": _eval_functional,
    "zoning": _eval_zoning,
    "circulation": _eval_circulation,
    "infrastructure": _eval_infrastructure,
    "constructability": _eval_constructability,
    "intent": _eval_intent,
}


class AbstractStrategicScorer:
    """
    Data-driven, deterministic abstract strategic candidate scorer.
    Evaluates candidates before spatial layout realization using preference catalog contracts.
    """

    @classmethod
    def _evaluate_criterion(
        cls,
        candidate: DesignCandidate,
        problem: DesignProblem,
        criterion: PreferenceCriterion,
    ) -> CriterionScore:
        cat_key = criterion.metadata.get("category", "")
        evaluator = _CATEGORY_EVALUATORS.get(cat_key, _eval_generic_custom)

        score_val, explanation, source_ids = evaluator(candidate, problem, criterion)

        # Apply precision rounding
        score_val = _clamp(score_val, 0.0, 1.0)
        weighted = score_val * criterion.weight

        return CriterionScore(
            criterion_id=criterion.id,
            score=score_val,
            weight=criterion.weight,
            weighted_score=weighted,
            explanation=explanation,
            source_ids=source_ids,
        )

    @classmethod
    def score_candidate(
        cls,
        candidate: DesignCandidate,
        problem: DesignProblem,
        preference_catalog: PreferenceCatalog | None = None,
    ) -> ScoreBreakdown:
        """
        Evaluate single DesignCandidate and return multi-criteria ScoreBreakdown.
        """
        catalog = get_preference_catalog(preference_catalog)
        precision = catalog.deterministic_precision

        criterion_scores: list[CriterionScore] = []
        for criterion in catalog.criteria:
            crit_score = cls._evaluate_criterion(candidate, problem, criterion)
            criterion_scores.append(crit_score)

        raw_total = sum(c.weighted_score for c in criterion_scores)
        total_score = round(_clamp(raw_total, 0.0, 1.0), precision)

        # Round individual weighted scores for output consistency
        rounded_criteria = [
            CriterionScore(
                criterion_id=c.criterion_id,
                score=round(c.score, precision),
                weight=c.weight,
                weighted_score=round(c.weighted_score, precision),
                explanation=c.explanation,
                source_ids=c.source_ids,
            )
            for c in criterion_scores
        ]

        return ScoreBreakdown(
            criteria=rounded_criteria,
            total_score=total_score,
            scoring_version=catalog.version,
        )

    @classmethod
    def score_candidates(
        cls,
        candidates: list[DesignCandidate],
        problem: DesignProblem,
        preference_catalog: PreferenceCatalog | None = None,
    ) -> list[RankedCandidate]:
        """
        Score a collection of candidates, compute tie-break ordering and ranks,
        and assign categorical selection status based on catalog thresholds.
        """
        catalog = get_preference_catalog(preference_catalog)
        if not candidates:
            return []

        scored_items: list[tuple[DesignCandidate, ScoreBreakdown, list[Any]]] = []

        for candidate in candidates:
            try:
                score_breakdown = cls.score_candidate(candidate, problem, catalog)
                crit_map = {c.criterion_id: c.score for c in score_breakdown.criteria}
                tb_values = [crit_map.get(cid, 0.0) for cid in catalog.tie_break.priority_criteria]
                tb_key = tb_values + [candidate.id]
                scored_items.append((candidate, score_breakdown, tb_key))
            except Exception as err:
                invalid_breakdown = ScoreBreakdown(
                    criteria=[
                        CriterionScore(
                            criterion_id=c.id,
                            score=0.0,
                            weight=c.weight,
                            weighted_score=0.0,
                            explanation=f"Scoring failed due to invalid candidate structure: {err}",
                            source_ids=[],
                        )
                        for c in catalog.criteria
                    ],
                    total_score=0.0,
                    scoring_version=catalog.version,
                )
                tb_key = [0.0] * len(catalog.tie_break.priority_criteria) + [getattr(candidate, "id", "")]
                scored_items.append((candidate, invalid_breakdown, tb_key))

        # Deterministic sorting: total_score desc, priority criteria scores desc, candidate.id asc
        sorted_items = sorted(
            scored_items,
            key=lambda x: (x[1].total_score, tuple(x[2][:-1]), x[0].id),
            reverse=True,
        )

        ranked_results: list[RankedCandidate] = []
        thresholds = catalog.selection_thresholds

        for rank_idx, (candidate, score_breakdown, tb_key) in enumerate(sorted_items, start=1):
            score = score_breakdown.total_score
            rejection_reasons: list[str] = []

            if score >= thresholds.selected_min_score:
                status = SelectionStatus.SELECTED
            elif score >= thresholds.viable_min_score:
                status = SelectionStatus.VIABLE
            elif score >= thresholds.marginal_min_score:
                status = SelectionStatus.MARGINAL
            else:
                status = SelectionStatus.REJECTED
                rejection_reasons.append(
                    f"Total score {score:.{catalog.deterministic_precision}f} below marginal threshold {thresholds.marginal_min_score:.{catalog.deterministic_precision}f}"
                )

            high_risk_count = sum(
                1 for r in candidate.risks
                if str(getattr(r, "severity", "")).lower() in {"high", "error", "blocking", "analysisseverity.error", "analysisseverity.blocking"}
            )
            if high_risk_count > 3 and status != SelectionStatus.REJECTED:
                status = SelectionStatus.REJECTED
                rejection_reasons.append(f"Candidate contains {high_risk_count} high-severity risks")

            provenance = {
                "problem_id": problem.id,
                "problem_version": problem.version,
                "strategy_id": candidate.source_strategy_id,
                "candidate_id": candidate.id,
                "scoring_catalog_version": catalog.version,
            }
            if candidate.provenance:
                provenance["candidate_provenance"] = candidate.provenance

            ranked_results.append(
                RankedCandidate(
                    candidate_id=candidate.id,
                    strategy_id=candidate.source_strategy_id,
                    rank=rank_idx,
                    score_breakdown=score_breakdown,
                    selection_status=status,
                    rejection_reasons=rejection_reasons,
                    tie_break_key=tb_key,
                    provenance=provenance,
                )
            )

        return ranked_results
