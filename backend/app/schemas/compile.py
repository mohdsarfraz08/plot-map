"""
Pydantic schemas for Stage 3B.6 Compile Orchestration and Candidate Hydration.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CompileRequest(BaseModel):
    """Request model containing the unstructured natural language prompt from the user."""
    prompt: str = Field(..., description="Natural language prompt describing architectural requirements.")
    max_strategies: int = Field(default=4, ge=1, le=10, description="Maximum number of strategies to explore and rank.")


class CandidateSummary(BaseModel):
    """Lightweight metadata summary of a ranked design candidate for UI cards/alternatives."""
    candidate_id: str
    strategy_id: str
    name: str
    rank: int
    is_selected: bool
    composite_score: float
    strategic_score: float
    spatial_score: float
    feasibility_status: str  # "feasible", "spatially_infeasible", "rejected"
    trade_offs: List[str] = Field(default_factory=list)
    rejection_reasons: List[str] = Field(default_factory=list)


class CompileResponse(BaseModel):
    """
    Unified response schema preserving 100% backward compatibility for existing frontend
    while delivering multi-candidate ranking and session metadata for lazy loading.
    """
    status: str = "success"
    success: bool = True
    message: str = "Layout compiled successfully."

    # Stage 3B.6 Additive Orchestration Fields
    session_id: str
    selected_candidate_id: str
    ranked_alternatives: List[CandidateSummary] = Field(default_factory=list)

    # Legacy Fields (100% backward compatibility for Home.jsx)
    extracted_intent: Dict[str, Any] = Field(default_factory=dict)
    layout: Dict[str, Any] = Field(default_factory=dict)
    boundaries: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    geometry: Dict[str, Any] = Field(default_factory=dict)
    floors: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    render_tree: Dict[str, Any] = Field(default_factory=dict)
    drawing_svg: str = ""
    explanation: Dict[str, Any] = Field(default_factory=dict)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class AlternateHydrationResponse(BaseModel):
    """Response returned when fetching heavy presentation assets for a specific candidate."""
    session_id: str
    candidate_id: str
    strategy_id: str
    name: str
    rank: int
    is_selected: bool
    status: str
    layout: Dict[str, Any] = Field(default_factory=dict)
    boundaries: Dict[str, Any] = Field(default_factory=dict)
    geometry: Dict[str, Any] = Field(default_factory=dict)
    floors: Dict[str, Any] = Field(default_factory=dict)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    drawing_svg: Optional[str] = None
    explanation: Dict[str, Any] = Field(default_factory=dict)
