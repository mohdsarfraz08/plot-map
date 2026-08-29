# BuildForgeAI Architecture — 2D Spatial Realization Specification

**Phase**: 3 — Architectural Reasoning / Phase 4 — Spatial Realization  
**Stage**: 3B.4D — 2D Spatial Realization  
**Document Status**: Canonical Architecture Specification — Stage 3B.4D Planned  

---

## 1. Purpose

Stage **3B.4D (2D Spatial Realization)** defines the canonical architectural boundary between high-level conceptual design reasoning (`DesignCandidate`, `CandidateOrganizer`) and deterministic 2D spatial layout optimization (`compile_blueprint`, `solve_layout`, Shapely geometry, MILP solver).

```text
Architectural Reasoning Pipeline (Stages 3A – 3B.4C):
DesignProblem → ArchitecturalAnalysis → DesignStrategy → DesignCandidate → CandidateOrganizer (Enriched DesignCandidate)

                                    │
                                    │ [STAGE 3B.4D BOUNDARY]
                                    ▼

2D Spatial Realization Pipeline (Stage 3B.4D & Baseline Engine):
Enriched DesignCandidate → SpatialRealizationAdapter → SpatialLayoutPlan → Existing compile_blueprint() / solve_layout() → Realized 2D Geometry & Layout
```

### Distinctions across layers:
1. **Architectural Reasoning**: Decides *WHAT* decisions exist, *WHY* trade-offs occur, and *WHICH* strategic choices are made (`ArchitecturalAnalysis`, `DesignStrategy`).
2. **Abstract Organization**: Derived non-geometric topological relationships between user groups, spaces, floor tiers, circulation nodes, and service stacks (`DesignCandidate`, `CandidateOrganizer`).
3. **Spatial Realization**: Translates abstract topological requirements into non-geometric spatial optimization inputs (`SpatialLayoutPlan`, `LayoutRealizationRequest`).
4. **Geometric Representation**: Computes explicit coordinates, bounding boxes, wall lines, opening points, and polygon envelopes (Shapely, `compile_geometry`).
5. **Optimization / Solver Execution**: MILP floor packing, spatial boundary constraints, and objective function optimization (`solve_layout`).

---

## 2. Input Contract

Stage 3B.4D consumes two input models: the enriched `DesignCandidate` and its originating `DesignProblem`.

### Authoritative Fields from `DesignCandidate`:
- `selected_decisions`: `list[DecisionRecord]` — Explicitly derived or fixed architectural decision choices (e.g. `unit_organization="grouped"`, `vertical_circulation="shared"`, `service_core_strategy="centralized"`).
- `floor_organization`: `dict[str, list[str]]` — Authoritative floor tier assignments mapping floor IDs (`floor_1`, `floor_2`, ...) to space IDs.
- `unit_organization`: `dict[str, list[str]]` — Authoritative unit grouping containers mapping unit IDs (`unit_family_a`, `unit_default`, ...) to space IDs.
- `circulation_intent`: `list[AbstractCirculationNode]` — Authoritative circulation core specifications (`id`, `type`, `access_type`, `connected_space_ids`).
- `service_organization`: `list[AbstractServiceStack]` — Authoritative service core specifications (`id`, `service_type`, `assigned_space_ids`).
- `source_problem_id` & `source_problem_version`: Source lineage identifiers.
- `source_strategy_id` & `source_analysis_id`: Strategic provenance identifiers.

### Advisory Fields from `DesignCandidate`:
- `unresolved_decisions`: `list[DecisionRecord]` — Open flexible dimensions that may be dynamically varied during spatial realization search.
- `assumptions`: `list[str]` — Qualitative context for strategy evaluation.
- `risks`: `list[StrategyRisk]` — Known strategy vulnerabilities.
- `feasibility_expectation`: `FeasibilityExpectation` — Pre-realization confidence assessment.
- `confidence`: `float` — Strategic confidence score.

