# BuildForgeAI | Constraint-Driven Building Compiler

**BuildForgeAI** is a spatial compiler that translates natural language requirements into legally compliant, structurally validated, and ventilation-optimized 3D building blueprints for dense urban real estate.

---

## 🛑 The Problem

Current generative AI design tools fail in dense urban environments. They treat house planning as an image-generation (diffusion) problem rather than a mathematical constraint problem.

In the reality of Indian real estate (e.g., fractional 43.75 × 41 ft plots, closed boundaries on three sides, and independent G+2 rental floors), existing AI tools hallucinate unbuildable layouts. They routinely ignore:

1. **Municipal Setbacks:** Drawing walls over legal boundaries.
2. **Structural Physics:** Failing to align load-bearing columns vertically across multiple independent floors.
3. **Environmental Reality:** Placing windows on shared boundary walls, suffocating inner rooms in landlocked plots.

As a result, homeowners and architects waste weeks in manual "schematic design" revision loops.

---

## 💡 The Solution

We realized the solution isn't drawing a floor plan—it is calculating one.

**Uncharted** decouples the AI from the spatial math. We use Large Language Models strictly to parse human intent. The actual wall placement, column alignment, and spatial packing are handled deterministically by a **Mixed-Integer Linear Programming (MILP)** solver and computational geometry.

Our engine ensures:

* **Zero Structural Hallucinations:** Columns and plumbing shafts are locked as immutable 3D boundaries before any rooms are placed.
* **Guaranteed Ventilation:** A topological graph evaluates airflow. If a room is landlocked, the engine procedurally carves Open-To-Sky (OTS) structural shafts through all floors.
* **Legal Compliance:** Municipal FAR/FSI and setbacks are applied via hard geometric subtractions, ensuring the output is instantly buildable.

---

## ⚙️ The Implementation Pipeline

The system architecture acts as an Abstract Syntax Tree (AST) compiler for physical space, executing in five distinct phases:

### 1. Intent Parsing Layer

* **Input:** Natural language prompt & plot dimensions.
* **Execution:** The LLM tokenizes the input into a strict JSON parameter schema. No spatial reasoning occurs here.

### 2. Topological Semantic Layer

* **Execution:** Converts the JSON into a **Directed Acyclic Graph (DAG)** / Hasse Diagram.
* **Validation:** Mathematically proves the privacy flow (Public → Semi-Private → Private) and adjacency rules. If a guest must walk through a bedroom to reach the kitchen, the compilation fails.

### 3. Geometric Constraint Layer

* **Execution:** Utilizes 2D/3D boolean operations to subtract local municipal setbacks from the raw plot polygon.
* **Validation:** Calculates the maximum buildable envelope and drops immutable vertical circulation cores (staircases/lifts) that span all G+2 floors.

### 4. Optimization Solver

* **Execution:** An Operations Research engine (MILP) mathematically packs the validated Room Graph into the buildable polygons.
* **Refinement:** Uses Non-dominated Sorting Genetic Algorithm II (NSGA-II) to iterate layouts, maximizing cross-ventilation and daylight scores.

### 5. 3D WebGL Rendering

* **Execution:** The React frontend reads the raw mathematical coordinate arrays and extrudes them into 3D walls, generating a fully interactive blueprint.

---

## 🛠️ Technology Stack

**Frontend & Interface**

* **Framework:** React.js / Next.js
* **Visualization:** Three.js / React Three Fiber (WebGL 3D Rendering)
* **Styling:** Tailwind CSS / Framer Motion

**Backend & API Orchestration**

* **Framework:** Python / FastAPI
* **Intent Parser:** OpenAI API / Google Gemini API (Strict JSON Mode)

**Core Math & Optimization Engine**

* **Computational Geometry:** Shapely (Polygon math, Setback subtraction)
* **Graph Theory:** NetworkX (Topological validation, Ventilation routing)
* **Operations Research:** PuLP / SciPy.optimize (MILP Constraint Solving)

---

## 🚀 Getting Started (Local Development)

### Prerequisites

* Python 3.10+
* Node.js 18+

### Backend Setup (Geometry Engine)

```bash
# Clone the repository
git clone https://github.com/mohdsarfraz08/plot-map.git
cd building-compiler/backend

# Create virtual environment and install OR/Math dependencies
python -m venv venv
venv\Scripts\activate  # On macos use `source venv/bin/activate`
pip install -r requirements.txt

# Run the FastAPI server
uvicorn app.main:app --reload

```

### Frontend Setup (WebGL Interface)

```bash
cd ../frontend

# Install dependencies
npm install

# Start the development server
npm run dev

```

---

## 🎯 Vision

To democratize structural engineering and architectural compliance across Bharat, empowering individual landowners and local builders to generate safe, optimized, and buildable homes in minutes instead of months.
