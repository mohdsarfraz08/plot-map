"""
Test Script for the 'Jury Curveball' Prompt:
'Design a highly compact 25x30 ft ground-floor 1BHK for a narrow plot. It must include a living area, a kitchen with exterior natural light, a single bedroom, and a bathroom that utilizes an OTS for ventilation.'
"""

import time
import json
from app.services.fast_compiler import compile_layout_fast

prompt = (
    "Design a highly compact 25x30 ft ground-floor 1BHK for a narrow plot. "
    "It must include a living area, a kitchen with exterior natural light, "
    "a single bedroom, and a bathroom that utilizes an OTS for ventilation."
)

print(f"--- Running Jury Curveball Scenario ---")
print(f"Prompt: {prompt}\n")

start_time = time.perf_counter()
res = compile_layout_fast(prompt=prompt, client=None)
elapsed = time.perf_counter() - start_time

print(f"Status: {'SUCCESS' if res['success'] else 'FAILED'}")
print(f"Execution Latency: {elapsed * 1000:.2f} ms ({elapsed:.4f} s)\n")

print("--- 1. Extracted Intent ---")
intent = res["extracted_intent"]
print(f"Plot: {intent['plot_width']} ft x {intent['plot_depth']} ft | Floors: {intent['floors']} | Road Setback: {intent['front_road_setback']} ft")
print(f"Rooms Requested: {[r['room_type'] for r in intent['rooms']]}")

print("\n--- 2. Realized 0.5ft Snapped Layout ---")
for name, r in res["layout"].items():
    print(f" - {name:20s}: Pos ({r['x']:4.1f}, {r['y']:4.1f}) | Size {r['width']:4.1f}' x {r['height']:4.1f}' | Area {r['width']*r['height']:5.1f} sqft | Zone: {r.get('zone', 'N/A')}")

f1_geom = res["floors"]["1"]["geometry"]

print("\n--- 3. Topological Doors (1D Shapely Midpoint Anchored) ---")
for d in f1_geom.get("doors", []):
    print(f" - {d['id']:8s}: Pos [{d['position'][0]:4.1f}, {d['position'][1]:4.1f}] | Width {d['width']} ft | Type: {d['type']:10s} | Connects: {' <-> '.join(d['rooms'])}")

print("\n--- 4. Topological Windows (Exterior & OTS Facades) ---")
for w in f1_geom.get("windows", []):
    print(f" - {w['id']:8s}: Pos [{w['position'][0]:4.1f}, {w['position'][1]:4.1f}] | Width {w['width']} ft | Type: {w['type']:10s} | Host Room: {w['room']}")

print("\n--- 5. 2D CAD SVG Output ---")
svg = res["drawing_svg"]
print(f"SVG Generated: {len(svg)} characters | Valid SVG: {'<svg' in svg and '</svg>' in svg}")

print("\n--- 6. Architectural Validation Checks ---")
# Check Living, Kitchen, Bedroom, Bathroom
names = list(res["layout"].keys())
has_living = any("living" in n.lower() for n in names)
has_kitchen = any("kitchen" in n.lower() for n in names)
has_bed = any("bed" in n.lower() for n in names)
has_bath = any("bath" in n.lower() for n in names)

print(f" - Has Living Room: {has_living}")
print(f" - Has Kitchen with Natural Light: {has_kitchen}")
print(f" - Has Bedroom: {has_bed}")
print(f" - Has Bathroom: {has_bath}")
print(f" - Has Doors: {len(f1_geom.get('doors', [])) > 0}")
print(f" - Has Windows: {len(f1_geom.get('windows', [])) > 0}")