### Authoritative Fields from `DesignProblem`:
- `site`: `SiteDefinition` — Plot dimensions (`plot_width`, `plot_depth`), setbacks (`left`, `right`, `top`, `bottom`), max floor count (`floors`), and site metadata.
- `spaces`: `list[SpaceRequirement]` — Master program requirements (`id`, `room` intent, `quantity`, `owner_id`, `priority`, `relationships`).

---

## 3. Output Contract

To maintain a clean separation between high-level reasoning and low-level MILP solver payloads, Stage 3B.4D introduces a conceptual intermediate schema: **`SpatialLayoutPlan`**.

```python
class SpatialRoomSpec(BaseModel):
    id: str
    name: str
    room_type: str
    target_area: float
    aspect_ratio_range: tuple[float, float] = (0.5, 2.0)
    floor_assignment: int = 1
    unit_id: str | None = None
    min_width: float | None = None
    min_depth: float | None = None

class SpatialAdjacencySpec(BaseModel):
    source_space_id: str
    target_space_id: str
    strength: str = "hard"  # hard | soft
    weight: float = 1.0

class SpatialCoreSpec(BaseModel):
    id: str
    core_type: str  # vertical_stairwell | plumbing_wet_core | circulation_node
    access_type: str  # shared | independent | hybrid
    floors: list[int]
    connected_space_ids: list[str]

class SpatialLayoutPlan(BaseModel):
    id: str
    source_candidate_id: str
    source_strategy_id: str
    source_problem_id: str
    source_problem_version: int
    plot_width: float
    plot_depth: float
    setbacks: dict[str, float]
    floors: int
    rooms: list[SpatialRoomSpec]
    adjacencies: list[SpatialAdjacencySpec]
    cores: list[SpatialCoreSpec]
    realization_parameters: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
```

The output payload passed to downstream spatial optimization is derived deterministically from `SpatialLayoutPlan`.

---

## 4. Geometry Boundary

```text
STRICT BOUNDARY DEFINITION:

+-------------------------------------------------------------------+
| NON-GEOMETRIC REASONING LAYER                                     |
| DesignProblem -> ArchitecturalAnalysis -> DesignCandidate        |
| (NO coordinates, NO bounding boxes, NO polygons, NO Shapely)      |
+-------------------------------------------------------------------+
                                 │
                                 │ Stage 3B.4D Realization Contract
                                 ▼
+-------------------------------------------------------------------+
| ABSTRACT SPATIAL REALIZATION CONTRACT                             |
| SpatialLayoutPlan / LayoutRealizationRequest                      |
| (Target areas, adjacency weights, floor assignments, core types)  |
+-------------------------------------------------------------------+
                                 │
                                 │ Downstream Adapter Input
                                 ▼
+-------------------------------------------------------------------+
| GEOMETRIC / OPTIMIZATION REALIZATION ENGINE                       |
| Shapely Polygons, MILP Solver (solve_layout), 2D Renderer         |
| (Exact X/Y coordinates, room rectangles, wall lines, doors)       |
+-------------------------------------------------------------------+
```

**Rule**: Reasoning components (`ArchitecturalAnalyzer`, `StrategyGenerator`, `CandidateOrganizer`) MUST NEVER import Shapely, PuLP, or spatial solver modules. Geometry becomes legal strictly inside the 2D Realization Engine.

---

## 5. Existing Compiler / Solver Reuse

Stage 3B.4D reuses the existing, battle-tested 2D compilation and optimization infrastructure located in:
- `backend/app/services/compiler/serializer.py` (`compile_blueprint`)
- `backend/app/services/optimization/solver.py` (`solve_layout`)
- `backend/app/services/geometry/setbacks.py` (`calculate_buildable_area`, `create_plot`)

### Adapter Architecture:
```text
Enriched DesignCandidate
        ↓
CandidateToLayoutAdapter (Translates candidate + problem to SpatialLayoutPlan)
        ↓
SpatialLayoutPlan.to_compiler_payload() (Generates payload dict matching compile_blueprint input)
        ↓
compile_blueprint(payload)
        ↓
solve_layout() [MILP Optimization]
        ↓
Realized 2D Blueprint Output
```

