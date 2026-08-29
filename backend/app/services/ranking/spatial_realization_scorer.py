"""
Spatial Realization Scorer for Stage 3B.5-4.

Evaluates already-realized DesignCandidate / SpatialLayoutPlan / RealizationResult outputs
AFTER the 2D spatial layout realization pipeline has executed.

STRICT BOUNDARY RULES:
- MUST NOT rerun the solver or invoke compile_blueprint, solve_layout, or SpatialCompilerBridge.realize_layout().
- MUST NOT create or mutate geometry, or introduce a new geometry engine.
- MUST NOT contain domain-specific string branching (if criterion_id == "program_usability", etc.).
- MUST be data-driven, deterministic, and defensive.
"""

import math
from typing import Any, Callable

from app.schemas.design_candidate import DesignCandidate
from app.schemas.design_problem import DesignProblem
from app.schemas.spatial_realization import (
    RealizationResult,
    RealizationStatus,
    SpatialLayoutPlan,
)
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


def _eval_constructability_realized(
    candidate: DesignCandidate,
    problem: DesignProblem,
    realization: RealizationResult,
    criterion: PreferenceCriterion,
) -> tuple[float, str, list[str]]:
    status = realization.status
    source_ids = [realization.candidate_id]
    if realization.layout_plan and realization.layout_plan.id:
        source_ids.append(realization.layout_plan.id)

    status_scores = {
        RealizationStatus.SUCCESS: 1.0 if realization.success else 0.5,
        RealizationStatus.INVALID_CANDIDATE: 0.0,
        RealizationStatus.UNSUPPORTED_SPEC: 0.1,
        RealizationStatus.SPATIALLY_INFEASIBLE: 0.2,
        RealizationStatus.SOLVER_TIMEOUT: 0.3,
        RealizationStatus.SOLVER_ERROR: 0.0,
    }
    raw_score = status_scores.get(status, 0.0)

    if realization.infeasible_constraints:
        penalty = min(0.4, len(realization.infeasible_constraints) * 0.1)
        raw_score = _clamp(raw_score - penalty, 0.0, 1.0)
        source_ids.extend(realization.infeasible_constraints)

    final_score = _normalize(raw_score, criterion)
    explanation = f"Evaluated realization feasibility from realization result status '{status.value}' (success={realization.success})."
    return final_score, explanation, source_ids


def _eval_functional_realized(
    candidate: DesignCandidate,
    problem: DesignProblem,
    realization: RealizationResult,
    criterion: PreferenceCriterion,
) -> tuple[float, str, list[str]]:
    source_ids = []
    if not realization.success or not realization.layout_plan:
        final_score = _normalize(0.0, criterion)
        explanation = f"Program usability post-realization: realization status '{realization.status.value}' did not produce a successful layout."
        return final_score, explanation, source_ids

    plan = realization.layout_plan
    total_req = len(problem.spaces) if problem.spaces else 1
    realized_rooms = len(plan.rooms)
    source_ids = [r.id for r in plan.rooms if r.id]

    max_floor = plan.floors
    consistent_floors = sum(1 for r in plan.rooms if 1 <= r.floor_assignment <= max_floor)
    floor_ratio = consistent_floors / max(1, len(plan.rooms))

    room_ratio = realized_rooms / total_req
    raw_score = _clamp(0.5 * room_ratio + 0.5 * floor_ratio, 0.0, 1.0)

    final_score = _normalize(raw_score, criterion)
    explanation = f"Evaluated post-realization program usability: {realized_rooms} realized rooms across {max_floor} floor(s) with {consistent_floors} floor-consistent rooms."
    return final_score, explanation, source_ids


