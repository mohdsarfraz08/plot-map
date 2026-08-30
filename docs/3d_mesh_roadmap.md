For **Antigravity**, I wouldn't build this as "a 3D generator." I would build it as a **Procedural Building Generation Engine (PBGE)**. The MILP optimizer remains the brain, while the PBGE becomes the visualization engine. This separation will make the system maintainable, extensible, and suitable for future features like style customization and interior generation.

# Antigravity Architecture

```text
                    USER INPUT
                         │
                         ▼
                 AI Requirement Parser
                         │
                         ▼
              Constraint Validation Engine
                         │
                         ▼
                 MILP Optimization Engine
                         │
                         ▼
              Building Information Model (BIM)
                         │
       ┌─────────────────┴─────────────────┐
       │                                   │
       ▼                                   ▼
 Validation Engine               Cost Estimation
       │
       ▼
 Procedural Building Generator
       │
       ▼
 Style Engine
       │
       ▼
 Material Engine
       │
       ▼
 Environment Generator
       │
       ▼
 Interactive 3D Model
```

---

# Phase 1 — Standardize the MILP Output

**Goal:** The optimizer should output a structured building description, not meshes.

Example:

```json
{
  "plot": {},
  "rooms": [],
  "walls": [],
  "doors": [],
  "windows": [],
  "stairs": [],
  "roof": {},
  "floors": [],
  "structural": {}
}
```

### Deliverables

* Building JSON schema
* Room graph
* Wall graph
* Door graph
* Window graph
* Structural metadata

This becomes the single source of truth.

---

# Phase 2 — Geometry Engine

**Purpose:** Convert mathematical data into clean geometric primitives.

Modules:

```
geometry/
    room.py
    wall.py
    opening.py
    roof.py
    stair.py
    mesh.py
```

Responsibilities:

* Generate wall centerlines
* Extrude walls constructively using split panels (no CSG boolean subtraction)
* Create wall thickness
* Generate floors and ceilings
* Calculate door and window opening gaps dynamically during extrusion
* Merge procedural meshes

No materials.
No colors.
No styling.

Only geometry.

---

# Phase 3 — Architectural Components

Replace cubes with procedural architectural objects.

### Wall Generator

Input

```
Line Segment
```

Output

```
Wall Mesh
```

Features

* Thickness
* Height
* Inner surface
* Outer surface
* Top cap
* Wall joins
* Corner cleanup

---

### Door Generator

Input

```
Opening
```

Output

```
Door Frame
Door
Threshold
Handle
```

Parameters

```
width
height
frame thickness
style
material
```

---

### Window Generator

Input

```
Opening
```

Output

```
Frame
Glass
Sill
Trim
```

Supports

* Sliding
* Casement
* Fixed
* Bay
* Floor-to-ceiling

---

### Stair Generator

Generate

* Straight
* L-shaped
* U-shaped
* Spiral (future)

Automatically calculate

```
rise

run

landing

handrails
```

---

### Roof Generator

Support

* Flat
* Sloped
* Gable
* Hip
* Shed

Generated from

```
Building Footprint
```

Not manually modeled.

---

# Phase 4 — Mesh Cleanup Engine

This phase removes the "boxy" appearance.

Tasks

### Bevel Engine

Apply

```
2–5 cm bevel
```

to visible edges.

---

### Corner Merging

Remove overlapping geometry.

---

### Normal Correction

Smooth shading.

---

### Constructive Panel Splitting

Avoid heavy boolean mesh differences. Instead:
* Generate discrete watertight panel segments around openings (Left Panel, Header, Right Panel, Sill).
* Mathematically merge adjacent panel vertices to guarantee clean quad topology and avoid non-manifold meshes.

---

### Mesh Optimization

Merge

* coplanar faces
* duplicate vertices

Reduce polygon count without losing quality.

---

# Phase 5 — Style Engine

This is where buildings become visually distinct.

Folder

```
styles/

modern/

minimal/

classical/

villa/

indian/

commercial/
```

Each style defines rules such as:

```yaml
roof:
    flat

walls:
    white_plaster

windows:
    black_aluminium

door:
    teak

balcony:
    glass

parapet:
    modern
```

Changing the style never changes the optimized layout.

---

# Phase 6 — Material Engine

Every mesh receives materials procedurally.

Example

```
Wall
↓

Exterior Paint

↓

Normal Map

↓

Roughness

↓

Ambient Occlusion
```

Materials include:

* Concrete
* Brick
* Stone
* Marble
* Wood
* Glass
* Metal
* Tiles
* Grass

---

# Phase 7 — Facade Engine

This gives the building architectural character.

Responsibilities

Automatically generate