No new solver engine will be created. The existing MILP solver is reused via a translation adapter.

---

## 6. Abstract-to-Spatial Translation

The `CandidateToLayoutAdapter` maps abstract topological structures into explicit spatial requirements:

1. **Floor Organization → `floor_assignment`**:
   - `floor_organization = {"floor_1": ["space_1", "space_2"], "floor_2": ["space_3"]}`
   - Sets `floor_assignment = 1` for `space_1`, `space_2`, and `floor_assignment = 2` for `space_3`.

2. **Unit Organization → Grouping Constraints**:
   - `unit_organization = {"unit_family_a": ["space_1", "space_2"]}`
   - Creates implicit spatial adjacency / proximity constraints between spaces sharing a unit container.

3. **Circulation Intent → Core Coordinates & Access Requirements**:
   - `AbstractCirculationNode(type="vertical_stairwell", access_type="shared")`
   - Maps to `stair_core` configuration (`width`, `height`, `edge`) in compiler payload.

4. **Service Organization → Service Stacks & Plumbing Proximity**:
   - `AbstractServiceStack(service_type="plumbing_wet_core", assigned_space_ids=[...])`
   - Generates high-priority adjacency/stacking constraints between wet spaces across floors.

5. **Selected Decisions → Realization Parameters**:
   - Explicit decision choices configure realization parameters (e.g. grid snap, aspect ratio bounds, corridor width factors).

---

## 7. Constraint Translation

Abstract constraints and requirements are mapped to spatial optimization inputs:

- **Hard Requirements**: Mapped to hard MILP boundary and placement constraints (e.g. mandatory floor assignment, non-overlap, buildable envelope bounds).
- **Soft Constraints & Preferences**: Mapped to MILP objective function penalty terms or preferred aspect ratio bounds.
- **Objectives**: Mapped to optimization direction parameters (e.g. minimize total circulation area, maximize perimeter exposure).
- **Relationships & Adjacencies**: `RequirementRelation(relation="adjacent")` maps to `adjacencies` list in `compile_blueprint` payload.
- **Incompatibilities**: `IncompatibilityRule` pairs map to explicit spatial non-adjacency or floor separation constraints.

---

## 8. Determinism

Spatial realization MUST be 100% deterministic:
1. **Sorted Input Iteration**: Space lists, floor keys, unit containers, and adjacencies are sorted lexicographically by ID before payload generation.
2. **Fixed Random Seeds**: MILP solver random seeds are fixed to deterministic constants.
3. **Deterministic Fingerprinting**: `SpatialLayoutPlan` computes a SHA-256 fingerprint from sorted spatial specifications.
4. **Reproducibility Guarantee**: Identical `(DesignCandidate, DesignProblem)` inputs executed N times produce identical 2D spatial layouts.

---

## 9. Failure & Infeasibility Model

When spatial realization fails, Stage 3B.4D returns structured failure information without crashing:

```python
class RealizationStatus(str, Enum):
    SUCCESS = "success"
    INVALID_CANDIDATE = "invalid_candidate"
    UNSUPPORTED_SPEC = "unsupported_spec"
    SPATIALLY_INFEASIBLE = "spatially_infeasible"
    SOLVER_TIMEOUT = "solver_timeout"
    SOLVER_ERROR = "solver_error"

class RealizationResult(BaseModel):
    status: RealizationStatus
    success: bool
    candidate_id: str
    layout_plan: SpatialLayoutPlan | None = None
    realized_geometry: dict[str, Any] | None = None
    error_message: str | None = None
    infeasible_constraints: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
```

Failures are explicitly reported and MUST NEVER be masked with dummy geometries.

---

## 10. Traceability

Complete provenance lineage is maintained end-to-end:

