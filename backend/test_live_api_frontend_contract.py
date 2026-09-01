"""
Frontend Contract & HTTP Integration Test.
Simulates the exact HTTP requests sent by Home.jsx in the frontend,
and verifies that all data structures expected by BuildingViewer3D, CADViewer2D, and ResultsPanel
are 100% present, valid, and populated.
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

frontend_test_scenarios = [
    {
        "name": "Scenario 1: 30x40 2BHK Urban",
        "payload": {
            "prompt": "A G+0 house on a 30x40 ft plot with a front road setback of 5.0 ft. Design brief: Design a modern 2BHK with living room, kitchen, dining, 2 bedrooms and 2 bathrooms"
        }
    },
    {
        "name": "Scenario 2: 20x50 Rowhouse",
        "payload": {
            "prompt": "A G+0 house on a 20x50 ft plot with a front road setback of 5.0 ft. Design brief: Design a linear rowhouse with front living, linear circulation spine, kitchen, dining and 2 bedrooms"
        }
    },
    {
        "name": "Scenario 3: 50x35 Luxury Villa",
        "payload": {
            "prompt": "A G+0 house on a 50x35 ft plot with a front road setback of 5.0 ft. Design brief: Design a spacious 3BHK villa with grand foyer, formal living wing, open kitchen/dining and master suites"
        }
    },
    {
        "name": "Scenario 4: 25x30 1BHK + OTS",
        "payload": {
            "prompt": "A G+0 house on a 25x30 ft plot with a front road setback of 5.0 ft. Design brief: Design a compact 1BHK with living room, kitchen with natural light, bedroom and bathroom with OTS lightwell"
        }
    },
    {
        "name": "Scenario 5: 40x40 G+1 Duplex",
        "payload": {
            "prompt": "A G+1 house on a 40x40 ft plot with a front road setback of 5.0 ft. Design brief: Design a G+1 duplex house with living, kitchen, bedrooms and internal staircase"
        }
    }
]

def test_frontend_http_contract():
    """Verify all frontend HTTP contract expectations."""
    for test in frontend_test_scenarios:
        print(f"\n--- Testing HTTP Contract: {test['name']} ---")
        
        response = client.post("/api/compile", json=test["payload"])
        assert response.status_code == 200, f"HTTP Error {response.status_code}: {response.text}"
        
        data = response.json()
        
        # 1. Top-Level Contract Fields
        assert data["success"] is True or data["status"] == "success"
        assert "layout" in data and len(data["layout"]) >= 3
        assert "floors" in data and "1" in data["floors"]
        assert "metadata" in data
        assert "metrics" in data
        assert "drawing_svg" in data and len(data["drawing_svg"]) > 100
        
        # 2. 3D Viewer Contract Fields
        f1 = data["floors"]["1"]
        assert "layout" in f1 and len(f1["layout"]) >= 3
        assert "geometry" in f1
        geom = f1["geometry"]
        assert "walls" in geom and len(geom["walls"]) > 0
        assert "doors" in geom and len(geom["doors"]) > 0
        assert "windows" in geom and len(geom["windows"]) > 0
        
        # 3. 2D CAD SVG Contract
        svg = data["drawing_svg"]
        assert "<svg" in svg and "</svg>" in svg
        
        # 4. Metrics Panel Contract
        metrics = data["metrics"]
        assert "plot_coverage_pct" in metrics
        assert "fsi" in metrics
        assert "cross_ventilation_score" in metrics
        assert "daylighting_score" in metrics
        assert "buildability_score" in metrics
        
        print(f"  [PASS] HTTP 200 OK | Layout: {len(data['layout'])} rooms | Walls: {len(geom['walls'])} | Doors: {len(geom['doors'])} | Windows: {len(geom['windows'])}")

if __name__ == "__main__":
    test_frontend_http_contract()
    print("\nALL FRONTEND HTTP CONTRACT TESTS PASSED!")
