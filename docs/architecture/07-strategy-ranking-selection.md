# BuildForgeAI Architecture — Strategy Ranking & Candidate Selection Specification

**Phase**: 3 — Architectural Reasoning / Phase 6 — Optimization & Ranking  
**Stage**: Stage 3B.5 — Strategy Ranking & Candidate Selection  
**Document Status**: Canonical Architecture Specification — Stage 3B.5 Planned  

---

## 1. Purpose

Stage **3B.5 (Strategy Ranking & Candidate Selection)** defines the computational architecture for evaluating, scoring, ordering, and selecting architectural alternatives generated upstream by `StrategyGenerator`, `CandidateGenerator`, `CandidateOrganizer`, and realized downstream by `CandidateToLayoutAdapter` and `SpatialCompilerBridge`.

```text
Architectural Pipeline:
DesignProblem → ArchitecturalAnalysis → DesignStrategy → DesignCandidate → CandidateOrganizer
                                                                                │
                                                                                ▼
Phase 1 Abstract Strategic Scorer ◄─────────────────────────── [STAGE 3B.5 BOUNDARY]
                                                                                │
                                                                                ▼
                                                                     SpatialLayoutPlan
                                                                                │
                                                                                ▼
                                                                     SpatialCompilerBridge
                                                                                │
                                                                                ▼
Phase 2 Spatial Realization Scorer ◄───────────────────────── RealizationResult / Geometry
                                                                                │
                                                                                ▼
                                                                  CandidateSelector & Ranks
```

### Key Architectural Distinctions:
1. **Strategy Generation (`StrategyGenerator`)**: Explores the space of conceptual architectural approaches based on decision dimensions and trade-offs.
2. **Candidate Generation (`CandidateGenerator`)**: Instantiates concrete structural decision combinations for a given strategy.
3. **Candidate Organization (`CandidateOrganizer`)**: Applies declarative spatial organization rules (floor assignments, unit containers, circulation nodes, service stacks).
4. **Spatial Realization (`CandidateToLayoutAdapter` & `SpatialCompilerBridge`)**: Translates candidates into non-geometric spatial layout plans and solves 2D geometric room placements via existing MILP solvers.
5. **Strategy Ranking (`AbstractStrategicScorer` & `SpatialRealizationScorer`)**: Evaluates already-generated strategies and candidates against multi-criteria objective functions and client preferences.
6. **Candidate Selection (`CandidateSelector`)**: Applies filtering thresholds, Pareto optimality selection, and deterministic tie-breaking to pick authoritative architectural candidate(s).

**Core Principle**: Stage 3B.5 DOES NOT invent new strategies or alter candidate structures. It evaluates already-generated alternatives deterministically.

---

## 2. Input Contracts

Stage 3B.5 consumes structured data contracts produced by upstream reasoning and spatial realization layers.

### 1. Authoritative Inputs:
- **`DesignCandidate`**: The candidate instance being evaluated, containing `selected_decisions`, `floor_organization`, `unit_organization`, `circulation_intent`, `service_organization`, `unresolved_decisions`, `assumptions`, `risks`, `feasibility_expectation`, and `confidence`.
- **`DesignStrategy`**: The originating strategy, providing strategic rationale, `trade_offs`, `dependencies`, `requirements_satisfied`, `constraints_addressed`, `preferences_supported`, and `objectives_targeted`.
- **`DesignProblem`**: The primary problem contract, providing site boundaries (`site`), room requirements (`spaces`), constraints (`constraints`), soft preferences (`preferences`), and optimization direction (`objectives`).

### 2. Optional / Realization Inputs:
- **`SpatialLayoutPlan`**: Non-geometric spatial plan produced by `CandidateToLayoutAdapter`, detailing room specs, aspect bounds, adjacencies, and core specs.
- **`RealizationResult`**: Downstream realization output from `SpatialCompilerBridge`, providing realization `status` (`SUCCESS`, `SPATIALLY_INFEASIBLE`, etc.), `realized_geometry`, `infeasible_constraints`, and execution parameters.

### 3. Advisory & Metadata Inputs:
- **`ArchitecturalAnalysis`**: Upstream analysis context detailing identified fixed/flexible decision dimensions, conflicts, and uncertainties.
- **`Provenance Metadata`**: Source lineage tracking IDs (`source_problem_id`, `source_strategy_id`, `source_analysis_id`, `candidate_id`, `layout_plan_id`).

