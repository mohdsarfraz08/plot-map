import pytest
from app.schemas.compile import CompileRequest
from app.services.orchestration import PipelineOrchestrator, SessionRegistry


def test_requirement_modification_loop_end_to_end():
    registry = SessionRegistry()
    orchestrator = PipelineOrchestrator(session_registry=registry)

    # Initial: Shared stair, G+1
    initial_prompt = "40x40 G+1 house for two families with shared staircase."
    res_a = orchestrator.compile(CompileRequest(prompt=initial_prompt))
    assert res_a.selected_candidate_id is not None
    assert res_a.extracted_intent.get("vertical_circulation") == "shared"
    assert "1" in res_a.floors and "2" in res_a.floors
    assert len(res_a.floors["1"].get("layout", {})) > 0
    assert len(res_a.floors["2"].get("layout", {})) > 0

    # Delta 1: Private access
    delta_1 = "Change the requirement: each family should have private access."
    res_b = orchestrator.recompile_with_delta(res_a.session_id, delta_1)
    assert res_b.session_id != res_a.session_id
    assert res_b.extracted_intent.get("vertical_circulation") == "independent"
    assert "1" in res_b.floors and "2" in res_b.floors

    # Delta 2: All families on ground floor
    delta_2 = "Now put all families on the ground floor."
    res_c = orchestrator.recompile_with_delta(res_b.session_id, delta_2)
    assert res_c.session_id != res_b.session_id
    assert res_c.extracted_intent.get("floor_allocation") == "ground_floor_only"
    user_rooms_fl1 = [k for k in res_c.floors["1"].get("layout", {}) if not k.startswith("OTS")]
    assert len(user_rooms_fl1) == 4
    assert len(res_c.floors.get("2", {}).get("layout", {})) == 0
