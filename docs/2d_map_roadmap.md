This is the roadmap I would actually give to Antigravity. It is **not just a feature list**—it defines the architecture, implementation order, coding standards, and future-proofing so that the 2D CAD engine becomes the foundation of the future 3D engine.

---

# Antigravity Prompt: Engineering Drawing Engine Roadmap v1.0

## Mission

Build a **professional engineering drawing engine** for Plot-Map.

The objective is **not** to render simple boxes or a basic floor plan.

The objective is to generate **CAD-quality architectural drawings** comparable to those produced by AutoCAD or Revit for residential floor plans.

The drawing engine must be mathematically deterministic, modular, extensible, and become the foundation for the future procedural 3D engine.

---

# Core Design Principles

These principles are mandatory.

### 1. Single Source of Truth

The project must never maintain separate building models.

The architecture must be

```text
AI Parser
      │
      ▼
MILP Optimization
      │
      ▼
Topological Building Model (TBM)
      │
      ▼
Relationship Builder
      │
      ▼
Graph Analysis
      │
      ▼
Design Rule Engine
      │
      ▼
Geometry Resolver
      │
      ▼
CAD Kernel (Geometry Service Abstraction)
      │
      ├─────────────┐
      ▼             ▼
2D Drawing    Future 3D Engine
```

Every future system must consume the same TBM and CAD Kernel.

---

### 2. Separation of Responsibilities

Separate the project into independent layers.

```text
TBM (Semantic Model)

↓

Design Rule Engine

↓

Geometry Resolver

↓

CAD Kernel (GeometryService)

↓

Drawing Model

↓

SVG Renderer

↓

Interactive Viewer
```

No renderer should contain architectural logic.

No geometry calculations should exist inside React.

---

### 3. Semantic Before Geometry

Sprint 1 must not contain rendering.

Sprint 1 must not contain SVG.

Sprint 1 must not contain Three.js.

Sprint 1 defines the building semantically.

---

# Architecture

```text
AI Parser
      │
      ▼
MILP Optimization
      │
      ▼
Topological Building Model (TBM)
      │
      ▼
Relationship Builder
      │
      ▼
Graph Analysis (NetworkX)
      │
      ▼
Design Rule Engine (Compliance & Stair Feasibility)
      │
      ▼
Geometry Resolver (CAD Kernel / GeometryService)
      │
      ▼
Drawing Model
      │
      ▼
SVG Renderer / PDF Exporter
      │
      ▼
Interactive Viewer
```

---

# Sprint 1 — Topological Building Model (TBM)

## Objective

Create the canonical semantic building representation.

The TBM is **data only**.

No rendering.

No geometry generation.

No drawing.

---

## Core Entities

Implement the following entities.

```text
Building

Plot

Floor

Room

Wall

Opening

Junction

Stair

Column

Beam
```

Each entity must contain:

* unique id
* semantic type
* metadata
* references to related entities

Do not embed rendering information.

---

## Relationship Types

Implement these semantic relationships.

```text
BOUNDS

Room → Wall
```

```text
SEPARATES

Wall → Room A
Wall → Room B
```

```text
HOSTS

Wall → Opening
```

```text
CONNECTS

Opening → Room A
Opening → Room B
```

```text
MEETS_AT

Wall → Junction
```

Relationships must be ID-based.

---

## Domain Model

The TBM should be implemented using:

* Python dataclasses (preferred for the domain layer)
* Pydantic models at API boundaries for validation and serialization

The TBM itself must remain framework-independent.

---

# Sprint 2 — Relationship Builder

Generate semantic relationships from the TBM.

Responsibilities:

* adjacency
* ownership
* containment
* connectivity
* validation

This module prepares the TBM for graph analysis.

---

# Sprint 3 — NetworkX Graph Builder

Generate a NetworkX graph from the TBM.

**Important:**

NetworkX is **not** the source of truth.

The TBM remains canonical.

The graph is regenerated whenever the TBM changes.

Use NetworkX only for algorithms.

Supported algorithms:

* room adjacency
* shortest path
* connectivity
* reachability
* cycle detection
* topology validation

---

# Sprint 3.5 — Design Rule Engine

## Objective
Validate architectural constraints and building code compliance on the Topological Building Model (TBM) before geometry generation.