> [!NOTE]
> All existing schemas (`DesignStrategy`, `DesignCandidate`, `DesignProblem`, `SpatialLayoutPlan`, `RealizationResult`) remain 100% unchanged. Stage 3B.5 consumes these objects read-only.

---

## 3. Ranking Output Contract

Stage 3B.5 introduces conceptual output contracts for structured evaluation results. (To be formally implemented in `backend/app/schemas/strategy_ranking.py` during Sub-stage 3B.5-1).

### Proposed Conceptual Schemas:

```python
class SelectionStatus(str, Enum):
    SELECTED = "selected"          # Top-ranked, fully viable candidate recommended for design output
    VIABLE = "viable"              # High-scoring alternative satisfying all hard constraints
    MARGINAL = "marginal"          # Low-scoring candidate with unresolved trade-offs or soft penalties
    REJECTED = "rejected"          # Infeasible or policy-violating candidate excluded from selection


class CriterionScore(BaseModel):
    criterion_id: str              # Unique criterion identifier (e.g. program_area_satisfaction)
    criterion_name: str            # Human-readable name
    raw_score: float               # Unweighted score normalized to [0.0, 1.0]
    weight: float                  # Configured weight in [0.0, 1.0]
    weighted_score: float          # raw_score * weight
    evaluation_reason: str         # Deterministic explanation of score derivation
    source_dimension: str | None   # Decision dimension or requirement ID linked to evaluation


class ScoreBreakdown(BaseModel):
    total_score: float             # Sum of weighted scores in [0.0, 1.0]
    strategic_score: float         # Phase 1 abstract strategic score in [0.0, 1.0]
    spatial_score: float           # Phase 2 spatial realization score in [0.0, 1.0]
    criteria_scores: list[CriterionScore]  # Detailed breakdown per criterion


class RankedCandidate(BaseModel):
    rank: int                      # 1-indexed overall rank (1 = best)
    candidate_id: str              # Unique DesignCandidate ID
    strategy_id: str               # Originating DesignStrategy ID
    selection_status: SelectionStatus  # Categorical selection status
    score_breakdown: ScoreBreakdown    # Multi-criteria score details
    rejection_reasons: list[str]   # Explicit reasons if status == REJECTED
    tie_break_provenance: str      # Deterministic tie-breaking rationale string
    provenance: dict[str, Any]     # Lineage metadata


class RankingResult(BaseModel):
    id: str                        # Unique ranking execution ID
    source_problem_id: str         # Target DesignProblem ID
    source_problem_version: int    # Target DesignProblem version
    ranked_candidates: list[RankedCandidate]  # Ranked candidates ordered from best to worst
    selected_candidate_ids: list[str]         # Candidate IDs chosen for final execution
    ranking_parameters: dict[str, Any]        # Weights and preference catalog configuration used
    provenance: dict[str, Any]     # Execution metadata
```

---

## 4. Ranking vs. Selection

Stage 3B.5 enforces a strict conceptual distinction between **Ranking** and **Selection**:

```text
               Candidates Pool [C1, C2, C3, C4, C5]
                                │
                                ▼
                       Multi-Criteria Scorer
                                │
                                ▼
         Ordered Ranks: [Rank 1: C3, Rank 2: C1, Rank 3: C4, Rank 4: C2, Rank 5: C5]
                                │
                                ▼
                     CandidateSelector Filter
        (Applies selection thresholds, Pareto bounds, & max count)
                                │
                                ▼
              Selected Candidates: [C3 (Primary), C1 (Alternative)]
```

1. **Ranking**: Computes quantitative scores for all evaluated candidates and orders them deterministically from highest to lowest score (Rank 1, Rank 2, ... Rank N). Every valid candidate receives a rank regardless of whether it is selected.
2. **Selection**: Evaluates ranked candidates against selection rules (e.g. `min_score_threshold = 0.6`, `max_selected_count = 2`, Pareto dominance bounds) to mark specific candidates as `SELECTED`, `VIABLE`, `MARGINAL`, or `REJECTED`. Selection determines which candidate designs proceed to downstream 2D/3D rendering or user presentation.

---

## 5. Two-Phase Ranking Architecture

To ensure high computational efficiency and eliminate unnecessary solver calls, Stage 3B.5 adopts a **Two-Phase Ranking Architecture**:

```text
Phase 1: Abstract Strategic Ranking (Fast Pre-Realization Filter)
DesignCandidate + DesignStrategy + DesignProblem ──► AbstractStrategicScorer ──► Strategic Score (S_abstract)
                                                                                       │
                                                                                       ▼
                                                                     [Is S_abstract >= threshold?]
                                                                         │                   │
                                                                      YES│                   │NO
                                                                         ▼                   ▼
Phase 2: Spatial Realization Scorer (Post-MILP Solver)            Spatial Realization    Status: REJECTED / MARGINAL
SpatialLayoutPlan + RealizationResult ─────────────► SpatialRealizationScorer  Bypassed      Score: S_abstract Only
                                                             │
                                                             ▼
                                                    Total Combined Score
```

### Phase 1 — Abstract Strategic Ranking:
- **Input**: `DesignCandidate`, `DesignStrategy`, `DesignProblem`, `ArchitecturalAnalysis`.
- **Timing**: Executes **BEFORE** 2D spatial layout realization.
- **Cost**: $O(N)$ fast non-geometric evaluation (microseconds).
- **Evaluates**:
  - Program requirement coverage (`requirements_satisfied`).
  - Constraint satisfaction (`constraints_addressed`).
  - Preference alignment (`preferences_supported`).
  - Known strategy risk severity and assumption count.
  - Qualitative feasibility expectation (`EXPECTED_FEASIBLE` vs `CONDITIONALLY_FEASIBLE`).
- **Pruning**: Low-scoring or strategically blocked candidates can be pruned before invoking expensive MILP solvers.

### Phase 2 — Spatial Realization Ranking:
- **Input**: `SpatialLayoutPlan`, `RealizationResult`.
- **Timing**: Executes **AFTER** `SpatialCompilerBridge.realize_layout()`.
- **Cost**: Evaluates optimization output metrics post-realization.
- **Evaluates**:
  - Realization feasibility status (`SUCCESS` vs `SPATIALLY_INFEASIBLE` / `SOLVER_TIMEOUT`).
  - Program area efficiency (ratio of actual room area to target area).
  - Vertical service core stacking alignment across multi-floor plans.
  - Circulation core accessibility efficiency.
  - Room aspect ratio compactness.

---

## 6. Scoring Model & Evaluation Criteria

Candidates are scored using a normalized, multi-criteria weighted additive model:

$$S_{\text{total}} = w_{\text{abstract}} \cdot S_{\text{abstract}} + w_{\text{spatial}} \cdot S_{\text{spatial}}$$

Where each sub-score is derived from weighted criteria:

$$S = \sum_{i=1}^{K} w_i \cdot s_i, \quad \text{with } \sum_{i=1}^{K} w_i = 1.0, \quad s_i \in [0.0, 1.0]$$

### Evaluation Criteria Categories:

| Criteria Category | Phase | Weight Default | Evaluation Description |
|---|---|---|---|
| **Program Usability & Area Satisfaction** | Phase 1 & 2 | `0.25` | Ratio of provided room areas and space types against requested `DesignProblem.spaces`. Penalizes missing spaces or extreme area deviations. |
| **Privacy & User Isolation Compliance** | Phase 1 | `0.20` | Compliance of unit organization (`unit_organization`) and circulation access type (`shared` vs `independent`) with user privacy requirements. |
| **Circulation Efficiency & Access** | Phase 1 & 2 | `0.15` | Evaluation of vertical circulation cores (`circulation_intent`), accessibility topology, and minimization of wasted circulation area. |
| **Structural & Service Core Stacking** | Phase 1 & 2 | `0.15` | Alignment of plumbing wet cores (`service_organization`) across floors to ensure vertical stacking efficiency. |
| **Realization Feasibility & Solver Confidence** | Phase 1 & 2 | `0.15` | Realization status (`SUCCESS` = 1.0, `SPATIALLY_INFEASIBLE` = 0.0) combined with strategy feasibility expectation and confidence score. |
| **Objective & Preference Alignment** | Phase 1 | `0.10` | Degree to which strategy targets soft preferences and optimization objectives defined in `DesignProblem`. |

---

## 7. Deterministic Scoring & Tie-Breaking Rules

Ranking must be **100% deterministic**. Given identical inputs, N executions MUST yield identical candidate ranks, scores, and breakdowns.

