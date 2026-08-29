# BuildForgeAI — Architecture & Implementation Roadmap

> **Status:** Active  
> **Purpose:** Source of truth for implementation stages and architectural boundaries  
> **Audience:** Human developers and AI coding agents (Copilot, Antigravity, etc.)  
> **Principle:** Coding agents are replaceable implementation workers. This document owns the architecture.

---

## 1. Product Vision

BuildForgeAI is intended to become a **general computational architectural design system**.

The system should accept changing and potentially ambiguous architectural requirements, analyze them, explore feasible architectural configurations, generate designs, validate them, optimize/rank alternatives, produce 2D/3D representations, and support iterative user modifications.

The product must **not** be designed around a single scenario.

The current `44 × 42 ft / four-family` problem is a **benchmark/test case only**.

### Target workflow

```text
USER REQUIREMENTS
        ↓
REQUIREMENT UNDERSTANDING
        ↓
DESIGN PROBLEM
        ↓
ARCHITECTURAL ANALYSIS
        ↓
DESIGN STRATEGIES
        ↓
CANDIDATE DESIGNS
        ↓
VALIDATION
        ↓
OPTIMIZATION / RANKING
        ↓
GEOMETRY REALIZATION
        ↓
       ┌───────────────┐
       ↓               ↓
      2D              3D/MESH
       └───────┬───────┘
               ↓
              USER
               ↓
       REQUIREMENT CHANGE
               ↓
       RE-ANALYSIS / RE-DESIGN
               ↺
```

---

## 2. Core Architectural Principle

The system separates:

- **Architectural reasoning:** WHAT should be designed, WHY, and what alternatives exist.
- **Spatial optimization:** whether a requested configuration is physically feasible and how spaces can be placed.
- **Geometry realization:** exact coordinates, boundaries, walls, openings, and output geometry.

```text
Architectural Reasoning
        ↓
Design Strategy
        ↓
Design Candidate
        ↓
Constraint / Feasibility Validation
        ↓
Existing Optimization Engine
        ↓
Geometry
        ↓
2D / 3D / Mesh
```

The existing MILP/PuLP/CBC engine must not become the architectural reasoning engine.

---

## 3. Generality Requirements

The architecture must support requirements such as:

- all families/users on the ground floor
- users distributed across different floors
- one shared staircase
- independent staircases
- shared entrances
- independent entrances
- shared spaces
- independent spaces
- privacy requirements
- accessibility requirements
- site constraints
- different floor counts
- different numbers of users/families/units
- different room programs
- different priorities
- conflicting requirements
- requirements that change after a design is generated

The system must not assume:

- `44 × 42 ft`
- four families
- four floors
- one family per floor
- fixed staircase count
- fixed room count
- residential-only buildings

---

# 4. Current System Baseline

The existing engine provides important lower-level capabilities:

```text
CompilerIntent
      ↓
Existing compiler
      ↓
Floor-level optimization / MILP
      ↓
TBM
      ↓
2D / CAD / 3D output
```

These components are valuable existing infrastructure.

### Preservation rule

New reasoning layers should be added **around** the existing engine before attempting to rewrite it.

Do not modify the solver merely to introduce architectural reasoning.

---

# 5. Implementation Roadmap

## Phase 0 — Existing Engine Baseline

**Status: Stable / Existing**

Responsibilities:

- parse existing compiler intent
- compile room/floor programs
- perform floor-level optimization
- generate TBM
- generate 2D/3D output

Existing behavior must remain available throughout the migration.

---

## Phase 1 — General Design Problem

**Status: COMPLETE**

Introduced a general representation for an architectural design problem.

Conceptually:

```text
DesignProblem
├── Site
├── Program
├── Requirements
├── Constraints
├── Preferences
├── Objectives
├── Relationships
└── Provenance
```

Supporting concepts include:

- `Requirement`
- `Constraint`
- `Preference`
- `Objective`
- `RequirementDelta`
- site/program/space/relationship structures

### Purpose

Represent arbitrary architectural requirements without encoding a specific building scenario.

---

## Phase 2 — Legacy Intent Adapter

**Status: COMPLETE**

```text
CompilerIntent
      ↓
to_design_problem()
      ↓
DesignProblem
```

### Purpose

Allow existing compiler input to coexist with the new general reasoning architecture.

The adapter maps only information actually represented by `CompilerIntent`.

Unsupported semantics must not be invented.

---

# 6. Phase 3 — Architectural Reasoning

## Stage 3A — Architectural Analysis

### Stage 3A.1 — Analysis Schema

**Status: COMPLETE**

Introduced:

```text
ArchitecturalAnalysis
DecisionRecord
ConflictRecord
UncertaintyRecord
DependencyRecord
FeasibilityConcern
```

The schema is an analysis contract and must not perform semantic inference by itself.