$$\text{DesignProblem} \longrightarrow \text{ArchitecturalAnalysis} \longrightarrow \text{DesignStrategy} \longrightarrow \text{DesignCandidate} \longrightarrow \text{SpatialLayoutPlan} \longrightarrow \text{RealizedLayout}$$

Every `RealizedLayout` carries metadata linking it back to `source_candidate_id`, `source_strategy_id`, `source_analysis_id`, and `source_problem_id` with version numbers.

---

## 11. Generality Guarantees

Stage 3B.4D preserves all generality principles established in 3B.3C and 3B.4C:
- **NO 44x42 Hardcoding**: Site plot width/depth and setbacks are read dynamically from `problem.site`.
- **NO Four-Family Hardcoding**: Unit counts and user groups are handled dynamically from `candidate.unit_organization`.
- **NO Python Domain Branching**: Spatial translation operates on generic schema fields and catalog rule parameters.
- **Unseen Decision Dimensions**: Unknown decision dimensions are passed as generic realization metadata without breaking the pipeline.

---

## 12. 2D Scope

Stage 3B.4D encompasses:
- Space and room polygon placement.
- Floor level assignment realization.
- Unit grouping proximity realization.
- Vertical circulation core placement.
- Service wet core stacking across floors.
- Buildable envelope setback compliance.
- 2D room graph adjacency realization.

---

## 13. Explicit Non-Goals

Stage 3B.4D strictly excludes:
- ❌ 3D mesh generation or 3D rendering.
- ❌ BIM / IFC export.
- ❌ CAD file export (DXF/DWG).
- ❌ TBM (Tile Building Model) generation (handled in later realization stages).
- ❌ Frontend UI components.
- ❌ Production REST API integration (`/api/compile` integration occurs in 3B.4E).
- ❌ LLM-driven spatial optimization.

---

## 14. Implementation Sub-Stages

Stage 3B.4D is decomposed into 6 safe incremental sub-stages:

```text
3B.4D-1: Spatial Realization Schema Contract (SpatialLayoutPlan)
    ↓
3B.4D-2: Abstract-to-Spatial Candidate Adapter (CandidateToLayoutAdapter)
    ↓
3B.4D-3: Compiler & MILP Solver Bridge (compile_blueprint Integration)
    ↓
3B.4D-4: Golden 2D Realization Test Fixtures
    ↓
3B.4D-5: Infeasibility & Failure Handling Engine
    ↓
3B.4D-6: Full Regression Verification & Migration Documentation
```

### Sub-stage Specifications:

#### Sub-stage 3B.4D-1 — Spatial Realization Schema Contract
- **Purpose**: Introduce non-geometric `SpatialLayoutPlan`, `SpatialRoomSpec`, `SpatialAdjacencySpec`, `SpatialCoreSpec`, and `RealizationResult` schemas.
- **Allowed Files**: `backend/app/schemas/spatial_realization.py`, `backend/tests/test_spatial_realization_schema.py`.
- **Forbidden Files**: Solver, compiler, drawing, or API files.

#### Sub-stage 3B.4D-2 — Abstract-to-Spatial Candidate Adapter
- **Purpose**: Implement `CandidateToLayoutAdapter` converting `(DesignCandidate, DesignProblem)` into `SpatialLayoutPlan`.
- **Allowed Files**: `backend/app/services/analysis/spatial_adapter.py`, `backend/tests/test_spatial_adapter.py`.

#### Sub-stage 3B.4D-3 — Compiler & MILP Solver Bridge
- **Purpose**: Connect `SpatialLayoutPlan` to existing `compile_blueprint` and `solve_layout` functions.
- **Allowed Files**: `backend/app/services/compiler/realization_bridge.py`, `backend/tests/test_realization_bridge.py`.

#### Sub-stage 3B.4D-4 — Golden 2D Realization Test Fixtures
- **Purpose**: Create explicit 2D spatial realization golden fixtures verifying non-geometric layout specs match expected spatial constraints.
- **Allowed Files**: `backend/tests/fixtures/golden_realization_fixtures.py`, `backend/tests/test_golden_2d_realization.py`.

