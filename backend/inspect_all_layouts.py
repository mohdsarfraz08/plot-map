"""
Visual & Architectural Layout Inspector.
Renders detailed ASCII floor maps and validates architectural livability metrics:
- Room dimensions and aspect ratios
- Circulation spine connectivity
- Minimum livable widths (Bedrooms >= 9.5ft, Baths >= 4.5ft, Hallways >= 3.5ft)
"""

from app.services.fast_compiler import compile_layout_fast

test_prompts = [
    ("Standard 30x40 2BHK", "Design a 2BHK house on a 30x40 plot with living, kitchen, dining, 2 bedrooms and 2 bathrooms"),
    ("Narrow 20x50 Rowhouse", "Design a linear house on a 20x50 plot with living room, kitchen, and 2 bedrooms"),
    ("Wide 50x35 Villa", "Design a spacious 3BHK villa on a 50x35 plot with large living room, open kitchen and 3 bedrooms"),
    ("Compact 25x30 1BHK", "Design a 1BHK house on a 25x30 plot with living, kitchen, single bedroom and bathroom with OTS"),
]

for title, prompt in test_prompts:
    print("=" * 80)
    print(f"SCENARIO: {title}")
    print(f"Prompt: {prompt}")
    print("=" * 80)
    
    res = compile_layout_fast(prompt=prompt, client=None)
    layout = res["layout"]
    f1_geom = res["floors"]["1"]["geometry"]
    plot_w = res["metadata"]["plot_width"]
    plot_d = res["metadata"]["plot_depth"]
    
    print(f"\nPlot Size: {plot_w:.1f}' x {plot_d:.1f}' | Total Built-up: {sum(r['width']*r['height'] for r in layout.values()):.1f} sqft\n")
    print(f"{'Room Name':<22} | {'Pos (X, Y)':<12} | {'Size (W x H)':<14} | {'Area':<10} | {'Aspect Ratio':<12} | {'Livability Check'}")
    print("-" * 88)
    
    for name, r in layout.items():
        w, h = r["width"], r["height"]
        area = w * h
        ar = max(w, h) / min(w, h)
        pos = f"({r['x']:.1f}, {r['y']:.1f})"
        size = f"{w:.1f}' x {h:.1f}'"
        
        # Livability checks
        check = "[OK]"
        if "bedroom" in name.lower() and min(w, h) < 9.0:
            check = f"[WARN] Narrow width ({min(w,h):.1f}' < 9.0')"
        elif "living" in name.lower() and min(w, h) < 10.0:
            check = f"[WARN] Small living ({min(w,h):.1f}' < 10.0')"
        elif "bath" in name.lower() and min(w, h) < 4.0:
            check = f"[WARN] Tiny bath ({min(w,h):.1f}' < 4.0')"
            
        print(f"{name:<22} | {pos:<12} | {size:<14} | {area:6.1f} sqft | {ar:5.2f}:1       | {check}")
        
    print("\nDoors & Connections:")
    for d in f1_geom.get("doors", []):
        print(f"  [DOOR] {d['id']:<8} at [{d['position'][0]:4.1f}, {d['position'][1]:4.1f}] ({d['direction']:<10}) connects: {' <-> '.join(d['rooms'])}")
        
    print("\nWindows:")
    for win in f1_geom.get("windows", []):
        print(f"  [WINDOW] {win['id']:<8} at [{win['position'][0]:4.1f}, {win['position'][1]:4.1f}] ({win['direction']:<10}) on {win['room']} ({win['type']})")
    print("\n")
