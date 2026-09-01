"""
Live Benchmark Demonstration Scenarios Test.
Executes and validates the 4 presentation scenarios on the Fast-Track Hybrid Compiler:
1. Standard Urban 30x40 2BHK
2. Narrow 20x50 Rowhouse
3. Wide 50x35 Luxury Villa
4. Multi-Floor 40x40 G+1 Duplex (with Staircase & Mumty Cutout)
"""

import time
import pytest
from app.services.fast_compiler import compile_layout_fast


@pytest.mark.parametrize(
    "scenario_name,prompt,expected_rooms,min_doors",
    [
        (
            "Scenario 1: Standard Urban 30x40 2BHK",
            "Design a 2BHK house on a 30x40 plot with living room, kitchen, dining, 2 bedrooms and 2 bathrooms",
            ["Living Room", "Kitchen", "Master Bedroom"],
            3,
        ),
        (
            "Scenario 2: Narrow 20x50 Rowhouse",
            "Design a linear house on a 20x50 plot with living room, kitchen, and 2 bedrooms",
            ["Living Room", "Kitchen", "Master Bedroom"],
            2,
        ),
        (
            "Scenario 3: Wide 50x35 Villa",
            "Design a spacious 3BHK villa on a 50x35 plot with large living room, open kitchen and 3 bedrooms",
            ["Living Room", "Kitchen & Dining", "Master Bedroom"],
            3,
        ),
        (
            "Scenario 4: G+1 Duplex with Staircase",
            "Design a G+1 duplex house on a 40x40 plot with living, kitchen, bedrooms and internal staircase",
            ["Living Room", "Kitchen", "Master Bedroom"],
            3,
        ),
    ],
)
def test_live_benchmark_scenario(scenario_name: str, prompt: str, expected_rooms: list, min_doors: int):
    """Verify each demo scenario compiles in < 1.0s with clean 2D SVG and 3D payload."""
    start_time = time.perf_counter()
    response = compile_layout_fast(prompt=prompt, client=None)
    elapsed = time.perf_counter() - start_time

    print(f"\n[{scenario_name}] Fast-Track Compiled in {elapsed*1000:.1f}ms ({elapsed:.3f}s)")

    # Strict Sub-Second Latency Gate for live presentation
    assert elapsed < 1.0, f"Compilation took too long: {elapsed:.2f}s"

    # Verify Response Integrity
    assert response["success"] is True
    assert response["layout"] is not None
    assert len(response["layout"]) >= 3

    # Check that required rooms are present
    layout_names = list(response["layout"].keys())
    for r_name in expected_rooms:
        assert any(r_name.lower() in name.lower() for name in layout_names), f"Missing {r_name} in {layout_names}"

    # Verify Floor 1 Geometry
    f1 = response["floors"]["1"]
    geom = f1["geometry"]
    assert len(geom["walls"]) > 0
    assert len(geom["doors"]) >= min_doors
    assert len(geom["windows"]) > 0

    # Verify 2D CAD SVG
    assert "<svg" in response["drawing_svg"]
    assert "</svg>" in response["drawing_svg"]