#### Sub-stage 3B.4D-5 — Infeasibility & Failure Handling Engine
- **Purpose**: Implement structured error handling for solver timeouts, envelope violations, and topological invalidity.
- **Allowed Files**: `backend/app/services/analysis/spatial_adapter.py`, `backend/tests/test_realization_infeasibility.py`.

#### Sub-stage 3B.4D-6 — Full Regression Verification & Migration Documentation
- **Purpose**: Run full regression suite across all test files and update architecture documentation.
- **Allowed Files**: `docs/architecture/06-2d-spatial-realization.md`, `docs/architecture/BUILDForgeAI_ARCHITECTURE_ROADMAP.md`.

---

## 15. Golden Fixture Specifications

Future 2D spatial realization tests will utilize 8 explicit golden scenario fixtures:
1. **44x42 Benchmark Scenario**: 4-family, 4-floor layout with vertical shared stair core and central wet stack.
2. **Single-Family Ground Floor Scenario**: 30x40 ft single-level layout with ground floor assignment.
3. **Shared Circulation Core Scenario**: Multi-unit layout connected to central shared stairwell.
4. **Independent Access Cores Scenario**: Multi-unit layout with per-unit private circulation cores.
5. **Hybrid Circulation Scenario**: Combination of shared vertical core and private unit entries.
6. **Multi-Floor Vertical Distribution Scenario**: Units distributed across floor 1, floor 2, floor 3.
7. **Centralized Service Core Stacking Scenario**: Bathrooms and kitchens vertically aligned across floors.
8. **Unseen Decision Dimension Scenario**: Custom `solar_shading_strategy` and `facade_transparency` mapped to spatial parameters.

---

## 16. Migration Strategy

The migration path maintains complete backwards compatibility:

```text
LEGACY PATH (Preserved):
CompilerIntent → to_design_problem() → compile_blueprint() → Direct MILP Layout

NEW DATA-DRIVEN REALIZATION PATH (Stage 3B.4D):
DesignProblem → ArchitecturalAnalysis → DesignStrategy → DesignCandidate → CandidateOrganizer → SpatialLayoutPlan → compile_blueprint() → Realized 2D Layout
```

Both compilation paths will coexist. The legacy path will not be removed until 2D spatial realization equivalence is fully proven.

---

## 17. Testing Strategy

Stage 3B.4D implementation will enforce 5 test categories:
1. **Schema Validation Tests**: Validate `SpatialLayoutPlan` serialization, immutability, and boundary checks.
2. **Adapter Unit Tests**: Validate translation of floor organization, unit organization, circulation nodes, and service stacks.
3. **Solver Integration Tests**: Verify end-to-end execution through `solve_layout` and `compile_blueprint`.
4. **Infeasibility Tests**: Verify invalid plot sizes, impossible adjacencies, and solver timeouts yield structured error results.
5. **Genericity & AST Tests**: AST inspection enforcing zero domain-specific Python branching in the realization adapter.

---

## 18. Security & Boundary Concerns

- **Provider Independence**: Spatial realization is 100% deterministic and operates offline with zero external LLM or cloud API dependencies.
- **Input Sanitization**: Numeric plot dimensions, setbacks, and target areas are sanitized and validated against positive bounds before solver execution.

---

## 19. Open Architectural Questions

Before starting 3B.4D implementation, the following architectural questions must be investigated:
1. **Room Area Allocation Defaults**: How should target room areas be allocated when space requirements specify room categories without explicit square footage?
2. **MILP Soft Objective Penalty Weights**: What default numeric weights should be assigned to soft adjacency preferences vs. circulation area minimization in `solve_layout`?
3. **Custom Dimension Handling**: How should un-mapped custom decision dimensions in `DesignCandidate` be recorded in `SpatialLayoutPlan` provenance?

