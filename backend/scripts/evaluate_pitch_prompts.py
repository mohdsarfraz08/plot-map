import os
import sys
import json
import math

sys.path.insert(0, os.path.abspath("."))

from app.schemas.compile import CompileRequest
from app.services.orchestration.pipeline_orchestrator import PipelineOrchestrator

PROMPTS = [
    (
        "1. 40x40 2BHK",
        "40x40 ground-floor home with 2 bedrooms, living room, kitchen and 2 bathrooms."
    ),
    (
        "2. 30x40 3BHK",
        "30x40 compact 3 bedroom ground-floor home with 2 bathrooms and good ventilation."
    ),
    (
        "3. 40x50 Spacious 2BHK",
        "40x50 spacious ground-floor home with 2 bedrooms, living room, kitchen and bathroom."
    ),
    (
        "4. 25x40 1BHK",
        "25x40 compact 1 bedroom ground-floor home with living room, kitchen and bathroom."
    ),
    (
        "5. 40x40 2-Family",
        "40x40 ground-floor home for two families with separate living spaces and private access."
    ),
    (
        "6. 30x50 Ventilated 2BHK",
        "30x50 ground-floor home with 2 bedrooms, living room, kitchen, bathroom and maximum natural ventilation."
    ),
]

def calculate_architectural_quality_score(layout, geometry, walls, doors, windows):
    score = 100.0
    deductions = []
    
    rooms = list(layout.values())
    if not rooms:
        return 0.0, ["No rooms generated"]
        
    for r in rooms:
        w, h = r["width"], r["height"]
        ar = max(w/h, h/w)
        if ar > 1.50:
            score -= 10
            deductions.append(f"Room {r.get('type')} aspect ratio {ar:.2f} exceeds 1.50")
        elif ar > 1.40:
            score -= 3
            
        area = w * h
        rtype = str(r.get("type", "")).lower()
        if "bath" in rtype and area > 75.0:
            score -= 10
            deductions.append(f"Bathroom oversized ({area:.1f} sqft)")
        elif "kitchen" in rtype and area > 140.0:
            score -= 10
            deductions.append(f"Kitchen oversized ({area:.1f} sqft)")
            
    if not doors:
        score -= 30
        deductions.append("Zero doors generated")
    else:
        has_entrance = any(d.get("type") == "entrance" or "exterior" in str(d.get("rooms", "")).lower() for d in doors)
        if not has_entrance:
            score -= 15
            deductions.append("Missing main entrance door")
            
    if not windows:
        score -= 15
        deductions.append("Zero windows generated")
        
    return max(0.0, score), deductions

def run_evaluation():
    from app.services.orchestration.session_registry import SessionRegistry
    orchestrator = PipelineOrchestrator(session_registry=SessionRegistry())
    results = []
    
    out_dir = os.path.abspath("pitch_eval_output")
    os.makedirs(out_dir, exist_ok=True)
    
    for label, prompt_text in PROMPTS:
        print(f"\n{'='*80}\nEVALUATING: {label}\nPrompt: '{prompt_text}'\n{'='*80}")
        req = CompileRequest(prompt=prompt_text)
        try:
            resp = orchestrator.compile(req, client=None)
            layout = resp.layout or {}
            geometry = resp.geometry or {}
            walls = geometry.get("walls", [])
            doors = geometry.get("doors", [])
            windows = geometry.get("windows", [])
            svg_content = resp.drawing_svg or ""
            
            svg_filename = f"{label.replace(' ', '_').replace('.', '')}.svg"
            svg_path = os.path.join(out_dir, svg_filename)
            with open(svg_path, "w", encoding="utf-8") as f:
                f.write(svg_content)
                
            q_score, deductions = calculate_architectural_quality_score(layout, geometry, walls, doors, windows)
            
            print(f"Status: SUCCESS | Architectural Quality Score: {q_score:.1f}/100")
            print("\nRoom Coordinate Table:")
            print(f"{'Room ID':<10} | {'Type':<12} | {'Position (x,y)':<16} | {'Dimensions (WxH)':<18} | {'Area':<12} | {'Aspect Ratio'}")
            print("-" * 85)
            for rname, r in layout.items():
                w, h = r["width"], r["height"]
                area = w * h
                ar = max(w/h, h/w)
                print(f"{rname:<10} | {r.get('type',''):<12} | ({r['x']:4.1f}, {r['y']:4.1f})        | {w:4.1f} x {h:4.1f} ft        | {area:5.1f} sqft  | {ar:.2f} : 1")
                
            print(f"\n3D Geometry & Openings: {len(walls)} walls, {len(doors)} doors, {len(windows)} windows")
            print("Doors:")
            for d in doors:
                pos = d.get("position", [0, 0])
                print(f"  * {d.get('id')}: type={d.get('type')}, pos=({pos[0]:.1f}, {pos[1]:.1f}), width={d.get('width')}ft, rooms={d.get('rooms')}")
                
            print("Windows:")
            for w in windows:
                pos = w.get("position", [0, 0])
                print(f"  * {w.get('id')}: type={w.get('type')}, pos=({pos[0]:.1f}, {pos[1]:.1f}), width={w.get('width')}ft, room={w.get('room')}")
                
            results.append({
                "label": label,
                "prompt": prompt_text,
                "score": q_score,
                "rooms": len(layout),
                "doors": len(doors),
                "windows": len(windows),
                "walls": len(walls),
                "svg": svg_path
            })
        except Exception as e:
            print(f"FAILED: {e}")
            results.append({
                "label": label,
                "prompt": prompt_text,
                "score": 0.0,
                "error": str(e)
            })

    print(f"\n{'='*80}\nFINAL PITCH EVALUATION SUMMARY\n{'='*80}")
    for r in results:
        if "error" in r:
            print(f"[FAIL] {r['label']}: FAILED ({r['error']})")
        else:
            print(f"[PASS] {r['label']}: Score={r['score']:.1f}/100 | {r['rooms']} rooms | {r['doors']} doors | {r['windows']} windows | SVG: {os.path.basename(r['svg'])}")

if __name__ == "__main__":
    run_evaluation()
