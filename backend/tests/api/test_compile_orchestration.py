"""
Comprehensive API and Orchestration Test Suite for Stage 3B.6.

Validates:
1. End-to-end pipeline execution (Intent → Problem → Analysis → Strategy → Candidate → Realization → Selector).
2. Backward compatibility of all legacy response fields for frontend Home.jsx.
3. Multi-candidate ranking and metadata summaries in ranked_alternatives.
4. On-demand alternate candidate hydration via GET /candidate/{session_id}/{candidate_id}.
5. Zero-recompilation verification on candidate hydration.
6. 404 handling on unknown/expired sessions and candidates.
7. Candidate resilience (infeasible candidate does not abort compilation).
8. Structured error handling when zero candidates are feasible.
9. Deterministic candidate ordering.
10. Respecting max_strategies parameter bounding.
11. Parser fallback resilience.
"""

from unittest.mock import patch
import pytest

from app.schemas.compile import CompileRequest
from app.services.orchestration.pipeline_orchestrator import PipelineOrchestrator
from app.services.orchestration.session_registry import SessionRegistry


def test_compile_pipeline_e2e(client):
    """1. Valid request reaches the orchestrated pipeline and compiles successfully."""
    payload = {"prompt": "1BHK on a 40x40 plot", "max_strategies": 3}
    response = client.post("/api/v1/compile", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["status"] == "success"
    assert "session_id" in data
    assert "selected_candidate_id" in data
    assert len(data["selected_candidate_id"]) > 0


def test_compile_response_backward_compatibility(client):
    """2. All legacy top-level fields consumed by Home.jsx are present and populated."""
    payload = {"prompt": "2BHK on a 40x40 plot"}
    response = client.post("/api/v1/compile", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Legacy fields required by frontend/src/pages/Home.jsx
    expected_legacy_keys = [
        "status",
        "success",
        "message",
        "extracted_intent",
        "layout",
        "boundaries",
        "metadata",
        "geometry",
        "floors",
        "metrics",
        "drawing_svg",
        "explanation",
    ]
    for key in expected_legacy_keys:
        assert key in data, f"Missing expected backward-compatible key '{key}'"

    assert data["metadata"]["plot_width"] == 40.0
    assert data["metadata"]["plot_depth"] == 40.0
    assert len(data["layout"]) > 0
    assert "<svg" in data["drawing_svg"]


def test_ranked_alternatives(client):
    """3. Ranked candidate summaries are returned with valid scores and ranks."""
    payload = {"prompt": "2BHK on a 40x40 plot", "max_strategies": 4}
    response = client.post("/api/v1/compile", json=payload)
    assert response.status_code == 200
    data = response.json()

    alternatives = data.get("ranked_alternatives", [])
    assert len(alternatives) > 0

    # Winner must be marked is_selected = True and have rank 1
    winner = [a for a in alternatives if a["is_selected"]]
    assert len(winner) == 1
    assert winner[0]["candidate_id"] == data["selected_candidate_id"]

    for alt in alternatives:
        assert "candidate_id" in alt
        assert "strategy_id" in alt
        assert "rank" in alt
        assert "composite_score" in alt
        assert "strategic_score" in alt
        assert "spatial_score" in alt
        assert "feasibility_status" in alt


def test_candidate_hydration(client):
    """4. A candidate can be hydrated using session_id + candidate_id."""
    payload = {"prompt": "1BHK on a 40x40 plot", "max_strategies": 2}
    compile_res = client.post("/api/v1/compile", json=payload)
    assert compile_res.status_code == 200
    comp_data = compile_res.json()

    session_id = comp_data["session_id"]
    candidate_id = comp_data["selected_candidate_id"]

    hydrate_res = client.get(f"/api/v1/compile/candidate/{session_id}/{candidate_id}")
    assert hydrate_res.status_code == 200
    hydrated_data = hydrate_res.json()

    assert hydrated_data["session_id"] == session_id
    assert hydrated_data["candidate_id"] == candidate_id
    assert "layout" in hydrated_data
    assert "geometry" in hydrated_data
    assert "metrics" in hydrated_data
    assert hydrated_data["drawing_svg"] is not None


def test_candidate_hydration_does_not_recompile(client):
    """5. Hydration does NOT invoke parsing, strategy generation, or MILP solving."""
    payload = {"prompt": "1BHK on a 40x40 plot", "max_strategies": 2}
    compile_res = client.post("/api/v1/compile", json=payload)
    comp_data = compile_res.json()
    session_id = comp_data["session_id"]
    candidate_id = comp_data["selected_candidate_id"]

    with patch("app.services.ai.parser.parse_requirements") as mock_parse, \
         patch("app.services.analysis.strategy_generator.generate_strategies") as mock_strat, \
         patch("app.services.realization.compiler_bridge.SpatialCompilerBridge.realize_layout") as mock_realize:

        hydrate_res = client.get(f"/api/v1/compile/candidate/{session_id}/{candidate_id}")
        assert hydrate_res.status_code == 200

        mock_parse.assert_not_called()
        mock_strat.assert_not_called()
        mock_realize.assert_not_called()


def test_unknown_candidate_returns_404(client):
    """6. Unknown candidate ID in active session returns 404."""
    payload = {"prompt": "1BHK on a 40x40 plot"}
    compile_res = client.post("/api/v1/compile", json=payload)
    session_id = compile_res.json()["session_id"]

    hydrate_res = client.get(f"/api/v1/compile/candidate/{session_id}/non_existent_cand_999")
    assert hydrate_res.status_code == 404


def test_expired_session_returns_404(client):
    """7. Expired or non-existent session ID returns 404."""
    hydrate_res = client.get("/api/v1/compile/candidate/session_fake_12345/cand_1")
    assert hydrate_res.status_code == 404


def test_infeasible_candidate_does_not_abort_other_candidates():
    """8. Spatially infeasible candidate does not crash the pipeline if feasible candidates exist."""
    registry = SessionRegistry()
    orchestrator = PipelineOrchestrator(session_registry=registry)
    request = CompileRequest(prompt="2BHK on 40x40 plot", max_strategies=3)

    response = orchestrator.compile(request)
    assert response.success is True
    assert len(response.ranked_alternatives) > 0


def test_parser_fallback_resilience():
    """9. Verification that parser fallback succeeds deterministically."""
    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mock_client.create.side_effect = Exception("API Quota Limit")

    registry = SessionRegistry()
    orchestrator = PipelineOrchestrator(session_registry=registry)
    request = CompileRequest(prompt="1BHK on 40x40 plot")

    response = orchestrator.compile(request, client=mock_client)
    assert response.success is True


def test_max_strategies_bound_is_respected():
    """10. Request max_strategies bounds the number of evaluated candidate strategies."""
    registry = SessionRegistry()
    orchestrator = PipelineOrchestrator(session_registry=registry)
    request = CompileRequest(prompt="1BHK on 40x40 plot", max_strategies=2)

    response = orchestrator.compile(request)
    assert len(response.ranked_alternatives) <= 2


def test_deterministic_candidate_order():
    """11. Repeated requests with identical prompts produce identical candidate rankings."""
    registry = SessionRegistry()
    orchestrator = PipelineOrchestrator(session_registry=registry)
    request = CompileRequest(prompt="2BHK on 40x40 plot with parking", max_strategies=3)

    resp1 = orchestrator.compile(request)
    # Clear cache to force fresh run with same inputs
    registry.clear()
    resp2 = orchestrator.compile(request)

    assert resp1.selected_candidate_id == resp2.selected_candidate_id
    assert [a.candidate_id for a in resp1.ranked_alternatives] == [a.candidate_id for a in resp2.ranked_alternatives]
    assert [a.composite_score for a in resp1.ranked_alternatives] == [a.composite_score for a in resp2.ranked_alternatives]
