"""
Candidate Selector & Deterministic Tie-Breaking Engine for Stage 3B.5-5.

Consumes already-scored RankedCandidate objects and selects the authoritative candidate set
based on PreferenceCatalog rules, selection thresholds, tie-breaking cascade, and max selection limits.

STRICT BOUNDARY RULES:
- MUST NOT generate strategies, modify candidates, run spatial realization, or invoke solvers.
- MUST NOT contain domain-specific string branching (if criterion_id == "program_usability", etc.).
- MUST be data-driven, deterministic, immutable, and defensive.
"""

from collections import defaultdict
from typing import Any

from app.schemas.strategy_preference import PreferenceCatalog
from app.schemas.strategy_ranking import (
    RankedCandidate,
    RankingResult,
    SelectionStatus,
)
from app.services.analysis.catalog_loader import get_preference_catalog


class CandidateSelector:
    """
    Data-driven, deterministic candidate selection and tie-breaking engine.
    """

    @classmethod
    def select(
        cls,
        ranked_candidates: list[RankedCandidate],
        preference_catalog: PreferenceCatalog | None = None,
        *,
        max_selected: int | None = None,
        source_problem_id: str | None = None,
        source_problem_version: int | None = None,
    ) -> RankingResult:
        """
        Deterministically rank and select candidates from an already-scored candidate list.

        :param ranked_candidates: List of RankedCandidate objects (pre-scored).
        :param preference_catalog: PreferenceCatalog instance or None to load default.
        :param max_selected: Optional explicit override for maximum selected candidate count.
        :param source_problem_id: Optional DesignProblem ID (derived from candidate provenance if omitted).
        :param source_problem_version: Optional DesignProblem version (derived from candidate provenance if omitted).
        :return: RankingResult containing ordered candidate ranks and selected_candidate_ids.
        """
        catalog = get_preference_catalog(preference_catalog)
        precision = catalog.deterministic_precision

        # Handle empty input
        if not ranked_candidates:
            prob_id = source_problem_id or "problem-empty"
            prob_ver = source_problem_version if source_problem_version is not None else 1
            return RankingResult(
                id=f"ranking-{prob_id}-{prob_ver}",
                source_problem_id=prob_id,
                source_problem_version=prob_ver,
                ranked_candidates=[],
                selected_candidate_ids=[],
                ranking_version="3B.5-5.v1",
                provenance={
                    "selector": "deterministic-candidate-selector",
                    "ranking_version": "3B.5-5.v1",
                    "catalog_version": catalog.version,
                    "total_ranked": 0,
                    "total_selected": 0,
                    "selected_candidate_ids": [],
                },
            )

        # Validate duplicate candidate IDs
        cand_ids = [rc.candidate_id for rc in ranked_candidates]
        if len(cand_ids) != len(set(cand_ids)):
            raise ValueError(f"Duplicate candidate_id found in input ranked_candidates: {cand_ids}")

        # Derive problem metadata if not explicitly provided
        prob_id = source_problem_id
        prob_ver = source_problem_version

        if prob_id is None or prob_ver is None:
            for rc in ranked_candidates:
                if isinstance(rc.provenance, dict):
                    if prob_id is None and "problem_id" in rc.provenance:
                        prob_id = str(rc.provenance["problem_id"])
                    if prob_ver is None and "problem_version" in rc.provenance:
                        try:
                            prob_ver = int(rc.provenance["problem_version"])
                        except (ValueError, TypeError):
                            pass
            if prob_id is None:
                prob_id = "problem-1"
            if prob_ver is None:
                prob_ver = 1

        priority_criteria = catalog.tie_break.priority_criteria

        # Deep copy input candidates to ensure non-mutation
        candidate_copies = [rc.model_copy(deep=True) for rc in ranked_candidates]

        def _sorting_key(rc: RankedCandidate) -> tuple[Any, ...]:
            score = round(rc.score_breakdown.total_score, precision)
            crit_map = {c.criterion_id: c.score for c in rc.score_breakdown.criteria}
            tb_scores = tuple(round(crit_map.get(cid, 0.0), precision) for cid in priority_criteria)
            return (score, tb_scores)

        # Group candidates by (score, priority_criterion_scores)
        groups: dict[tuple[Any, ...], list[RankedCandidate]] = defaultdict(list)
        for rc in candidate_copies:
            key = _sorting_key(rc)
            groups[key].append(rc)

        # Sort keys descending, then candidate_id ascending for tie-break
        sorted_keys = sorted(groups.keys(), reverse=True)
        ordered_candidates: list[RankedCandidate] = []
        for k in sorted_keys:
            group_sorted = sorted(groups[k], key=lambda x: x.candidate_id)
            ordered_candidates.extend(group_sorted)

        thresholds = catalog.selection_thresholds
        selection_limit = max_selected if max_selected is not None else len(ordered_candidates)

        final_ranked_candidates: list[RankedCandidate] = []
        selected_ids: list[str] = []

        for rank_idx, rc in enumerate(ordered_candidates, start=1):
            score = rc.score_breakdown.total_score
            crit_map = {c.criterion_id: c.score for c in rc.score_breakdown.criteria}
            tb_key = [score] + [crit_map.get(cid, 0.0) for cid in priority_criteria] + [rc.candidate_id]

            rejection_reasons = list(rc.rejection_reasons)
            current_status = rc.selection_status

            if current_status == SelectionStatus.REJECTED:
                final_status = SelectionStatus.REJECTED
                if not rejection_reasons:
                    rejection_reasons.append("Rejected by upstream evaluation status")
            elif score < thresholds.marginal_min_score:
                final_status = SelectionStatus.REJECTED
                if not any("below marginal threshold" in r for r in rejection_reasons):
                    rejection_reasons.append(
                        f"Total score {score:.{precision}f} below marginal threshold {thresholds.marginal_min_score:.{precision}f}"
                    )
            elif score < thresholds.viable_min_score:
                final_status = SelectionStatus.MARGINAL
                if not any("marginal threshold" in r for r in rejection_reasons):
                    rejection_reasons.append(
                        f"Total score {score:.{precision}f} below viable threshold {thresholds.viable_min_score:.{precision}f}"
                    )
            elif score < thresholds.selected_min_score:
                final_status = SelectionStatus.VIABLE
                if not any("selection threshold" in r for r in rejection_reasons):
                    rejection_reasons.append(
                        f"Total score {score:.{precision}f} below selected threshold {thresholds.selected_min_score:.{precision}f}"
                    )
            else:
                if len(selected_ids) < selection_limit:
                    final_status = SelectionStatus.SELECTED
                    selected_ids.append(rc.candidate_id)
                else:
                    final_status = SelectionStatus.VIABLE
                    rejection_reasons.append(
                        f"Eligible candidate not selected because max_selected limit of {selection_limit} was reached"
                    )

            prov = dict(rc.provenance) if isinstance(rc.provenance, dict) else {}
            prov["selection_engine"] = "CandidateSelector"
            prov["rank"] = rank_idx
            prov["catalog_version"] = catalog.version

            final_rc = RankedCandidate(
                candidate_id=rc.candidate_id,
                strategy_id=rc.strategy_id,
                rank=rank_idx,
                score_breakdown=rc.score_breakdown,
                selection_status=final_status,
                rejection_reasons=rejection_reasons,
                tie_break_key=tb_key,
                provenance=prov,
            )
            final_ranked_candidates.append(final_rc)

        ranking_id = f"ranking-{prob_id}-{prob_ver}"
        ranking_provenance = {
            "selector": "deterministic-candidate-selector",
            "ranking_version": "3B.5-5.v1",
            "catalog_version": catalog.version,
            "source_problem_id": prob_id,
            "source_problem_version": prob_ver,
            "total_ranked": len(final_ranked_candidates),
            "total_selected": len(selected_ids),
            "selected_candidate_ids": selected_ids,
        }

        return RankingResult(
            id=ranking_id,
            source_problem_id=prob_id,
            source_problem_version=prob_ver,
            ranked_candidates=final_ranked_candidates,
            selected_candidate_ids=selected_ids,
            ranking_version="3B.5-5.v1",
            provenance=ranking_provenance,
        )