### Stage 3A.2 — Architectural Analyzer

**Status: COMPLETE**

Target:

```text
DesignProblem
      ↓
ArchitecturalAnalyzer
      ↓
ArchitecturalAnalysis
```

### Responsibilities

The analyzer determines:

- fixed decisions
- flexible decisions
- hard constraints
- soft preferences
- objectives
- conflicts
- uncertainties
- architectural decision dimensions
- dependencies
- feasibility concerns
- questions requiring clarification

### Non-responsibilities

The analyzer must not:

- generate exact geometry
- place walls
- solve MILP
- call CBC/PuLP
- generate CAD
- generate meshes
- choose the final architectural strategy
- require an LLM

### Critical semantic rule

These remain distinct:

```text
"I need one staircase."
        ↓
Hard requirement

"I prefer one staircase."
        ↓
Soft preference

"Minimize circulation/staircase area."
        ↓
Objective
```

### Conservative behavior

When important information is missing:

```text
DO NOT GUESS
       ↓
Record uncertainty
       ↓
Identify affected decisions
       ↓
Ask clarification when appropriate
```

---

## Stage 3B — Design Strategy Generation

**Status: IN PROGRESS** (3B.3 Complete, 3B.4 PLANNED)

```text
ArchitecturalAnalysis
        ↓
Strategy Generator
        ↓
DesignStrategy[]
```

A strategy represents a conceptual architectural approach, not exact geometry.

### Sub-stages & Progress:

- **Stage 3B.1 — DesignStrategy Schema** (**COMPLETE**)  
  Introduced non-geometric `DesignStrategy`, `DecisionRecord`, `TradeOff`, `StrategyRisk`, and `FeasibilityExpectation` schemas.

- **Stage 3B.2 — StrategyGenerator Baseline Infrastructure** (**COMPLETE**)  
  Established baseline deterministic pipeline: requirement traceability, constraint filtering, uncertainty propagation, fingerprint deduplication, deterministic ordering, and strategy limit bounding.

- **Stage 3B.3 — Generic Data-Driven Generation Engine** (**COMPLETE** ✅)  
  Removed domain-dimension coupling and replaced hardcoded archetypes with a pure data-driven reasoning engine.
  - **Stage 3B.3A** ✅: Analysis Data Contract (`DecisionRecord.alternatives`, `IncompatibilityRule`, `DimensionRelationship`) + tests.
  - **Stage 3B.3B** ✅: Generic Strategy Engine (Bounded Cartesian combination, dynamic filtering, dynamic trade-off derivation) + unseen dimension tests.
  - **Stage 3B.3C** ✅: Legacy Archetype Removal & Full Regression.
    - **3B.3C-1** ✅: Legacy audit — all hardcoded rules classified.
    - **3B.3C-2** ✅: Declarative Decision Catalog (`decision_catalog.json` + `catalog_loader.py`) created. `ArchitecturalAnalyzer` generically populates `DecisionRecord.alternatives` from catalog with no `if/elif` domain branches.
    - **3B.3C-3** ✅: Golden migration tests — semantic equivalence verified against benchmark.
    - **3B.3C-4** ✅: Legacy Path B removed from `StrategyGenerator`. `RequirementKind` branching removed from generator. AST-based legacy absence regression test added. **85/85 tests passing.**

- **Stage 3B.4C — Generic Candidate Organizer Migration** (**COMPLETE** ✅)
  - **3B.4C-1** ✅: Audit legacy candidate organization behaviors & classify rules.
  - **3B.4C-2** ✅: Generic data-driven `CandidateOrganizer` engine implemented (`organize_candidate`, `OrganizationAction`, `OrganizationRule`).
  - **3B.4C-3** ✅: Golden behavior & migration equivalence (17-point verification suite passing, golden fixtures created).
  - **3B.4C-4** ✅: Legacy path audit & AST absence guard verification (**178/178 tests passing** across 12 test modules).

