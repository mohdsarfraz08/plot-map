import os
import json
import instructor
from app.core.config import settings

gemini_key = os.environ.get("GEMINI_API_KEY") or settings.GEMINI_API_KEY
if gemini_key:
    os.environ["GEMINI_API_KEY"] = gemini_key

from app.api.dependencies import get_gemini_client
from app.schemas.compile import CompileRequest
from app.services.orchestration import PipelineOrchestrator, get_session_registry
from app.services.ai.parser import parse_requirements, parse_requirements_fallback
from app.services.compiler.intent_adapter import to_design_problem
from app.services.analysis.architectural_analyzer import analyze_design_problem
from app.services.analysis.strategy_generator import generate_strategies
from app.services.analysis.candidate_organizer import organize_candidate
from app.services.analysis.catalog_loader import get_catalog_organization_rules
from app.services.analysis.spatial_adapter import CandidateToLayoutAdapter
from app.schemas.design_candidate import DesignCandidate
from app.services.realization.compiler_bridge import SpatialCompilerBridge
from app.services.compiler.serializer import compile_blueprint

prompt = "I want one shared staircase for all families. 40x40 plot, G+1 house, 2 families, 2 bedrooms and kitchen."

print("==================================================")
print("COMPARING NON-LLM vs LLM PIPELINE EXECUTION")
print("Prompt:", prompt)
print("==================================================")

client = None
if gemini_key:
    try:
        client = instructor.from_provider(
            model="google/gemini-2.5-flash",
            api_key=gemini_key,
        )
    except Exception as e:
        print(f"Warning: Could not initialize Gemini client: {e}")

def run_pipeline(use_llm: bool):
    print(f"\n>>>>>>>>>>>> RUNNING (use_llm={use_llm}) <<<<<<<<<<<<")
    cl = client if use_llm else None
    
    # 1. Intent
    intent = parse_requirements(prompt, client=cl)
    print("\n--- 1. PARSED INTENT ---")
    print(json.dumps(intent.model_dump(), indent=2))
    
    # 2. DesignProblem
    problem = to_design_problem(intent)
    print("\n--- 2. DESIGN PROBLEM ---")
    print(f"Problem ID: {problem.id}, Plot: {problem.site.plot_width}x{problem.site.plot_depth}, Floors: {problem.site.floors}")
    print(f"Spaces: {[s.id + '(' + s.room.room_type.value + ', owner=' + str(s.owner_id) + ', qty=' + str(s.quantity) + ')' for s in problem.spaces]}")
    print(f"User groups: {[ug.id for ug in problem.user_groups]}")
    print(f"Requirements: {[r.id + ':' + r.kind.value for r in problem.requirements]}")
    
    # 3. Architectural Analysis
    analysis = analyze_design_problem(problem)
    print("\n--- 3. ARCHITECTURAL ANALYSIS ---")
    print(f"Fixed decisions: {[f'{d.dimension}={d.value}' for d in analysis.fixed_decisions]}")
    print(f"Flexible decisions: {[f'{d.dimension}' for d in analysis.flexible_decisions]}")
    print(f"Organization rules: {[r.id for r in analysis.organization_rules]}")
    
    # 4. Strategies
    strategies = generate_strategies(analysis, problem=problem, max_strategies=3)
    print("\n--- 4. STRATEGIES ---")
    for s in strategies:
        print(f"Strategy: {s.id} - {s.name} - decisions: {[f'{d.dimension}={d.value}' for d in s.decisions]}")
        
    # 5. Candidate 1 Organization & Spatial Realization
    if strategies:
        strat = strategies[0]
        cand = organize_candidate(
            DesignCandidate(
                id="cand_1",
                source_strategy_id=strat.id,
                source_analysis_id="test",
                source_problem_id=problem.id,
                source_problem_version=1,
                name=strat.name,
                selected_decisions=strat.decisions,
            ),
            get_catalog_organization_rules(),
            problem=problem,
        )
        print("\n--- 5. ORGANIZED CANDIDATE ---")
        print(f"Candidate floor_organization: {cand.floor_organization}")
        print(f"Candidate unit_organization: {cand.unit_organization}")
        print(f"Candidate circulation_intent: {[c.model_dump() for c in cand.circulation_intent]}")
        print(f"Candidate service_organization: {[s.model_dump() for s in cand.service_organization]}")
        
        # 6. Spatial Layout Plan
        layout_plan = CandidateToLayoutAdapter.adapt(cand, problem, plan_id="plan-cand_1")
        print("\n--- 6. SPATIAL LAYOUT PLAN ---")
        print(f"Floors count: {layout_plan.floors}, Room floor assignments: {[(r.id, r.floor_assignment) for r in layout_plan.rooms]}")
        print(f"Vertical cores: {[c.model_dump() for c in layout_plan.cores]}")
        
        # 7. Payload for compiler / MILP
        payload = SpatialCompilerBridge.plan_to_compiler_payload(layout_plan, problem=problem)
        print("\n--- 7. COMPILER/MILP PAYLOAD ---")
        print(f"Payload plot: {payload.get('plot')}")
        print(f"Payload floors: {payload.get('floors')}")
        print(f"Payload rooms count: {len(payload.get('rooms', []))}")
        print(f"Payload rooms: {payload.get('rooms')}")
        print(f"Payload stair_location: {payload.get('stair_location')}")
        
        # 8. Spatial Realization
        comp_res = compile_blueprint(payload)
        print("\n--- 8. COMPILED BLUEPRINT RESULT ---")
        print(f"Success: {comp_res.get('success')}")
        print(f"Error: {comp_res.get('error')}")
        print(f"Floors data keys: {list(comp_res.get('floors_data', {}).keys())}")
        for fl_k, fl_v in comp_res.get('floors_data', {}).items():
            print(f"  Floor {fl_k} rooms in layout: {list(fl_v.get('layout', {}).keys())}")
            print(f"  Floor {fl_k} walls count: {len(fl_v.get('geometry', {}).get('walls', []))}")
            print(f"  Floor {fl_k} corridors count: {len(fl_v.get('geometry', {}).get('corridors', []))}")
            print(f"  Floor {fl_k} doors count: {len(fl_v.get('geometry', {}).get('doors', []))}")
        print(f"Boundaries stair_core: {comp_res.get('boundaries', {}).get('stair_core')}")
        
    return intent

run_pipeline(use_llm=False)
run_pipeline(use_llm=True)