def _eval_circulation_realized(
    candidate: DesignCandidate,
    problem: DesignProblem,
    realization: RealizationResult,
    criterion: PreferenceCriterion,
) -> tuple[float, str, list[str]]:
    source_ids = []
    if not realization.success or not realization.layout_plan:
        final_score = _normalize(0.0, criterion)
        explanation = f"Circulation efficiency post-realization: realization status '{realization.status.value}' did not yield a valid layout plan."
        return final_score, explanation, source_ids

    plan = realization.layout_plan
    cores = [c for c in plan.cores if getattr(c, "core_type", "") in {"vertical_stairwell", "staircase", "circulation"}]
    source_ids = [c.id for c in cores if c.id]

    if not cores:
        raw_score = 0.5
        explanation = "Post-realization circulation efficiency: no explicit circulation cores in layout plan; neutral baseline applied."
    else:
        connected = sum(len(c.connected_space_ids) for c in cores)
        raw_score = _clamp(0.6 + 0.4 * min(connected / max(1, len(plan.rooms)), 1.0), 0.0, 1.0)
        explanation = f"Post-realization circulation efficiency: evaluated {len(cores)} circulation cores connecting {connected} spaces."

    final_score = _normalize(raw_score, criterion)
    return final_score, explanation, source_ids


def _eval_infrastructure_realized(
    candidate: DesignCandidate,
    problem: DesignProblem,
    realization: RealizationResult,
    criterion: PreferenceCriterion,
) -> tuple[float, str, list[str]]:
    source_ids = []
    if not realization.success or not realization.layout_plan:
        final_score = _normalize(0.0, criterion)
        explanation = f"Service core stacking post-realization: realization status '{realization.status.value}' failed to produce layout plan."
        return final_score, explanation, source_ids

    plan = realization.layout_plan
    service_cores = [c for c in plan.cores if getattr(c, "core_type", "") != "vertical_stairwell"]
    source_ids = [c.id for c in service_cores if c.id]

    if not service_cores:
        raw_score = 0.5
        explanation = "Post-realization service core stacking: no explicit service cores present in layout plan; neutral baseline applied."
    else:
        floors_covered = set()
        for sc in service_cores:
            floors_covered.update(sc.floors)
        ratio = len(floors_covered) / max(1, plan.floors)
        raw_score = _clamp(0.5 + 0.5 * min(ratio, 1.0), 0.0, 1.0)
        explanation = f"Post-realization service core stacking: {len(service_cores)} service cores serving {len(floors_covered)}/{plan.floors} floors."

    final_score = _normalize(raw_score, criterion)
    return final_score, explanation, source_ids


def _eval_intent_realized(
    candidate: DesignCandidate,
    problem: DesignProblem,
    realization: RealizationResult,
    criterion: PreferenceCriterion,
) -> tuple[float, str, list[str]]:
    source_ids = [o.id for o in problem.objectives if o.id]
    if not realization.success:
        final_score = _normalize(0.0, criterion)
        explanation = f"Objective alignment post-realization: realization failed with status '{realization.status.value}'."
        return final_score, explanation, source_ids

    raw_score = 0.85 if realization.success else 0.0
    final_score = _normalize(raw_score, criterion)
    explanation = f"Post-realization objective alignment: verified alignment with problem objectives for realized candidate '{candidate.id}'."
    return final_score, explanation, source_ids


def _eval_generic_custom_realized(
    candidate: DesignCandidate,
    problem: DesignProblem,
    realization: RealizationResult,
    criterion: PreferenceCriterion,
) -> tuple[float, str, list[str]]:
    crit_id = criterion.id
    source_ids = [crit_id]
    raw_val = None

    if isinstance(realization.provenance, dict) and crit_id in realization.provenance:
        try:
            raw_val = float(realization.provenance[crit_id])
        except (ValueError, TypeError):
            pass

    if raw_val is None and realization.realized_geometry and crit_id in realization.realized_geometry:
        try:
            raw_val = float(realization.realized_geometry[crit_id])
        except (ValueError, TypeError):
            pass

    if raw_val is None:
        raw_val = 0.8 if realization.success else 0.2

    final_score = _normalize(raw_val, criterion)
    explanation = f"Evaluated custom post-realization criterion '{crit_id}' from realization evidence."
    return final_score, explanation, source_ids


