"""
Compiler & MILP Solver Bridge & Failure Handling Engine for Stage 3B.4D-5.

Bridges non-geometric SpatialLayoutPlan objects to the existing 2D building compiler
(compile_blueprint) and MILP optimization solver (solve_layout), providing a deterministic
failure classification and normalization layer across 6 realization statuses:
- SUCCESS
- INVALID_CANDIDATE
- UNSUPPORTED_SPEC
- SPATIALLY_INFEASIBLE
- SOLVER_TIMEOUT
- SOLVER_ERROR

STRICT REUSE BOUNDARY:
- MUST reuse existing compile_blueprint() and solve_layout() implementations.
- MUST NOT implement a new solver or duplicate MILP algorithms.
- ZERO architectural domain 'if dimension == ...' or 'if value == ...' branches.
"""

import re
from typing import Any

from app.schemas.design_problem import DesignProblem
from app.schemas.spatial_realization import (
    RealizationResult,
    RealizationStatus,
    SpatialLayoutPlan,
)
from app.services.compiler import serializer


def normalize_error_message(text: str) -> str:
    """
    Deterministically normalize error text by stripping memory addresses, file paths,
    and non-deterministic runtime tokens.
    """
    if not text:
        return "Unknown error"
    clean = str(text)
    clean = re.sub(r"0x[0-9a-fA-F]+", "<hex_addr>", clean)
    clean = re.sub(r"[A-Za-z]:\\[^\n\r:'\"]+", "<file_path>", clean)
    clean = re.sub(r"/\S+/\S+", "<file_path>", clean)
    return clean.strip()