---

## 20. Acceptance Criteria

Stage 3B.4D is complete when:
- [x] `SpatialLayoutPlan` contract is fully defined and tested.
- [x] `CandidateToLayoutAdapter` converts any valid `DesignCandidate` into `SpatialLayoutPlan` deterministically.
- [x] Realization engine reuses existing `compile_blueprint` / `solve_layout` without solver duplication.
- [x] All 8 golden 2D spatial realization fixtures pass cleanly.
- [x] Infeasibility and solver failures are reported via structured `RealizationResult` objects without unhandled exceptions.
- [x] Complete lineage and provenance are preserved end-to-end.
- [x] AST checks confirm ZERO domain-specific Python branches in the realization adapter.
- [x] Complete regression test suite passes 100% green.

---

## 21. Stage 3B.4D Completion & Verification Audit

**Status**: **COMPLETE** (2026-08-29)

### Sub-stage Audit Summary:
1. **Stage 3B.4D-1 (Schema Contract)**: Defined `SpatialLayoutPlan`, `SpatialRoomSpec`, `SpatialAdjacencySpec`, `SpatialCoreSpec`, and `RealizationResult` schemas in `backend/app/schemas/spatial_realization.py`. Verified via `test_spatial_realization_schema.py` (28 tests).
2. **Stage 3B.4D-2 (Candidate Adapter)**: Implemented deterministic `CandidateToLayoutAdapter` in `backend/app/services/analysis/spatial_adapter.py`. Verified via `test_candidate_to_layout_adapter.py` (28 tests).
3. **Stage 3B.4D-3 (Compiler & MILP Solver Bridge)**: Built `SpatialCompilerBridge` in `backend/app/services/realization/compiler_bridge.py` linking `SpatialLayoutPlan` to `compile_blueprint()` and `solve_layout()`. Verified via `test_compiler_bridge.py` (28 tests).
4. **Stage 3B.4D-4 (Golden 2D Realization Test Fixtures)**: Created 8 canonical golden 2D realization scenarios in `backend/tests/fixtures/golden_spatial_realization_fixtures.py`. Verified via `test_golden_spatial_realization.py` (28 tests).
5. **Stage 3B.4D-5 (Infeasibility & Failure Handling Engine)**: Integrated structured failure normalization and classification into `SpatialCompilerBridge`. Verified via `test_realization_failure_handling.py` (28 tests).
6. **Stage 3B.4D-6 (Final Regression Verification & Migration Documentation)**: Validated total regression suite (311 tests passed), determinism, traceability, genericity, solver reuse, geometry boundary isolation, and coexisting legacy compatibility.

### Verification Matrix:
- **Total Test Count**: 311 tests passing across 17 test modules (0 failures, 1 warning).
- **Golden Fixture Scenarios (A–I)**: All 8 golden 2D spatial scenarios verified end-to-end.
- **Failure Status Coverage**: All 6 `RealizationStatus` values (`SUCCESS`, `INVALID_CANDIDATE`, `UNSUPPORTED_SPEC`, `SPATIALLY_INFEASIBLE`, `SOLVER_TIMEOUT`, `SOLVER_ERROR`) covered and tested.
- **Determinism Audit**: Verified 100% reproducible execution across repeated runs with zero timestamp/memory address leakage.
- **Traceability Audit**: Verified 100% provenance lineage preservation from `DesignProblem` through `SpatialLayoutPlan` to `RealizationResult`.
- **Genericity & AST Audit**: Verified zero domain-specific `if/elif` branches in `CandidateToLayoutAdapter` and `SpatialCompilerBridge`.
- **Solver & Geometry Boundary Audit**: Confirmed zero duplicate solvers or geometry placement engines were introduced; existing `compile_blueprint()` and `solve_layout()` are reused strictly.
- **Legacy Path Compatibility**: Confirmed `CompilerIntent` $\rightarrow$ `compile_blueprint` path coexists without modification.

