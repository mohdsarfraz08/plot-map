"""
FastAPI endpoints for architectural compilation and on-demand candidate hydration.
Stage 3B.6: Downstream API Integration & Lazy Orchestration.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_gemini_client
from app.schemas.compile import (
    AlternateHydrationResponse,
    CompileRequest,
    CompileResponse,
)
from app.services.ai.explainer import explain_layout
from app.services.compiler.serializer import compile_blueprint
from app.services.orchestration import PipelineOrchestrator, get_session_registry

router = APIRouter()


@router.post("", response_model=CompileResponse, status_code=200)
def compile_layout(
    request: CompileRequest,
    client: Any = Depends(get_gemini_client),  # noqa: B008
) -> CompileResponse:
    """
    POST endpoint that takes a natural language description, executes the modular
    reasoning pipeline (Stage 1 through Stage 3B.5), and returns the winning
    blueprint alongside ranked alternative candidate summaries.
    """
    if not request.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt cannot be empty.",
        )

    ai_state = {
        "compiler_failed": False,
        "quota_exhausted": False,
        "failure_type": None,
    }

    orchestrator = PipelineOrchestrator(
        session_registry=get_session_registry(),
        compile_blueprint_fn=compile_blueprint,
        explain_layout_fn=explain_layout,
    )
    return orchestrator.compile(request, client=client, ai_state=ai_state)


@router.get("/candidate/{session_id}/{candidate_id}", response_model=AlternateHydrationResponse, status_code=200)
def get_candidate_hydration(
    session_id: str,
    candidate_id: str,
    client: Any = Depends(get_gemini_client),  # noqa: B008
) -> AlternateHydrationResponse:
    """
    GET endpoint that hydrates full presentation assets (2D CAD SVG, layout geometry, metrics)
    for a specific alternate candidate from an active in-memory compilation session without
    re-running parsing, strategy generation, or MILP layout optimization.
    """
    orchestrator = PipelineOrchestrator(
        session_registry=get_session_registry(),
        compile_blueprint_fn=compile_blueprint,
        explain_layout_fn=explain_layout,
    )
    result = orchestrator.hydrate_candidate(session_id, candidate_id, client=client)

    if not result.get("success", False):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.get("error", "Candidate or session not found."),
        )

    return AlternateHydrationResponse.model_validate(result)