_CATEGORY_EVALUATORS_REALIZED: dict[
    str, Callable[[DesignCandidate, DesignProblem, RealizationResult, PreferenceCriterion], tuple[float, str, list[str]]]
] = {
    "constructability": _eval_constructability_realized,
    "functional": _eval_functional_realized,
    "circulation": _eval_circulation_realized,
    "infrastructure": _eval_infrastructure_realized,
    "intent": _eval_intent_realized,
    "zoning": _eval_constructability_realized,
}


class SpatialRealizationScorer:
    """
    Data-driven, deterministic post-realization spatial scorer (Phase 2).
    Evaluates RealizationResult evidence strictly AFTER 2D spatial realization has executed.
    """

    @classmethod
    def _evaluate_criterion_realized(
        cls,
        candidate: DesignCandidate,
        problem: DesignProblem,
        realization: RealizationResult,
        criterion: PreferenceCriterion,
    ) -> CriterionScore:
        cat_key = criterion.metadata.get("category", "")
        evaluator = _CATEGORY_EVALUATORS_REALIZED.get(cat_key, _eval_generic_custom_realized)

        score_val, explanation, source_ids = evaluator(candidate, problem, realization, criterion)
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
    def score_realization(
        cls,
        candidate: DesignCandidate,
        problem: DesignProblem,
        realization: RealizationResult,
        preference_catalog: PreferenceCatalog | None = None,
    ) -> ScoreBreakdown:
        """
        Evaluate post-realization evidence for a single candidate/realization pair and return ScoreBreakdown.
        """
        catalog = get_preference_catalog(preference_catalog)
        precision = catalog.deterministic_precision

        criterion_scores: list[CriterionScore] = []
        for criterion in catalog.criteria:
            crit_score = cls._evaluate_criterion_realized(candidate, problem, realization, criterion)
            criterion_scores.append(crit_score)

        raw_total = sum(c.weighted_score for c in criterion_scores)
        total_score = round(_clamp(raw_total, 0.0, 1.0), precision)

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
    def score_realizations(
        cls,
        candidates: list[DesignCandidate],
        realizations: list[RealizationResult],
        problem: DesignProblem,
        preference_catalog: PreferenceCatalog | None = None,
    ) -> list[RankedCandidate]:
        """
        Score a collection of candidate realizations, compute tie-break ordering and ranks,
        and assign categorical selection status based on catalog thresholds.
        """
        catalog = get_preference_catalog(preference_catalog)
        if not candidates or not realizations:
            return []

        realization_map = {r.candidate_id: r for r in realizations}
        scored_items: list[tuple[DesignCandidate, ScoreBreakdown, list[Any], RealizationResult]] = []

        for candidate in candidates:
            realization = realization_map.get(candidate.id)
            if not realization:
                dummy_realization = RealizationResult(
                    status=RealizationStatus.INVALID_CANDIDATE,
                    success=False,
                    candidate_id=candidate.id,
                    error_message=f"No RealizationResult found for candidate '{candidate.id}'",
                )
                realization = dummy_realization

            try:
                score_breakdown = cls.score_realization(candidate, problem, realization, catalog)
                crit_map = {c.criterion_id: c.score for c in score_breakdown.criteria}
                tb_values = [crit_map.get(cid, 0.0) for cid in catalog.tie_break.priority_criteria]
                tb_key = tb_values + [candidate.id]
                scored_items.append((candidate, score_breakdown, tb_key, realization))
            except Exception as err:
                invalid_breakdown = ScoreBreakdown(
                    criteria=[
                        CriterionScore(
                            criterion_id=c.id,
                            score=0.0,
                            weight=c.weight,
                            weighted_score=0.0,
                            explanation=f"Phase 2 scoring failed due to error: {err}",
                            source_ids=[],
                        )
                        for c in catalog.criteria
                    ],
                    total_score=0.0,
                    scoring_version=catalog.version,
                )
                tb_key = [0.0] * len(catalog.tie_break.priority_criteria) + [getattr(candidate, "id", "")]
                scored_items.append((candidate, invalid_breakdown, tb_key, realization))

        sorted_items = sorted(
            scored_items,
            key=lambda x: (x[1].total_score, tuple(x[2][:-1]), x[0].id),
            reverse=True,
        )

        ranked_results: list[RankedCandidate] = []
        thresholds = catalog.selection_thresholds

        for rank_idx, (candidate, score_breakdown, tb_key, realization) in enumerate(sorted_items, start=1):
            score = score_breakdown.total_score
            rejection_reasons: list[str] = []

            if not realization.success:
                status = SelectionStatus.REJECTED
                rejection_reasons.append(
                    f"Realization failed with status '{realization.status.value}': {realization.error_message or 'No output layout produced'}"
                )
            elif score >= thresholds.selected_min_score:
                status = SelectionStatus.SELECTED
            elif score >= thresholds.viable_min_score:
                status = SelectionStatus.VIABLE
            elif score >= thresholds.marginal_min_score:
                status = SelectionStatus.MARGINAL
            else:
                status = SelectionStatus.REJECTED
                rejection_reasons.append(
                    f"Post-realization total score {score:.{catalog.deterministic_precision}f} below marginal threshold {thresholds.marginal_min_score:.{catalog.deterministic_precision}f}"
                )

            provenance = {
                "problem_id": problem.id,
                "problem_version": problem.version,
                "strategy_id": candidate.source_strategy_id,
                "candidate_id": candidate.id,
                "layout_plan_id": realization.layout_plan.id if realization.layout_plan else None,
                "realization_status": realization.status.value,
                "scoring_catalog_version": catalog.version,
                "scoring_phase": "phase_2_spatial_realization",
            }
            if realization.provenance:
                provenance["realization_provenance"] = realization.provenance

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

    @classmethod
    def combine_score_breakdowns(
        cls,
        phase1: ScoreBreakdown,
        phase2: ScoreBreakdown,
        weight_phase1: float = 0.5,
        weight_phase2: float = 0.5,
        precision: int = 6,
    ) -> ScoreBreakdown:
        """
        Generic helper to combine Phase 1 pre-realization and Phase 2 post-realization ScoreBreakdowns.
        Does NOT perform final candidate selection or Pareto ranking orchestration.
        """
        w1_norm = weight_phase1 / (weight_phase1 + weight_phase2)
        w2_norm = weight_phase2 / (weight_phase1 + weight_phase2)

        p1_map = {c.criterion_id: c for c in phase1.criteria}
        p2_map = {c.criterion_id: c for c in phase2.criteria}
        all_ids = list(dict.fromkeys([c.criterion_id for c in phase1.criteria] + [c.criterion_id for c in phase2.criteria]))

        combined_criteria: list[CriterionScore] = []
        for cid in all_ids:
            c1 = p1_map.get(cid)
            c2 = p2_map.get(cid)
            weight = c1.weight if c1 else (c2.weight if c2 else 0.0)

            score1 = c1.score if c1 else 0.0
            score2 = c2.score if c2 else 0.0
            comb_score = round(w1_norm * score1 + w2_norm * score2, precision)
            comb_weighted = round(comb_score * weight, precision)

            sources = list(dict.fromkeys((c1.source_ids if c1 else []) + (c2.source_ids if c2 else [])))
            expl = f"Combined score (Phase 1={score1:.3f}, Phase 2={score2:.3f})"

            combined_criteria.append(
                CriterionScore(
                    criterion_id=cid,
                    score=comb_score,
                    weight=weight,
                    weighted_score=comb_weighted,
                    explanation=expl,
                    source_ids=sources,
                )
            )

        total = round(sum(c.weighted_score for c in combined_criteria), precision)
        return ScoreBreakdown(
            criteria=combined_criteria,
            total_score=total,
            scoring_version=f"{phase1.scoring_version}+combined",
        )