* Window trims
* Cornices
* Pillars
* Roof overhangs
* Balcony railings
* Fascia boards
* Gutters
* Exterior lights

Generated using style rules.

---

# Phase 8 — Interior Generator

Based on room type.

Living Room

```
Sofa

TV

Center Table
```

Kitchen

```
Counter

Cabinets

Sink
```

Bedroom

```
Bed

Wardrobe

Study Table
```

Bathroom

```
WC

Sink

Shower
```

Everything positioned procedurally while respecting circulation.

---

# Phase 9 — Environment Generator

Generate

* Compound wall
* Main gate
* Driveway
* Walkways
* Lawn
* Trees
* Shrubs
* Street
* Lighting
* Parking

Derived from remaining plot area.

---

# Phase 10 — Rendering Layer & Hybrid Instance Placement

Three.js should only render what the engine produces. To minimize network payload and optimize rendering:
* **Unique Procedural Meshes:** Walls, floors, slabs, and roofs are generated on the backend and sent as unique meshes.
* **Hybrid Instance Placement:** Windows, doors, stairs, and furniture are sent as lightweight references containing a logical `assetId` and transform metadata (3D position, rotation, scale).
* **Asset Registry:** Decouples file paths from geometry. The procedural engine requests a logical asset ID (e.g., `door_modern_01`), and the frontend's Asset Manager loads, caches, clones, and instances the corresponding GLTF model from `public/assets/` or a CDN.

```
Engine (Mesh + Transforms)
        │
        ├── Unique meshes ──────> Direct render
        └── Asset transforms ───> InstancedMesh (cloned GLB)
```

Three.js should not contain building-generation logic.

---

# Technology Stack

* **Backend:** Python 3.12+, NumPy (vector math), Shapely (2D offsets, intersections, boundaries), Trimesh (extrusion, UV generation, mesh synthesis), Pydantic, FastAPI.
* **Frontend:** React, Three.js, React Three Fiber, Drei, GLTFLoader, Meshopt Decoder, DRACO Compression, InstancedMesh.

---

# Proposed Repository Structure

```
antigravity/

core/
│
├── parser/
├── milp/
├── validator/
├── bim/
│
├── geometry/
│   ├── room.py
│   ├── wall.py
│   ├── roof.py
│   ├── stair.py
│   ├── opening.py
│   └── mesh.py
│
├── generators/
│   ├── wall_generator.py
│   ├── roof_generator.py
│   ├── door_generator.py
│   ├── window_generator.py
│   ├── stair_generator.py
│   ├── balcony_generator.py
│   └── facade_generator.py
│
├── style_engine/
│
├── materials/
│
├── assets/
│
├── interiors/
│
├── environment/
│
└── renderer/
```

---

# Development Roadmap

| Sprint        | Goal                                                            | Success Criteria                                                                               |
| ------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| **Sprint 1**  | Standardize MILP output into a Building Information Model (BIM) | A complete JSON model describing rooms, walls, doors, windows, floors, and structural metadata |
| **Sprint 2**  | Build the Geometry Engine                                       | Procedurally generate clean constructive walls (no CSG), floors, and ceiling meshes            |
| **Sprint 3**  | Create architectural generators                                 | Define logical asset IDs and transforms for windows, doors, and stairs                         |
| **Sprint 4**  | Add mesh cleanup                                                | Eliminate overlapping vertices, align normals, and optimize quad geometry topology             |
| **Sprint 5**  | Implement the Style Engine & Asset Registry                     | Map styles to materials/PBR textures and GLTF asset bundles dynamically                        |
| **Sprint 6**  | Add materials and facade details                                | Produce visually realistic exteriors using procedural facade generation rules                  |
| **Sprint 7**  | Generate interiors                                              | Furnish rooms procedurally using keeping-out clearance grids                                   |
| **Sprint 8**  | Build the environment                                           | Generate compound walls, landscaping, pathways, and site context                               |
| **Sprint 9**  | Integrate with Three.js                                         | Render custom meshes + hybrid instanced components (GLTFLoader + InstancedMesh)                |
| **Sprint 10** | Performance optimization                                        | Support large multi-storey buildings while maintaining interactive frame rates                 |

## Long-term Vision

The engine should evolve into a **Building Information Model (BIM) → Procedural Generation → Rendering** pipeline, not a mesh generator. The MILP solver decides **what** the building is, the procedural engine decides **how** it is constructed geometrically, the style engine decides **how it looks**, and the renderer simply displays the result.

That separation will make Antigravity scalable enough to support future capabilities like multiple architectural styles, instant design variants, editable buildings, interior generation, cost estimation, structural analysis, and even IFC/BIM export without redesigning the core architecture.