class SpatialCompilerBridge:
    """
    Bridge service translating SpatialLayoutPlan to existing compiler payloads,
    executing 2D layout compilation and MILP optimization, and normalizing failures.
    """

    @classmethod
    def classify_failure(
        cls,
        error_msg: str,
        exc: Exception | None = None,
    ) -> RealizationStatus:
        """
        Generic, data-driven failure classifier.
        Uses exception types and error text patterns without domain branching.
        """
        if isinstance(exc, TimeoutError):
            return RealizationStatus.SOLVER_TIMEOUT

        err_lower = (error_msg or "").lower()

        if any(k in err_lower for k in ["timeout", "timelimit", "time limit", "exceeded time"]):
            return RealizationStatus.SOLVER_TIMEOUT
        if any(k in err_lower for k in ["infeasible", "unsolvable", "envelope overflow", "setback", "exceeds area", "cannot fit"]):
            return RealizationStatus.SPATIALLY_INFEASIBLE
        if any(k in err_lower for k in ["unsupported", "unknown spec", "invalid spec", "invalid room", "invalid plot", "unrepresentable", "translation failure"]):
            return RealizationStatus.UNSUPPORTED_SPEC
        if any(k in err_lower for k in ["invalid candidate", "missing candidate", "missing reference", "invalid reference", "topological"]):
            return RealizationStatus.INVALID_CANDIDATE

        return RealizationStatus.SOLVER_ERROR

    @classmethod
    def validate_plan_structure(cls, plan: SpatialLayoutPlan) -> tuple[bool, str]:
        """
        Generic pre-compilation structural validation.
        """
        if not plan or not isinstance(plan, SpatialLayoutPlan):
            return False, "Invalid candidate: Empty or invalid SpatialLayoutPlan object"

        if not plan.id or not plan.source_candidate_id:
            return False, "Invalid candidate: Missing required source candidate ID or layout plan ID"

        if plan.plot_width <= 0.0 or plan.plot_depth <= 0.0:
            return False, "Unsupported spec: Non-positive plot dimensions specified"

        for r in plan.rooms:
            if not r.id or r.target_area <= 0.0:
                return False, f"Unsupported spec: Invalid room target area or ID for room '{r.id}'"

        return True, ""

    @classmethod
    def plan_to_compiler_payload(
        cls,
        plan: SpatialLayoutPlan,
        problem: DesignProblem | None = None,
    ) -> dict[str, Any]:
        """
        Translate SpatialLayoutPlan into the dict payload expected by compile_blueprint().
        """
        valid, err = cls.validate_plan_structure(plan)
        if not valid:
            if "Unsupported spec" in err:
                raise ValueError(err)
            raise KeyError(err)

        plot_cfg = {
            "width": plan.plot_width,
            "depth": plan.plot_depth,
        }

        setbacks = {
            "left": plan.setbacks.get("left", 0.0),
            "right": plan.setbacks.get("right", 0.0),
            "bottom": plan.setbacks.get("bottom", 0.0),
            "top": plan.setbacks.get("top", 0.0),
        }

        stair_core_cfg = {"width": 8.0, "height": 10.0, "edge": "bottom-left"}
        for core in plan.cores:
            if core.core_type == "vertical_stairwell":
                break

        rooms_payload = []
        for r in plan.rooms:
            rooms_payload.append(
                {
                    "name": r.id,
                    "type": r.room_type,
                    "target_area": r.target_area,
                    "aspect_ratio_range": r.aspect_ratio_range,
                    "floor_assignment": r.floor_assignment,
                    "unit_id": r.unit_id,
                }
            )

        adjacencies_payload = []
        for adj in plan.adjacencies:
            adjacencies_payload.append((adj.source_space_id, adj.target_space_id))

        grid_snap = float(plan.realization_parameters.get("grid_snap", 0.5))
        time_limit_sec = int(plan.realization_parameters.get("time_limit_sec", 5))

        return {
            "plot": plot_cfg,
            "setbacks": setbacks,
            "stair_core": stair_core_cfg,
            "rooms": rooms_payload,
            "adjacencies": adjacencies_payload,
            "floors": plan.floors,
            "grid_snap": grid_snap,
            "time_limit_sec": time_limit_sec,
        }

    @classmethod
    def realize_layout(
        cls,
        plan: SpatialLayoutPlan,
        problem: DesignProblem | None = None,
    ) -> RealizationResult:
        """
        Execute 2D spatial layout realization for a SpatialLayoutPlan with structured
        failure normalization.
        """
        if not plan or not hasattr(plan, "id") or not plan.id:
            cand_id = getattr(plan, "source_candidate_id", "unknown") if plan else "unknown"
            return RealizationResult(
                status=RealizationStatus.INVALID_CANDIDATE,
                success=False,
                candidate_id=cand_id,
                error_message="Invalid candidate: Null or empty SpatialLayoutPlan provided",
                provenance={"compiler": "compile_blueprint", "source_candidate_id": cand_id},
            )

        provenance = dict(plan.provenance or {})
        provenance["compiler"] = "compile_blueprint"
        provenance["layout_plan_id"] = plan.id
        provenance["source_candidate_id"] = plan.source_candidate_id
        provenance["source_strategy_id"] = plan.source_strategy_id
        provenance["source_problem_id"] = plan.source_problem_id
        provenance["source_problem_version"] = plan.source_problem_version

        # 1. Structural plan validation
        cand_id = plan.source_candidate_id if (plan.source_candidate_id and plan.source_candidate_id.strip()) else "unknown"

        valid, val_err = cls.validate_plan_structure(plan)
        if not valid:
            status = (
                RealizationStatus.UNSUPPORTED_SPEC
                if "Unsupported spec" in val_err
                else RealizationStatus.INVALID_CANDIDATE
            )
            return RealizationResult(
                status=status,
                success=False,
                candidate_id=cand_id,
                layout_plan=plan if cand_id != "unknown" else None,
                error_message=normalize_error_message(val_err),
                provenance=provenance,
            )

        # 2. Payload translation
        try:
            payload = cls.plan_to_compiler_payload(plan, problem=problem)
        except Exception as exc:
            norm_msg = normalize_error_message(f"Translation failure: {exc}")
            status = cls.classify_failure(norm_msg, exc=exc)
            return RealizationResult(
                status=status,
                success=False,
                candidate_id=plan.source_candidate_id,
                layout_plan=plan,
                error_message=norm_msg,
                provenance=provenance,
            )

        # 3. Compiler & solver execution with exception handling
        try:
            compiler_res = serializer.compile_blueprint(payload)
        except Exception as exc:
            norm_msg = normalize_error_message(f"Compiler exception: {exc}")
            status = cls.classify_failure(norm_msg, exc=exc)
            return RealizationResult(
                status=status,
                success=False,
                candidate_id=plan.source_candidate_id,
                layout_plan=plan,
                error_message=norm_msg,
                infeasible_constraints=[norm_msg] if status == RealizationStatus.SPATIALLY_INFEASIBLE else [],
                provenance=provenance,
            )

        is_success = compiler_res.get("success", False)

        if is_success:
            return RealizationResult(
                status=RealizationStatus.SUCCESS,
                success=True,
                candidate_id=plan.source_candidate_id,
                layout_plan=plan,
                realized_geometry=compiler_res,
                provenance=provenance,
            )

        # 4. Result dictionary failure classification
        raw_err = str(compiler_res.get("error", "Unknown compilation failure"))
        norm_msg = normalize_error_message(raw_err)
        status = cls.classify_failure(norm_msg)

        return RealizationResult(
            status=status,
            success=False,
            candidate_id=plan.source_candidate_id,
            layout_plan=plan,
            error_message=norm_msg,
            infeasible_constraints=[norm_msg] if status == RealizationStatus.SPATIALLY_INFEASIBLE else [],
            provenance=provenance,
        )


def realize_spatial_layout(
    plan: SpatialLayoutPlan,
    problem: DesignProblem | None = None,
) -> RealizationResult:
    """Standalone functional wrapper for SpatialCompilerBridge."""
    return SpatialCompilerBridge.realize_layout(plan, problem=problem)