## Responsibilities
* **NBC (National Building Code) Validation:** Minimum bedroom sizes, kitchen ventilation areas, minimum door widths.
* **Setback Compliance:** Verify buildable zone restrictions.
* **Stair Feasibility:** Calculate floor-to-floor rise and run to ensure allocated stair bounding box is physically capable of holding the staircase before generating drawing elements.
* **Corridor & Circulation Clearances:** Ensure accessible paths are maintained.
* **Structural Feasibility:** Basic check for span limits between column anchors.

Output:
```text
TBM (Raw) → Design Rule Engine → Validated TBM
```

---

# Sprint 4 — Geometry Resolver

This sprint introduces geometry through a dedicated **CAD Kernel** layer (abstracted behind a `GeometryService`).

## Architectural Abstractions
* **GeometryService:** Do not import Shapely (`from shapely.geometry import ...`) or NumPy directly into business logic. Wrap all geometric calculations, offset operations, unions, and intersections inside a `GeometryService` so that the underlying computational engine can be swapped (e.g., from Shapely to CGAL or OpenCascade) in the future.
* **CAD Kernel Duties:** Responsible for coordinate transforms, polygon offsets, snapping, projections, clipping, bounding box calculation, tolerance testing, and geometric predicates.

## Wall Representation (Orthogonal MVP)
* **Orthogonal Constraints:** For the MVP, restrict layouts to orthogonal (90-degree steps) wall junctions. Postpone arbitrary-angle support to simplify miter calculations.
* **Wall Polygons:** Do not represent walls as a simple Centerline + Thickness. Instead, generate explicit wall polygons by resolving junctions constructively (splitting panels) after topology is established.
* **Junction Cleanup:** Solve L-junctions, T-junctions, and X-junctions. Use `unary_union` only as a secondary cleanup fallback.

The TBM remains semantic; the CAD Kernel resolves precise spatial boundaries.

---

# Sprint 5 — Drawing Model

The Drawing Model is the CAD representation.

It is independent of SVG.

Supported primitives:

```text
Line

Polyline

Arc

Circle

Text

Hatch

Dimension

Leader

Symbol
```

No SVG should exist inside this module.

---

# Sprint 6 — Architectural Symbol Engine

Generate professional drafting symbols.

Implement:

Doors

* frame
* leaf
* swing arc

Windows

* sliding
* fixed
* casement

Stairs

* treads
* arrow
* UP/DOWN

Columns

North Arrow

Scale

Grid

Section Marks

Elevation Marks

All symbols must be vector-based.

---

# Sprint 7 — Dimension Engine

Automatically generate:

Overall dimensions

Room dimensions

Opening dimensions

Setbacks

Wall offsets

Implement collision-aware placement.

## Spatial Index Abstraction
Design the API with a decoupled spatial boundary:
```text
DimensionEngine ──> SpatialIndex (Abstract API)
```
* **MVP Phase:** Implement `SpatialIndex` using a simple search list.
* **Production Phase:** Swap the implementation to use an R-Tree (`shapely.strtree.STRtree`) under the hood to ensure rapid checks ($O(\log N)$) without altering the `DimensionEngine` code.

Pipeline:
```text
Candidate ──> Query SpatialIndex ──> Collision? ──(Yes)──> Move Outward ──> Repeat
                                 └──(No)───> Accept & Draw
```

---

# Sprint 8 — Annotation Engine

Automatically generate:

Room Name

Room Area

Door Tags

Window Tags

Wall Tags

Scale

North Arrow

Revision

Notes

Annotations must avoid wall collisions.

---

# Sprint 9 — Layer Engine

Implement CAD-style layers.

Required layers:

```text
Walls

Doors

Windows

Dimensions

Annotations

Furniture

Structural

Grid

Utilities
```

Every drawing element belongs to exactly one layer.

---

# Sprint 10 — Sheet Generator

Generate printable sheets.

Support:

A4

A3

A2

A1

Landscape

Portrait

Automatically create:

Title Block

Project Information

Drawing Number

Revision

Date

Scale

---

# Sprint 11 — SVG Renderer

SVG is an export format only.

Do not store business logic in SVG.

Requirements:

* **Sheet-Scale Decoupling:** Model geometry scales with the viewport scale factor $S$, but text, annotations, dimension ticks, and arrowheads are drawn in absolute sheet units (e.g., $2.5\text{ mm}$ text). Text sizes must never be stretched or distorted by model scaling.
* `<g>` groups for CAD layers
* semantic IDs matching TBM entity IDs
* scalable viewBox
* engineering scale transformation
* print-ready output

---

# Sprint 12 — Interactive Viewer

Implement:

Pan

Zoom

Selection

Hover

Layer Toggle

Measurement

Highlight

The viewer only displays data.

It never computes geometry.

---

# Sprint 13 — Export Engine

Support:

SVG

PDF

Future:

DXF

IFC

The renderer should be replaceable without changing the Drawing Model.

---

# Repository Structure

```text
backend/
│
├── core/
│   ├── tbm/
│   │   ├── building.py
│   │   ├── plot.py
│   │   ├── floor.py
│   │   ├── room.py
│   │   ├── wall.py
│   │   ├── opening.py
│   │   └── junction.py
│   │
│   ├── cad_kernel/
│   │   ├── geometry_service.py   <-- Shapely/NumPy abstraction
│   │   └── spatial_index.py
│   │
│   └── design_rules/
│       ├── nbc_rules.py          <-- Code compliance checks
│       ├── stair_feasibility.py  <-- Early optimization feedback
│       └── rule_engine.py
│
├── services/
│   ├── relationship_builder.py
│   ├── graph_builder.py
│   ├── geometry_resolver.py
│   ├── drawing_generator.py
│   ├── dimension_engine.py
│   └── annotation_engine.py
│
└── drawing/
    ├── primitives/
    ├── symbols/
    ├── layers/
    ├── sheets/
    └── exporters/

frontend/
│
└── viewer/
    ├── svg_renderer/
    └── cad_controls/
```

---

# Technology Stack

| Layer | Technology |
| :--- | :--- |
| **Domain Model** | Python `dataclasses` + Pydantic |
| **Graph Analysis** | `networkx` |
| **Geometry (CAD Kernel)** | `shapely`, `numpy` (hidden behind `GeometryService`) |
| **Spatial Index** | `shapely.strtree.STRtree` (abstracted behind `SpatialIndex` API) |
| **SVG Export** | `svgwrite` or direct XML generation |
| **PDF Export** | `reportlab` |
| **DXF Export (Future)** | `ezdxf` |
| **Frontend Viewer** | React + SVG |

---

# Coding Standards

Mandatory:

* SOLID principles
* Clean Architecture
* Abstraction of third-party libraries (especially CAD geometry engine)
* Domain-driven design for the TBM
* Pure functions for geometry calculations
* Immutable IDs
* Unit tests for every service
* Type hints throughout the Python codebase

---

# Performance Goals

Target:

* Generate a complete residential engineering drawing in **under 2 seconds**.
* Geometry resolution should scale linearly with the number of rooms and walls.
* SVG output should remain lightweight and editable.

---

# Future Compatibility

The implementation **must not** be tightly coupled to 2D rendering.

The completed architecture must support this future evolution without redesign:

```text
Topological Building Model (TBM)
              │
      ┌───────┴────────┐
      │                │
      ▼                ▼
Geometry Resolver   Graph Analysis
      │
      ▼
Drawing Model
      │
 ┌────┴────┐
 ▼         ▼
SVG      Future Mesh Generator
             │
             ▼
Procedural 3D Engine
             │
             ▼
React Three Fiber
```

The future 3D engine must consume the same Geometry Resolver output used by the 2D drawing engine, ensuring consistency between engineering drawings and 3D visualization.

---

# Success Criteria

The implementation is complete when it can:

* Build a validated **Topological Building Model (TBM)** from the MILP output.
* Resolve wall intersections into accurate architectural geometry.
* Generate professional engineering drawings with proper wall joins, drafting-standard door/window/stair symbols, automatic dimensions, annotations, layers, title blocks, and printable SVG/PDF output.
* Maintain a clean separation between **semantic model**, **geometry**, **drawing model**, and **renderer**.
* Provide a stable foundation so that a future procedural 3D engine can be added by implementing a new renderer, without changing the TBM or Geometry Resolver. This guarantees that both 2D engineering drawings and future 3D models are always generated from the same underlying building definition.