- **Stage 3B.4D — 2D Spatial Realization** (**COMPLETE** ✅)  
  *See canonical specification: [`06-2d-spatial-realization.md`](file:///c:/Users/affaa/OneDrive/Desktop/BuildForge/docs/architecture/06-2d-spatial-realization.md)*
  - **3B.4D-1** ✅: Spatial Realization Schema Contract (`SpatialLayoutPlan`, `SpatialRoomSpec`).
  - **3B.4D-2** ✅: Abstract-to-Spatial Candidate Adapter (`CandidateToLayoutAdapter`).
  - **3B.4D-3** ✅: Compiler & MILP Solver Bridge (`compile_blueprint` integration).
  - **3B.4D-4** ✅: Golden 2D Realization Test Fixtures.
  - **3B.4D-5** ✅: Infeasibility & Failure Handling Engine (`RealizationResult`).
  - **3B.4D-6** ✅: Full Regression & Migration Verification (**311/311 tests passing** across 17 test modules).

- **Stage 3B.5 — Strategy Ranking & Candidate Selection** (**COMPLETE** ✅)  
  *See canonical specification: [`07-strategy-ranking-selection.md`](file:///c:/Users/affaa/OneDrive/Desktop/BuildForge/docs/architecture/07-strategy-ranking-selection.md)*
  - **3B.5-1** ✅: Strategy Ranking & Selection Schema Contracts (`RankingResult`, `RankedCandidate`).
  - **3B.5-2** ✅: Declarative Preference & Scoring Catalog (`preference_catalog.json` & loader).
  - **3B.5-3** ✅: Phase 1 Abstract Strategic Scorer (`AbstractStrategicScorer`).
  - **3B.5-4** ✅: Phase 2 Spatial Realization Scorer (`SpatialRealizationScorer`).
  - **3B.5-5** ✅: Candidate Selector & Deterministic Tie-Breaking Engine (`CandidateSelector`).
  - **3B.5-6** ✅: Golden Ranking Test Fixtures & Full Regression Verification (**498/498 tests passing** across 23 test modules).

- **Stage 3B.6 — Downstream Integration & Orchestration** (**PLANNED / NEXT** ⏳)

Strategies emerge directly from the design problem and must never be hardcoded around a benchmark or specific building type.

---

# 7. Phase 4 — Candidate Design Generation

**Status: PLANNED**

```text
DesignStrategy
      ↓
DesignCandidate
```

A candidate should eventually describe a concrete architectural configuration including:

- building organization
- floor organization
- unit organization
- space program
- relationships
- circulation
- services
- constraints
- design metrics

Multiple candidates should eventually be supported.

---

# 8. Phase 5 — Validation

**Status: PLANNED**

```text
DesignCandidate
      ↓
Validation
      ↓
Feasible / Infeasible
```

Validation should eventually consider:

- site constraints
- program requirements
- spatial feasibility
- circulation
- access
- service relationships
- user requirements
- architectural relationships
- applicable regulatory constraints

Validation remains distinct from candidate generation.

---

# 9. Phase 6 — Optimization & Ranking

**Status: PLANNED**

```text
Candidate A ─┐
Candidate B ─┼──→ Evaluate → Rank
Candidate C ─┘
```

Possible objectives include:

- usable area
- circulation efficiency
- privacy
- service efficiency
- accessibility
- daylight/environmental response
- cost
- user-defined priorities

The system must not assume a universal objective hierarchy.

---

# 10. Phase 7 — Geometry Realization

**Status: PLANNED**

```text
Validated DesignCandidate
          ↓
Existing spatial optimizer
          ↓
Exact placement
          ↓
Geometry
```

The existing MILP/PuLP/CBC engine should be reused where appropriate.

The optimizer answers:

> Where can the spaces physically go?

The reasoning layer answers:

> What spaces/configuration should exist?

---

# 11. Phase 8 — 2D / 3D Output

**Status: Existing + Future Integration**

```text
Geometry
   ├──→ 2D architectural drawing / CAD
   ├──→ TBM
   └──→ 3D / Mesh
```

Output remains a downstream representation of the selected design.

---

# 12. Phase 9 — User Modification Loop

**Status: PLANNED**

```text
Existing Design
      +
User Change
      ↓
RequirementDelta
      ↓
Affected Decisions
      ↓
Re-analysis
      ↓
Re-strategy
      ↓
Re-validation
      ↓
Updated Design
```

Examples:

- “Make the kitchen larger.”
- “Move the staircase.”
- “Give Family B more privacy.”
- “I no longer want separate staircases.”
- “Keep everyone on the ground floor.”

The system should eventually identify affected architectural decisions rather than blindly rebuilding everything.

---

# 13. Phase 10 — LLM Integration

**Status: PLANNED / Provider-Independent**

LLMs are replaceable components.

```text
LLM Provider
      ↓
Requirement Extraction
      ↓
DesignProblem
      ↓
OUR DESIGN ENGINE
      ↓
Reasoning / Optimization
      ↓
Design
```

Possible providers:

- Gemini
- OpenAI
- local models
- other providers
- human-authored structured input

The internal architecture must not depend on a particular provider.

The core design engine should remain functional when LLM calls fail.

---

# 14. Benchmark Scenarios

The `44 × 42 ft / four-family` scenario is a **benchmark**, not a domain model.

The benchmark suite should eventually include:

1. Simple 2-bedroom house on a 30×40 plot.
2. Two families requiring independent homes.
3. Multiple users with one shared staircase.
4. Independent circulation requirements.
5. All users/families on the ground floor.
6. Users/families distributed across floors.
7. Conflicting entrance/circulation requirements.
8. The 44×42 four-family benchmark.

The same general architecture must process every scenario.

---

# 15. Architecture Decision Rules

## ADR-001 — General Design Problem

Use a general `DesignProblem` representation rather than scenario-specific domain models.

**Reason:** Requirements vary between projects.

## ADR-002 — Preserve Existing MILP

The existing floor-level MILP solver remains a spatial optimization component.

**Reason:** Architectural reasoning and exact spatial placement are different responsibilities.

## ADR-003 — LLM Provider Independence

No specific LLM provider should be required by the architectural reasoning architecture.

**Reason:** Providers can change, fail, become expensive, or become unavailable.

## ADR-004 — Analysis Before Strategy

Analyze what decisions exist before generating architectural strategies.

**Reason:** Avoid premature assumptions and special-case solutions.

## ADR-005 — Benchmark Independence

The 44×42/four-family problem is a benchmark only.

Agents must not introduce domain classes such as:

```text
FourFamilyBuilding
FamilyPerFloor
FourFloorStrategy
44x42Strategy
```

unless a future architecture decision explicitly requires them.

## ADR-006 — Conservative Inference

Missing information must be represented as uncertainty/open decisions rather than silently guessed.

**Reason:** Incorrect assumptions can produce architecturally invalid designs.

## ADR-007 — Coding Agent Independence

Architecture documentation is the source of truth, not the memory of an individual coding agent.

**Reason:** Implementation may move between Copilot, Antigravity, another LLM, or human developers.

---

# 16. Implementation Workflow

Every future stage follows:

```text
1. Architecture discussion
        ↓
2. Update roadmap/documentation
        ↓
3. Review and approve
        ↓
4. Implementation prompt
        ↓
5. Coding agent implementation
        ↓
6. Focused tests
        ↓
7. Code review
        ↓
8. Git commit
        ↓
9. Update documentation/status
        ↓
10. Next stage
```

### Coding-agent rule

A coding agent must read the relevant architecture documentation before implementation.

Architecture decisions should not exist only in chat history.

---

# 17. Stage Documentation Template

Every future stage should document:

```text
# Stage X — Name

## Objective
## Why This Stage Exists
## Inputs
## Outputs
## Responsibilities
## Non-Responsibilities
## Interfaces
## Data Model
## Algorithms / Rules
## Error Handling
## Test Requirements
## Acceptance Criteria
## Dependencies
## Future Extensions
## Known Limitations
## Implementation Status
## Change Log
```

---

# 18. Overall Acceptance Criteria

The eventual system should demonstrate:

### Generality
The same engine processes substantially different architectural requirements.

### Reasoning
The system identifies architectural decisions rather than merely extracting room names.

### Alternatives
The system can generate multiple feasible strategies when appropriate.

### Constraint awareness
The system distinguishes hard requirements, preferences, objectives, conflicts, and uncertainties.

### Optimization
The system evaluates alternatives according to user-defined priorities.

### Geometry
The selected architecture becomes valid spatial geometry.

### Iteration
Users can change requirements and the system can re-analyze and update the design.

### Provider independence
The core design engine does not depend on a particular LLM.

---

# 19. Current Status

| Stage | Status |
|---|---|
| Existing compiler/optimizer baseline | 🟢 Stable |
| Phase 1 — DesignProblem | 🟢 Complete |
| Phase 2 — Intent Adapter | 🟢 Complete |
| Stage 3A — ArchitecturalAnalysis Schema & Analyzer | 🟢 Complete |
| Stage 3B.1 – 3B.3 — Generic StrategyGenerator Engine | 🟢 Complete |
| Stage 3B.4A – 3B.4C — DesignCandidate Schema & CandidateOrganizer | 🟢 Complete |
| Stage 3B.4D — 2D Spatial Realization | 🟢 Complete |
| Stage 3B.5 — Strategy Ranking & Selection | 🟡 Planned / Next |
| Phase 4 — Candidate Design | ⚪ Planned |
| Phase 5 — Validation | ⚪ Planned |
| Phase 6 — Optimization/Ranking | ⚪ Planned |
| Phase 7 — Geometry Realization | ⚪ Planned |
| Phase 8 — 2D/3D Integration | ⚪ Planned |
| Phase 9 — User Modification Loop | ⚪ Planned |
| Phase 10 — LLM Provider Layer | ⚪ Planned |

---

# 20. Immediate Next Step

Implement **Stage 3A.2 — ArchitecturalAnalyzer** only after this roadmap has been reviewed and approved.

Target:

```text
DesignProblem
      ↓
ArchitecturalAnalyzer
      ↓
ArchitecturalAnalysis
```

No strategy generation, geometry, solver integration, API integration, or LLM integration should be introduced in Stage 3A.2.
