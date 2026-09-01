"""
Pipeline Orchestrator for Stage 3B.6.

Coordinates end-to-end architectural compilation:
CompilerIntent → DesignProblem → ArchitecturalAnalysis → DesignStrategy[] →
DesignCandidate[] → SpatialRealization → CandidateSelector →
Winner + Ranked Alternatives.

STRICT BOUNDARY RULES:
- Thin composition layer ONLY.
- ZERO architectural domain knowledge or dimension-specific rules.
- Coordinates existing modular services.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.core.exceptions import (
    AIParserError,
    InfeasibleRequestError,
    OptimizationSolverError,
)
from app.drawing import Drawing, Polyline, export_drawing_to_svg
from app.drawing.symbols import generate_door_symbol, generate_window_symbol
from app.schemas.compile import CandidateSummary, CompileRequest, CompileResponse
from app.schemas.design_candidate import DesignCandidate
from app.schemas.design_strategy import DesignStrategy
from app.schemas.spatial_realization import RealizationResult, RealizationStatus
from app.schemas.strategy_ranking import CriterionScore, RankedCandidate, ScoreBreakdown, SelectionStatus
from app.services.ai.explainer import explain_layout
from app.services.ai.parser import parse_requirements
from app.services.analysis.architectural_analyzer import analyze_design_problem
from app.services.analysis.candidate_organizer import organize_candidate
from app.services.analysis.catalog_loader import get_catalog_organization_rules
from app.services.analysis.spatial_adapter import CandidateToLayoutAdapter
from app.services.analysis.strategy_generator import generate_strategies
from app.services.annotation_engine import generate_annotations
from app.services.compiler.intent_adapter import to_design_problem
from app.services.dimension_engine import generate_dimensions
from app.services.geometry_resolver import resolve_geometry
from app.services.optimization.feasibility import verify_feasibility
from app.services.ranking.abstract_strategic_scorer import AbstractStrategicScorer
from app.services.ranking.candidate_selector import CandidateSelector
from app.services.ranking.spatial_realization_scorer import SpatialRealizationScorer
from app.services.realization.compiler_bridge import SpatialCompilerBridge
from app.services.relationship_builder import build_tbm_from_layout
from app.services.orchestration.session_registry import (
    CandidateRecord,
    SessionRecord,
    SessionRegistry,
    get_session_registry,
)

logger = logging.getLogger(__name__)


def generate_drawing_svg_for_layout(payload: Dict[str, Any], compiled_result: Dict[str, Any]) -> Tuple[Any, str]:
    """Pure helper function to generate 2D CAD SVG from a compiled layout."""
    try:
        building = build_tbm_from_layout(payload, compiled_result)
        geom = resolve_geometry(building)
        drawing = Drawing()

        for w_id, panels in geom.wall_panels.items():
            for p in panels:
                drawing.add(Polyline(
                    layer="Walls",
                    color="#1e293b",
                    stroke_width=2.5,
                    points=p.vertices,
                    is_closed=True,
                ))

        for op_id, op in building.openings.items():
            box = geom.opening_boxes.get(op_id)
            if box:
                wall = building.walls.get(op.wall_id) if op.wall_id else None
                if wall is not None:
                    j1 = building.junctions.get(wall.start_junction_id) if wall.start_junction_id else None
                    j2 = building.junctions.get(wall.end_junction_id) if wall.end_junction_id else None
                    if j1 is not None and j2 is not None:
                        dx = j2.x - j1.x
                        dy = j2.y - j1.y
                        L = (dx**2 + dy**2)**0.5
                        if L > 0.01:
                            ux, uy = dx / L, dy / L
                            center = op.position_offset
                            h_w = op.width / 2.0
                            x1_op = j1.x + (center - h_w) * ux
                            y1_op = j1.y + (center - h_w) * uy
                            x2_op = j1.x + (center + h_w) * ux
                            y2_op = j1.y + (center + h_w) * uy
                            if op.type == "Door":
                                for sym_p in generate_door_symbol(x1_op, y1_op, x2_op, y2_op):
                                    drawing.add(sym_p)
                            else:
                                thickness = getattr(wall, "thickness", 0.2)
                                for sym_p in generate_window_symbol(x1_op, y1_op, x2_op, y2_op, thickness):
                                    drawing.add(sym_p)

        generate_dimensions(building, geom, drawing)
        generate_annotations(building, geom, drawing)
        return building, export_drawing_to_svg(drawing)
    except Exception as exc:
        logger.warning(f"SVG Drawing Generation Warning: {exc}")
        return None, f'<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><!-- Drawing Generation Error: {str(exc)} --></svg>'


class PipelineOrchestrator:
    """
    Thin pipeline orchestrator coordinating Stage 1 through Stage 3B.5 services.
    """

    def __init__(
        self,
        session_registry: Optional[SessionRegistry] = None,
        compile_blueprint_fn: Optional[Any] = None,
        explain_layout_fn: Optional[Any] = None,
    ):
        self.registry = session_registry or get_session_registry()
        self.compile_blueprint_fn = compile_blueprint_fn
        self.explain_layout_fn = explain_layout_fn or explain_layout

    def compile(
        self,
        request: CompileRequest,
        client: Any = None,
        ai_state: Optional[Dict[str, Any]] = None,
    ) -> CompileResponse:
        """
        Executes end-to-end architectural reasoning and spatial compilation.
        """
        if not request.prompt.strip():
            raise InfeasibleRequestError(message="Prompt cannot be empty.", detail="Prompt string is blank.")

        if ai_state is None:
            ai_state = {
                "compiler_failed": False,
                "quota_exhausted": False,
                "failure_type": None,
            }

        # Check in-memory prompt cache for deterministic re-use (only for default runtime)
        cached_session = None
        if client is None and self.compile_blueprint_fn is None:
            cached_session = self.registry.get_session_by_prompt(request.prompt)

        if cached_session and cached_session.selected_candidate_id in cached_session.candidates:
            winner_rec = cached_session.candidates[cached_session.selected_candidate_id]
            # Build ranked alternatives summaries
            ranked_summaries = [
                CandidateSummary(
                    candidate_id=c.candidate_id,
                    strategy_id=c.strategy_id,
                    name=c.name,
                    rank=c.rank,
                    is_selected=c.is_selected,
                    composite_score=c.composite_score,
                    strategic_score=c.strategic_score,
                    spatial_score=c.spatial_score,
                    feasibility_status=c.status,
                    trade_offs=c.trade_offs,
                    rejection_reasons=c.rejection_reasons,
                )
                for c in sorted(cached_session.candidates.values(), key=lambda x: x.rank)
            ]
            return CompileResponse(
                session_id=cached_session.session_id,
                selected_candidate_id=cached_session.selected_candidate_id,
                ranked_alternatives=ranked_summaries,
                extracted_intent=cached_session.intent,
                layout=winner_rec.layout,
                boundaries=winner_rec.boundaries,
                metadata=cached_session.metadata,
                geometry=winner_rec.geometry,
                floors=winner_rec.floors,
                metrics=winner_rec.metrics,
                drawing_svg=winner_rec.drawing_svg or "",
                explanation=winner_rec.explanation,
            )

        # 1. Parse Requirements into CompilerIntent
        try:
            intent = parse_requirements(request.prompt, client, ai_state)
        except Exception as exc:
            raise AIParserError(
                message="Failed to parse user intent into structural requirements.",
                detail=str(exc),
            )

        # 2. Feasibility Validation
        setbacks = {
            "left": 3.0,
            "right": 3.0,
            "bottom": intent.front_road_setback,
            "top": 3.0,
        }
        is_feasible, reason = verify_feasibility(intent, setbacks)
        if not is_feasible:
            raise InfeasibleRequestError(
                message="Requested layout exceeds legal or physical limits of the plot.",
                detail=reason,
            )

        # 3. Transform Intent into Stage 1 DesignProblem
        design_problem = to_design_problem(intent)

        # 4. Architectural Analysis (Stage 3A)
        analysis = analyze_design_problem(design_problem)

        # 5. Generic Strategy Generation (Stage 3B.3)
        max_strats = min(request.max_strategies, 10)
        strategies = generate_strategies(analysis, problem=design_problem, max_strategies=max_strats)

        # 6. Candidate Organization & Spatial Realization (Stage 3B.4)
        org_rules = get_catalog_organization_rules()
        realized_candidates: List[Tuple[DesignCandidate, DesignStrategy, RealizationResult]] = []

        for idx, strat in enumerate(strategies, start=1):
            cand_id = f"cand_{idx}_{strat.id}"
            cand = DesignCandidate(
                id=cand_id,
                source_strategy_id=strat.id,
                source_analysis_id=str(analysis.provenance.get("analysis_id", f"analysis-{design_problem.id}")),
                source_problem_id=design_problem.id,
                source_problem_version=design_problem.version,
                name=strat.name,
                selected_decisions=strat.decisions,
            )

            # Enrich candidate topology
            cand = organize_candidate(cand, org_rules, problem=design_problem)

            # Adapt to SpatialLayoutPlan
            layout_plan = CandidateToLayoutAdapter.adapt(cand, design_problem, plan_id=f"plan-{cand_id}")

            # Realize via SpatialCompilerBridge or custom compile_blueprint_fn
            if self.compile_blueprint_fn is not None:
                payload = SpatialCompilerBridge.plan_to_compiler_payload(layout_plan, problem=design_problem)
                comp_res = self.compile_blueprint_fn(payload)
                if comp_res.get("success", False):
                    realization_result = RealizationResult(
                        status=RealizationStatus.SUCCESS,
                        success=True,
                        candidate_id=cand_id,
                        layout_plan=layout_plan,
                        realized_geometry=comp_res,
                    )
                else:
                    err_msg = str(comp_res.get("error", "Optimization Constraint Solver Error: failed"))
                    status = SpatialCompilerBridge.classify_failure(err_msg)
                    realization_result = RealizationResult(
                        status=status,
                        success=False,
                        candidate_id=cand_id,
                        layout_plan=layout_plan,
                        error_message=err_msg,
                    )
            else:
                realization_result = SpatialCompilerBridge.realize_layout(layout_plan, problem=design_problem)

            realized_candidates.append((cand, strat, realization_result))

        # 7. Strategic & Spatial Scoring & Candidate Ranking (Stage 3B.5)
        candidates_list = [c[0] for c in realized_candidates]
        realizations_list = [c[2] for c in realized_candidates]

        strategic_rankings = AbstractStrategicScorer.score_candidates(candidates_list, design_problem)
        strategic_map = {r.candidate_id: r for r in strategic_rankings}

        spatial_rankings = SpatialRealizationScorer.score_realizations(candidates_list, realizations_list, design_problem)
        spatial_map = {r.candidate_id: r for r in spatial_rankings}

        scored_candidates: List[RankedCandidate] = []
        for cand, strat, real_res in realized_candidates:
            strat_rank = strategic_map.get(cand.id)
            spatial_rank = spatial_map.get(cand.id)

            strat_score = strat_rank.score_breakdown.total_score if strat_rank else 0.8
            spatial_score = spatial_rank.score_breakdown.total_score if spatial_rank else 0.0

            if strat_rank and spatial_rank:
                combined_breakdown = SpatialRealizationScorer.combine_score_breakdowns(
                    strat_rank.score_breakdown, spatial_rank.score_breakdown
                )
                comp_score = combined_breakdown.total_score
                sel_status = spatial_rank.selection_status
                reasons = list(spatial_rank.rejection_reasons)
                tb_key = spatial_rank.tie_break_key
            else:
                comp_score = round(0.5 * strat_score + 0.5 * spatial_score, 4)
                combined_breakdown = ScoreBreakdown(
                    criteria=[
                        CriterionScore(criterion_id="strategic", score=strat_score, weight=0.5, weighted_score=strat_score*0.5, explanation="Strategic fit", source_ids=[]),
                        CriterionScore(criterion_id="spatial", score=spatial_score, weight=0.5, weighted_score=spatial_score*0.5, explanation="Spatial score", source_ids=[]),
                    ],
                    total_score=comp_score,
                    scoring_version="3B.6-v1",
                )
                sel_status = SelectionStatus.REJECTED if not real_res.success else SelectionStatus.VIABLE
                reasons = [f"Realization status: {real_res.status.value}"] if not real_res.success else []
                tb_key = [comp_score, spatial_score, strat_score, cand.id]

            scored_candidates.append(
                RankedCandidate(
                    candidate_id=cand.id,
                    strategy_id=strat.id,
                    rank=1,  # will be assigned by selector
                    score_breakdown=combined_breakdown,
                    selection_status=sel_status,
                    rejection_reasons=reasons,
                    tie_break_key=tb_key,
                    provenance={"problem_id": design_problem.id, "problem_version": design_problem.version},
                )
            )

        # Execute CandidateSelector
        ranking_result = CandidateSelector.select(
            scored_candidates,
            max_selected=1,
            source_problem_id=design_problem.id,
            source_problem_version=design_problem.version,
        )

        # Identify winning candidate
        if not ranking_result.selected_candidate_ids:
            # Fallback to top ranked candidate if feasible, else top realized candidate
            feasible_ranked = [r for r in ranking_result.ranked_candidates if r.selection_status != SelectionStatus.REJECTED]
            if not feasible_ranked:
                realized_success = [c for c, s, r in realized_candidates if r.success]
                if realized_success:
                    winner_id = ranking_result.ranked_candidates[0].candidate_id if ranking_result.ranked_candidates else realized_success[0].id
                else:
                    # Extract specific solver error if present
                    for _, _, real_res in realized_candidates:
                        if real_res.error_message and "Optimization Constraint Solver Error" in real_res.error_message:
                            raise OptimizationSolverError(
                                message="MILP solver failed to pack rooms under the requested constraints.",
                                detail=real_res.error_message,
                            )
                    raise OptimizationSolverError(
                        message="All candidate strategies failed spatial optimization under the requested constraints.",
                        detail="No candidate could be spatially realized within plot envelope.",
                    )
            else:
                winner_id = feasible_ranked[0].candidate_id
        else:
            winner_id = ranking_result.selected_candidate_ids[0]

        # 8. Create Session and Populate Candidate Records
        metadata = {
            "plot_width": intent.plot_width,
            "plot_depth": intent.plot_depth,
            "buildable_area_sqft": (intent.plot_width - 6.0) * (intent.plot_depth - intent.front_road_setback - 3.0),
            "ots_generated_count": 0,
        }
        session = self.registry.create_session(
            prompt=request.prompt,
            selected_candidate_id=winner_id,
            intent=intent.model_dump(),
            metadata=metadata,
        )

        rank_order_map = {r.candidate_id: r for r in ranking_result.ranked_candidates}

        winner_record: Optional[CandidateRecord] = None

        # Build payload for CAD / Explanation
        payload = {
            "plot": {"width": intent.plot_width, "depth": intent.plot_depth},
            "setbacks": setbacks,
            "road_edge": "bottom",
            "grid_snap": 0.5,
            "floors": intent.floors,
        }

        for cand, strat, real_res in realized_candidates:
            is_winner = (cand.id == winner_id)
            r_info = rank_order_map.get(cand.id)
            rank = r_info.rank if r_info else 99
            comp_score = r_info.score_breakdown.total_score if r_info else 0.0

            compiler_res = real_res.realized_geometry or {}

            # Generate presentation assets for winner immediately
            if is_winner and real_res.status == RealizationStatus.SUCCESS:
                # Build SVG drawing
                _, drawing_svg = generate_drawing_svg_for_layout(payload, compiler_res)
                explanation_obj = self.explain_layout_fn(request.prompt, compiler_res, client, ai_state)
                if hasattr(explanation_obj, "model_dump"):
                    explanation_dict = explanation_obj.model_dump()
                elif isinstance(explanation_obj, dict):
                    explanation_dict = explanation_obj
                else:
                    explanation_dict = dict(explanation_obj)
            else:
                drawing_svg = None
                explanation_dict = {
                    "overview": f"Strategy: {strat.name}. Approach: {strat.approach}",
                    "space_allocation_reasoning": {},
                    "compliance_analysis": "Pending full presentation hydration.",
                    "zoning_rationale": "Pending full presentation hydration.",
                }

            trade_offs_str = [f"{t.explanation}" for t in strat.trade_offs] if strat.trade_offs else []

            cand_rec = CandidateRecord(
                candidate_id=cand.id,
                strategy_id=strat.id,
                name=strat.name,
                rank=rank,
                is_selected=is_winner,
                status=real_res.status.value,
                strategic_score=r_info.score_breakdown.criteria[0].score if r_info else 0.0,
                spatial_score=r_info.score_breakdown.criteria[1].score if r_info else 0.0,
                composite_score=comp_score,
                trade_offs=trade_offs_str,
                rejection_reasons=r_info.rejection_reasons if r_info else [],
                layout=compiler_res.get("layout", {}),
                boundaries=compiler_res.get("boundaries", {}),
                geometry=compiler_res.get("geometry", {}),
                floors=compiler_res.get("floors", {}),
                metrics=compiler_res.get("metrics", {}),
                drawing_svg=drawing_svg,
                explanation=explanation_dict,
            )

            self.registry.store_candidate(session.session_id, cand_rec)
            if is_winner:
                winner_record = cand_rec

        if not winner_record:
            raise OptimizationSolverError(
                message="Winning candidate presentation generation failed.",
                detail=f"Candidate '{winner_id}' could not be formatted.",
            )

        # Build CandidateSummary list
        ranked_summaries = [
            CandidateSummary(
                candidate_id=c.candidate_id,
                strategy_id=c.strategy_id,
                name=c.name,
                rank=c.rank,
                is_selected=c.is_selected,
                composite_score=c.composite_score,
                strategic_score=c.strategic_score,
                spatial_score=c.spatial_score,
                feasibility_status=c.status,
                trade_offs=c.trade_offs,
                rejection_reasons=c.rejection_reasons,
            )
            for c in sorted(session.candidates.values(), key=lambda x: x.rank)
        ]

        return CompileResponse(
            session_id=session.session_id,
            selected_candidate_id=winner_id,
            ranked_alternatives=ranked_summaries,
            extracted_intent=intent.model_dump(),
            layout=winner_record.layout,
            boundaries=winner_record.boundaries,
            metadata=metadata,
            geometry=winner_record.geometry,
            floors=winner_record.floors,
            metrics=winner_record.metrics,
            drawing_svg=winner_record.drawing_svg or "",
            explanation=winner_record.explanation,
        )

    def hydrate_candidate(
        self,
        session_id: str,
        candidate_id: str,
        client: Any = None,
    ) -> Dict[str, Any]:
        """
        Hydrates full presentation assets for a specific candidate without re-running
        parsing, strategy generation, or MILP layout solving.
        """
        session = self.registry.get_session(session_id)
        if not session:
            return {
                "success": False,
                "error": "Session not found or expired.",
            }

        candidate = self.registry.get_candidate(session_id, candidate_id)
        if not candidate:
            return {
                "success": False,
                "error": f"Candidate '{candidate_id}' not found in session '{session_id}'.",
            }

        # Lazy-generate drawing SVG if not already present
        if not candidate.drawing_svg and candidate.layout:
            payload = {
                "plot": {
                    "width": session.intent.get("plot_width", 40.0),
                    "depth": session.intent.get("plot_depth", 40.0),
                },
                "setbacks": {
                    "left": 3.0,
                    "right": 3.0,
                    "bottom": session.intent.get("front_road_setback", 3.0),
                    "top": 3.0,
                },
                "road_edge": "bottom",
                "grid_snap": 0.5,
                "floors": session.intent.get("floors", 1),
            }
            compiled_result = {
                "layout": candidate.layout,
                "geometry": candidate.geometry,
                "floors": candidate.floors,
            }
            _, drawing_svg = generate_drawing_svg_for_layout(payload, compiled_result)
            candidate.drawing_svg = drawing_svg

        return {
            "success": True,
            "session_id": session_id,
            "candidate_id": candidate.candidate_id,
            "strategy_id": candidate.strategy_id,
            "name": candidate.name,
            "rank": candidate.rank,
            "is_selected": candidate.is_selected,
            "status": candidate.status,
            "layout": candidate.layout,
            "boundaries": candidate.boundaries,
            "geometry": candidate.geometry,
            "floors": candidate.floors,
            "metrics": candidate.metrics,
            "drawing_svg": candidate.drawing_svg,
            "explanation": candidate.explanation,
        }

    def recompile_with_delta(
        self,
        base_session_id: str,
        delta_prompt: str,
        client: Any = None,
        ai_state: Optional[Dict[str, Any]] = None,
    ) -> CompileResponse:
        """
        Executes Task 4 Requirement Modification Loop:
        Retrieves the base session's intent and DesignProblem, applies the requirement delta,
        re-runs architectural analysis, strategy generation, realization, and ranking.
        """
        from app.schemas.intent import CompilerIntent
        from app.services.analysis.problem_modifier import (
            apply_requirement_deltas,
            parse_prompt_delta_to_requirement_delta,
        )

        session = self.registry.get_session(base_session_id)
        if not session:
            return self.compile(CompileRequest(prompt=delta_prompt), client=client, ai_state=ai_state)

        base_intent_dict = dict(session.intent)
        base_intent = CompilerIntent(**base_intent_dict)
        base_problem = to_design_problem(base_intent)

        # Parse and apply delta
        deltas = parse_prompt_delta_to_requirement_delta(delta_prompt, base_problem)
        updated_problem = apply_requirement_deltas(base_problem, deltas)

        # Update intent fields
        delta_intent = parse_requirements(delta_prompt, client, ai_state)
        if delta_intent.vertical_circulation:
            base_intent.vertical_circulation = delta_intent.vertical_circulation
        if delta_intent.floor_allocation:
            base_intent.floor_allocation = delta_intent.floor_allocation
        if delta_intent.entrance_strategy:
            base_intent.entrance_strategy = delta_intent.entrance_strategy

        # Re-compile with updated problem and intent
        combined_prompt = f"{session.prompt} | Modified: {delta_prompt}"
        return self._compile_from_problem(
            design_problem=updated_problem,
            intent=base_intent,
            prompt=combined_prompt,
            max_strategies=3,
            client=client,
            ai_state=ai_state,
        )

    def _compile_from_problem(
        self,
        design_problem: Any,
        intent: Any,
        prompt: str,
        max_strategies: int = 3,
        client: Any = None,
        ai_state: Optional[Dict[str, Any]] = None,
    ) -> CompileResponse:
        """Helper to execute analysis, strategy generation, realization, and ranking for a DesignProblem."""
        if ai_state is None:
            ai_state = {"compiler_failed": False, "quota_exhausted": False, "failure_type": None}

        analysis = analyze_design_problem(design_problem)
        max_strats = min(max_strategies, 10)
        strategies = generate_strategies(analysis, problem=design_problem, max_strategies=max_strats)

        org_rules = get_catalog_organization_rules()
        realized_candidates: List[Tuple[DesignCandidate, DesignStrategy, RealizationResult]] = []

        for idx, strat in enumerate(strategies, start=1):
            cand_id = f"cand_{idx}_{strat.id}"
            cand = DesignCandidate(
                id=cand_id,
                source_strategy_id=strat.id,
                source_analysis_id=str(analysis.provenance.get("analysis_id", f"analysis-{design_problem.id}")),
                source_problem_id=design_problem.id,
                source_problem_version=design_problem.version,
                name=strat.name,
                selected_decisions=strat.decisions,
            )

            cand = organize_candidate(cand, org_rules, problem=design_problem)
            layout_plan = CandidateToLayoutAdapter.adapt(cand, design_problem, plan_id=f"plan-{cand_id}")

            if self.compile_blueprint_fn is not None:
                payload = SpatialCompilerBridge.plan_to_compiler_payload(layout_plan, problem=design_problem)
                comp_res = self.compile_blueprint_fn(payload)
                if comp_res.get("success", False):
                    realization_result = RealizationResult(
                        status=RealizationStatus.SUCCESS,
                        success=True,
                        candidate_id=cand_id,
                        layout_plan=layout_plan,
                        realized_geometry=comp_res,
                    )
                else:
                    err_msg = str(comp_res.get("error", "Optimization Constraint Solver Error: failed"))
                    status = SpatialCompilerBridge.classify_failure(err_msg)
                    realization_result = RealizationResult(
                        status=status,
                        success=False,
                        candidate_id=cand_id,
                        layout_plan=layout_plan,
                        error_message=err_msg,
                    )
            else:
                realization_result = SpatialCompilerBridge.realize_layout(layout_plan, problem=design_problem)

            realized_candidates.append((cand, strat, realization_result))

        candidates_list = [c[0] for c in realized_candidates]
        realizations_list = [c[2] for c in realized_candidates]

        strategic_rankings = AbstractStrategicScorer.score_candidates(candidates_list, design_problem)
        strategic_map = {r.candidate_id: r for r in strategic_rankings}

        spatial_rankings = SpatialRealizationScorer.score_realizations(candidates_list, realizations_list, design_problem)
        spatial_map = {r.candidate_id: r for r in spatial_rankings}

        scored_candidates: List[RankedCandidate] = []
        for cand, strat, real_res in realized_candidates:
            strat_rank = strategic_map.get(cand.id)
            spatial_rank = spatial_map.get(cand.id)
            strat_score = strat_rank.score_breakdown.total_score if strat_rank else 0.8
            spatial_score = spatial_rank.score_breakdown.total_score if spatial_rank else 0.0

            if strat_rank and spatial_rank:
                combined_breakdown = SpatialRealizationScorer.combine_score_breakdowns(
                    strat_rank.score_breakdown, spatial_rank.score_breakdown
                )
                comp_score = combined_breakdown.total_score
                sel_status = spatial_rank.selection_status
                reasons = list(spatial_rank.rejection_reasons)
                tb_key = spatial_rank.tie_break_key
            else:
                comp_score = round(0.5 * strat_score + 0.5 * spatial_score, 4)
                combined_breakdown = ScoreBreakdown(
                    criteria=[
                        CriterionScore(criterion_id="strategic", score=strat_score, weight=0.5, weighted_score=strat_score*0.5, explanation="Strategic fit", source_ids=[]),
                        CriterionScore(criterion_id="spatial", score=spatial_score, weight=0.5, weighted_score=spatial_score*0.5, explanation="Spatial score", source_ids=[]),
                    ],
                    total_score=comp_score,
                    scoring_version="3B.6-v1",
                )
                sel_status = SelectionStatus.VIABLE if real_res.success else SelectionStatus.REJECTED
                reasons = [] if real_res.success else [real_res.error_message or "Spatial realization failed"]
                tb_key = [comp_score, spatial_score, strat_score, cand.id]

            if not real_res.success:
                sel_status = SelectionStatus.REJECTED
                reasons = [f"Realization status: {real_res.status.value}"]
                tb_key = [0.0, 0.0, 0.0, cand.id]
            elif not (strat_rank and spatial_rank):
                sel_status = SelectionStatus.VIABLE
                reasons = []
                tb_key = [comp_score, spatial_score, strat_score, cand.id]

            scored_candidates.append(
                RankedCandidate(
                    candidate_id=cand.id,
                    strategy_id=strat.id,
                    rank=1,
                    selection_status=sel_status,
                    score_breakdown=combined_breakdown,
                    rejection_reasons=reasons,
                    tie_break_key=tb_key,
                    provenance={"problem_id": design_problem.id, "problem_version": design_problem.version},
                )
            )

        ranking_result = CandidateSelector.select(scored_candidates, max_selected=1)

        if not ranking_result.selected_candidate_ids:
            feasible_ranked = [r for r in ranking_result.ranked_candidates if r.selection_status != SelectionStatus.REJECTED]
            if not feasible_ranked:
                for _, _, real_res in realized_candidates:
                    if real_res.error_message and "Optimization Constraint Solver Error" in real_res.error_message:
                        raise OptimizationSolverError(
                            message="MILP solver failed to pack rooms under the requested constraints.",
                            detail=real_res.error_message,
                        )
                raise OptimizationSolverError(
                    message="All candidate strategies failed spatial optimization under the requested constraints.",
                    detail="No candidate could be spatially realized within plot envelope.",
                )
            winner_id = feasible_ranked[0].candidate_id
        else:
            winner_id = ranking_result.selected_candidate_ids[0]

        metadata = {
            "plot_width": intent.plot_width,
            "plot_depth": intent.plot_depth,
            "buildable_area_sqft": (intent.plot_width - 6.0) * (intent.plot_depth - intent.front_road_setback - 3.0),
            "ots_generated_count": 0,
        }
        session = self.registry.create_session(
            prompt=prompt,
            selected_candidate_id=winner_id,
            intent=intent.model_dump(),
            metadata=metadata,
        )

        rank_order_map = {r.candidate_id: r for r in ranking_result.ranked_candidates}
        winner_record: Optional[CandidateRecord] = None

        setbacks = {"left": 3.0, "right": 3.0, "bottom": intent.front_road_setback, "top": 3.0}
        payload = {
            "plot": {"width": intent.plot_width, "depth": intent.plot_depth},
            "setbacks": setbacks,
            "road_edge": "bottom",
            "grid_snap": 0.5,
            "floors": intent.floors,
        }

        for cand, strat, real_res in realized_candidates:
            is_winner = (cand.id == winner_id)
            r_info = rank_order_map.get(cand.id)
            rank = r_info.rank if r_info else 99
            comp_score = r_info.score_breakdown.total_score if r_info else 0.0

            compiler_res = real_res.realized_geometry or {}

            if is_winner and real_res.status == RealizationStatus.SUCCESS:
                _, drawing_svg = generate_drawing_svg_for_layout(payload, compiler_res)
                explanation_obj = self.explain_layout_fn(prompt, compiler_res, client, ai_state)
                if hasattr(explanation_obj, "model_dump"):
                    explanation_dict = explanation_obj.model_dump()
                elif isinstance(explanation_obj, dict):
                    explanation_dict = explanation_obj
                else:
                    explanation_dict = dict(explanation_obj)
            else:
                drawing_svg = None
                explanation_dict = {
                    "overview": f"Strategy: {strat.name}. Approach: {strat.approach}",
                    "space_allocation_reasoning": {},
                    "compliance_analysis": "Pending full presentation hydration.",
                    "zoning_rationale": "Pending full presentation hydration.",
                }

            trade_offs_str = [f"{t.explanation}" for t in strat.trade_offs] if strat.trade_offs else []

            cand_rec = CandidateRecord(
                candidate_id=cand.id,
                strategy_id=strat.id,
                name=strat.name,
                rank=rank,
                is_selected=is_winner,
                status=real_res.status.value,
                strategic_score=r_info.score_breakdown.criteria[0].score if r_info else 0.0,
                spatial_score=r_info.score_breakdown.criteria[1].score if r_info else 0.0,
                composite_score=comp_score,
                trade_offs=trade_offs_str,
                rejection_reasons=r_info.rejection_reasons if r_info else [],
                layout=compiler_res.get("layout", {}),
                boundaries=compiler_res.get("boundaries", {}),
                geometry=compiler_res.get("geometry", {}),
                floors=compiler_res.get("floors", {}),
                metrics=compiler_res.get("metrics", {}),
                drawing_svg=drawing_svg,
                explanation=explanation_dict,
            )

            self.registry.store_candidate(session.session_id, cand_rec)
            if is_winner:
                winner_record = cand_rec

        if not winner_record:
            raise OptimizationSolverError(
                message="Winning candidate presentation generation failed.",
                detail=f"Candidate '{winner_id}' could not be formatted.",
            )

        ranked_summaries = [
            CandidateSummary(
                candidate_id=c.candidate_id,
                strategy_id=c.strategy_id,
                name=c.name,
                rank=c.rank,
                is_selected=c.is_selected,
                composite_score=c.composite_score,
                strategic_score=c.strategic_score,
                spatial_score=c.spatial_score,
                feasibility_status=c.status,
                trade_offs=c.trade_offs,
                rejection_reasons=c.rejection_reasons,
            )
            for c in sorted(session.candidates.values(), key=lambda x: x.rank)
        ]

        return CompileResponse(
            session_id=session.session_id,
            selected_candidate_id=winner_id,
            ranked_alternatives=ranked_summaries,
            extracted_intent=intent.model_dump(),
            layout=winner_record.layout,
            boundaries=winner_record.boundaries,
            metadata=metadata,
            geometry=winner_record.geometry,
            floors=winner_record.floors,
            metrics=winner_record.metrics,
            drawing_svg=winner_record.drawing_svg or "",
            explanation=winner_record.explanation,
        )