### Deterministic Rules:
1. **Fixed Precision Arithmetic**: Floating-point scores are rounded deterministically to 6 decimal places (`round(score, 6)`) to eliminate cross-platform float drift.
2. **Lexicographical Tie-Breaking Hierarchy**: When two candidates produce identical total scores ($S_{\text{total}}$), ties are broken deterministically by evaluating the following strict priority cascade:
   - Priority 1: Realization Status (`SUCCESS` > `SOLVER_TIMEOUT` > `SPATIALLY_INFEASIBLE` > `INVALID_CANDIDATE`).
   - Priority 2: Higher Program Usability Score ($s_{\text{usability}}$).
   - Priority 3: Higher Realization Feasibility Score ($s_{\text{feasibility}}$).
   - Priority 4: Higher Strategic Confidence (`candidate.confidence`).
   - Priority 5: Lexicographical sorting of Candidate ID (`candidate.id`).

Every tie-break event records its decision path in `RankedCandidate.tie_break_provenance`.

---

## 8. Data-Driven Preference Catalog Integration

Following the architectural pattern established in 3B.3C (`decision_catalog.json`) and 3B.4C (`CandidateOrganizer`), Stage 3B.5 MUST store scoring weights, preference rules, and evaluation criteria declaratively in a catalog file:

**`backend/app/services/analysis/preference_catalog.json`**

```json
{
  "version": "1.0.0",
  "weights": {
    "program_usability": 0.25,
    "privacy_compliance": 0.20,
    "circulation_efficiency": 0.15,
    "service_stacking": 0.15,
    "realization_feasibility": 0.15,
    "objective_alignment": 0.10
  },
  "selection_thresholds": {
    "min_selected_score": 0.60,
    "max_selected_candidates": 3
  },
  "criteria_definitions": [
    {
      "id": "privacy_compliance",
      "name": "Privacy & Unit Isolation Compliance",
      "phase": "abstract",
      "evaluator": "unit_isolation_evaluator",
      "parameters": {
        "independent_bonus": 0.2,
        "shared_circulation_penalty": 0.1
      }
    }
  ]
}
```

Loaded via `catalog_loader.py`. The scoring engine evaluates criteria dynamically using parameters from `preference_catalog.json` with **ZERO domain-specific `if/elif` Python branches**.

---

## 9. Provenance & Score Breakdown

Every `RankedCandidate` output maintains complete auditability:
- **`score_breakdown`**: Contains an explicit list of `CriterionScore` objects documenting `raw_score`, `weight`, `weighted_score`, and human-readable `evaluation_reason`.
- **`provenance`**: Preserves originating lineage identifiers (`source_problem_id`, `source_problem_version`, `source_analysis_id`, `source_strategy_id`, `candidate_id`, `layout_plan_id`).

---

## 10. Failure & Rejection Handling

Stage 3B.5 handles realization failures and infeasible candidates gracefully without throwing unhandled exceptions:

1. **Infeasible Realization Results**: If a candidate produces `RealizationStatus.SPATIALLY_INFEASIBLE` or `INVALID_CANDIDATE`, it receives:
   - `selection_status = SelectionStatus.REJECTED`
   - `spatial_score = 0.0`
   - Explicit entry in `rejection_reasons` (e.g. `"Spatial realization failed: Envelope overflow"`).
2. **Missing Input Data**: If optional realization results are absent, Phase 1 abstract strategic scores are used exclusively with `selection_status = SelectionStatus.VIABLE` or `MARGINAL`.
3. **No Unhandled Crashes**: Failed candidates are kept in the ranking output list at the lowest ranks, ensuring complete visibility and auditability.

---

## 11. Geometry & Solver Isolation Rules

Stage 3B.5 enforces strict architectural boundaries:
- **Phase 1 Strategic Scorer**: MUST NOT import Shapely, PuLP, CBC, or geometry renderer modules. Operates exclusively on abstract Pydantic schemas.
- **Phase 2 Realization Scorer**: Reads non-geometric summary metrics from `RealizationResult` (e.g. `status`, `target_area` ratios). MUST NOT invoke or modify solver algorithms directly.
- **No Solver Duplication**: Stage 3B.5 reuses `SpatialCompilerBridge` for spatial realization and DOES NOT introduce a secondary solver or room placement engine.

---

## 12. LLM / External API Boundary

Stage 3B.5 is 100% deterministic, local, and provider-independent:
- **No External Network Calls**: Scoring and selection run entirely offline without calling OpenAI, Gemini, or third-party APIs.
- **No LLM Non-Determinism**: Scores are computed via explicit mathematical models and catalog rules, not LLM prompts.

---

## 13. Generality Guarantees

Stage 3B.5 upholds all generality principles established across Phase 3:
- **NO 44x42 Hardcoding**: Evaluates arbitrary site dimensions from `problem.site`.
- **NO 4-Family Hardcoding**: Evaluates arbitrary unit containers and space programs dynamically from `candidate.unit_organization` and `problem.spaces`.
- **Unseen Decision Dimensions**: Unknown custom decision dimensions in `selected_decisions` are scored generically via preference catalog rules without requiring custom Python code edits.

---

## 14. Legacy Compatibility

The legacy compilation path (`CompilerIntent` $\rightarrow$ `compile_blueprint`) remains fully supported:
- Legacy compilation requests bypass strategy ranking or utilize a default single-candidate wrapper (`DefaultCandidateRanker`) that assigns `rank = 1` and `selection_status = SELECTED` automatically.

---

## 15. Sub-Stage Implementation Roadmap

Stage 3B.5 is organized into 6 safe, sequential sub-stages:

```text
3B.5-1: Strategy Ranking & Selection Schema Contracts (RankingResult, RankedCandidate)
    ↓
3B.5-2: Declarative Preference & Scoring Catalog (preference_catalog.json & loader)
    ↓
3B.5-3: Phase 1 Abstract Strategic Scorer (AbstractStrategicScorer)
    ↓
3B.5-4: Phase 2 Spatial Realization Scorer (SpatialRealizationScorer)
    ↓
3B.5-5: Candidate Selector & Deterministic Tie-Breaking Engine (CandidateSelector)
    ↓
3B.5-6: Golden Ranking Test Fixtures & Full Regression Verification
```

### Sub-stage Specifications:

#### Sub-stage 3B.5-1 — Schema Contracts
- **Purpose**: Create `backend/app/schemas/strategy_ranking.py` defining `RankingResult`, `RankedCandidate`, `ScoreBreakdown`, `CriterionScore`, and `SelectionStatus`.
- **Verification**: `backend/tests/test_strategy_ranking_schema.py`.

#### Sub-stage 3B.5-2 — Declarative Preference Catalog
- **Purpose**: Create `preference_catalog.json` and extend `catalog_loader.py` to load scoring weights and criteria parameters.
- **Verification**: `backend/tests/test_preference_catalog.py`.

#### Sub-stage 3B.5-3 — Phase 1 Abstract Strategic Scorer
- **Purpose**: Implement `AbstractStrategicScorer` evaluating non-geometric candidates against program requirements, privacy, risk, and preference criteria.
- **Verification**: `backend/tests/test_abstract_strategic_scorer.py`.

#### Sub-stage 3B.5-4 — Phase 2 Spatial Realization Scorer
- **Purpose**: Implement `SpatialRealizationScorer` evaluating post-realization metrics from `RealizationResult`.
- **Verification**: `backend/tests/test_spatial_realization_scorer.py`.

#### Sub-stage 3B.5-5 — Candidate Selector & Tie-Breaking Engine
- **Purpose**: Implement `CandidateSelector` applying multi-criteria total score combination, threshold filtering, selection status assignment, and deterministic tie-breaking.
- **Verification**: `backend/tests/test_candidate_selector.py`.

#### Sub-stage 3B.5-6 — Golden Ranking Fixtures & Full Regression
- **Purpose**: Implement golden ranking scenarios (benchmarks, single family, multi-family, infeasible candidates) and run full 311+ test regression suite.
- **Verification**: `backend/tests/test_golden_strategy_ranking.py`.

---

## 16. Acceptance Criteria

Stage 3B.5 is complete when:
- [ ] `strategy_ranking.py` schema contracts fully defined and tested.
- [ ] Scoring weights and criteria rules loaded declaratively from `preference_catalog.json`.
- [ ] `AbstractStrategicScorer` scores non-geometric candidates deterministically before realization.
- [ ] `SpatialRealizationScorer` scores post-realization results without modifying solver logic.
- [ ] `CandidateSelector` applies deterministic tie-breaking and selection status assignment.
- [ ] Failed/infeasible candidates receive `REJECTED` status with explicit rejection reasons without crashing.
- [ ] AST checks confirm ZERO domain-specific Python `if/elif` branches in scoring evaluators.
- [ ] All golden ranking fixtures pass cleanly and full regression test suite passes 100% green.
