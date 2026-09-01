import math
from typing import List, Tuple
from app.drawing import Drawing, Line, Polyline, Arc, Circle, Text, Hatch, Dimension, Leader, Symbol, CADPrimitive

def export_drawing_to_svg(drawing: Drawing) -> str:
    """
    Exports a CAD Drawing to a high-quality, drafting-standard SVG string.
    Converts CAD y-up coordinate system to screen y-down coordinate system,
    wrapping elements in group layers for clean styling and visibility.
    """
    # 1. Determine bounding box of all elements to size the viewport
    all_xs: List[float] = []
    all_ys: List[float] = []
    
    # Simple bounds helper
    def collect_point(x: float, y: float):
        all_xs.append(x)
        all_ys.append(y)
        
    for el in drawing.elements:
        if isinstance(el, Line):
            collect_point(el.x1, el.y1)
            collect_point(el.x2, el.y2)
        elif isinstance(el, Polyline):
            for pt in el.points:
                collect_point(pt[0], pt[1])
        elif isinstance(el, Arc):
            collect_point(el.cx - el.radius, el.cy - el.radius)
            collect_point(el.cx + el.radius, el.cy + el.radius)
        elif isinstance(el, Circle):
            collect_point(el.cx - el.radius, el.cy - el.radius)
            collect_point(el.cx + el.radius, el.cy + el.radius)
        elif isinstance(el, Text):
            collect_point(el.x, el.y)
        elif isinstance(el, Hatch):
            for pt in el.boundary_points:
                collect_point(pt[0], pt[1])
        elif isinstance(el, Dimension):
            collect_point(el.x1, el.y1)
            collect_point(el.x2, el.y2)
            collect_point(el.dim_x, el.dim_y)
            
    if not all_xs or not all_ys:
        # Default empty viewport
        return '<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"></svg>'
        
    min_x, max_x = min(all_xs), max(all_xs)
    min_y, max_y = min(all_ys), max(all_ys)
    
    # Add a border margin for the SVG viewport
    margin = 2.0
    width = (max_x - min_x) + 2 * margin
    height = (max_y - min_y) + 2 * margin
    
    # Scale factor: 1 unit in feet = 15 pixels in SVG space
    scale = 20.0
    view_w = width * scale
    view_h = height * scale
    
    # Transformation helper: converts CAD coordinates to SVG screen coordinates
    def tx(x: float) -> float:
        return (x - min_x + margin) * scale
        
    def ty(y: float) -> float:
        # Flip Y-axis: CAD y-up to SVG y-down
        return (max_y + margin - y) * scale
        
    # Group elements by layer
    layer_groups = {layer: [] for layer in drawing.layers}
    layer_groups["default"] = []
    
    for el in drawing.elements:
        layer = el.layer if el.layer in layer_groups else "default"
        
        svg_elem = ""
        stroke_color = el.color
        stroke_w = el.stroke_width * 1.5
        
        if isinstance(el, Line):
            svg_elem = f'<line x1="{tx(el.x1):.2f}" y1="{ty(el.y1):.2f}" x2="{tx(el.x2):.2f}" y2="{ty(el.y2):.2f}" stroke="{stroke_color}" stroke-width="{stroke_w:.2f}" stroke-linecap="round" />'
            
        elif isinstance(el, Polyline):
            pts_str = " ".join([f"{tx(pt[0]):.2f},{ty(pt[1]):.2f}" for pt in el.points])
            if el.is_closed:
                svg_elem = f'<polygon points="{pts_str}" stroke="{stroke_color}" stroke-width="{stroke_w:.2f}" fill="none" stroke-linejoin="round" />'
            else:
                svg_elem = f'<polyline points="{pts_str}" stroke="{stroke_color}" stroke-width="{stroke_w:.2f}" fill="none" stroke-linecap="round" stroke-linejoin="round" />'
                
        elif isinstance(el, Arc):
            # Calculate start and end coordinates in screen space
            a1_rad = math.radians(el.start_angle)
            a2_rad = math.radians(el.end_angle)
            
            # CAD coordinates
            x1_cad = el.cx + el.radius * math.cos(a1_rad)
            y1_cad = el.cy + el.radius * math.sin(a1_rad)
            x2_cad = el.cx + el.radius * math.cos(a2_rad)
            y2_cad = el.cy + el.radius * math.sin(a2_rad)
            
            # Convert to SVG space
            sx, sy = tx(x1_cad), ty(y1_cad)
            ex, ey = tx(x2_cad), ty(y2_cad)
            r = el.radius * scale
            
            # Determine sweep direction and large arc flags
            angle_diff = (el.end_angle - el.start_angle) % 360
            large_arc = 1 if angle_diff > 180 else 0
            
            # Standard positive angles sweep CCW in CAD (which is CW in SVG y-down screen coordinates)
            sweep = 0  # y-down inversion sweeps counter-clockwise in SVG
            
            svg_elem = f'<path d="M {sx:.2f} {sy:.2f} A {r:.2f} {r:.2f} 0 {large_arc} {sweep} {ex:.2f} {ey:.2f}" stroke="{stroke_color}" stroke-width="{stroke_w:.2f}" fill="none" />'
            
        elif isinstance(el, Circle):
            svg_elem = f'<circle cx="{tx(el.cx):.2f}" cy="{ty(el.cy):.2f}" r="{(el.radius * scale):.2f}" stroke="{stroke_color}" stroke-width="{stroke_w:.2f}" fill="none" />'
            
        elif isinstance(el, Text):
            # Scale text font size: e.g., font_size = 10.0 => 10px
            f_size = el.font_size
            anchor_style = "middle" if el.anchor == "middle" else ("end" if el.anchor == "end" else "start")
            
            # Rotate transform
            rot_str = ""
            if el.rotation != 0.0:
                # Screen rotation is inverted due to Y inversion
                screen_rot = -el.rotation
                rot_str = f' transform="rotate({screen_rot:.2f}, {tx(el.x):.2f}, {ty(el.y):.2f})"'
                
            svg_elem = f'<text x="{tx(el.x):.2f}" y="{ty(el.y):.2f}" font-family="Outfit, Inter, sans-serif" font-size="{f_size:.1f}px" fill="{stroke_color}" text-anchor="{anchor_style}"{rot_str} dominant-baseline="middle">{el.content}</text>'
            
        elif isinstance(el, Hatch):
            pts_str = " ".join([f"{tx(pt[0]):.2f},{ty(pt[1]):.2f}" for pt in el.boundary_points])
            # Solid fill with transparency
            svg_elem = f'<polygon points="{pts_str}" fill="{el.fill_color}" fill-opacity="0.2" stroke="none" />'
            
        elif isinstance(el, Dimension):
            # Decompose Dimension primitive into lines and ticks
            # Main line
            svg_elem = f'<g class="dimension">'
            
            # Determine orientation: horizontal or vertical
            is_horiz = abs(el.y1 - el.y2) < 0.1
            
            if is_horiz:
                # Horizontal dimension line
                svg_elem += f'<line x1="{tx(el.x1):.2f}" y1="{ty(el.dim_y):.2f}" x2="{tx(el.x2):.2f}" y2="{ty(el.dim_y):.2f}" stroke="{stroke_color}" stroke-width="1.0" />'
                # Extensions
                svg_elem += f'<line x1="{tx(el.x1):.2f}" y1="{ty(el.y1):.2f}" x2="{tx(el.x1):.2f}" y2="{ty(el.dim_y):.2f}" stroke="{stroke_color}" stroke-width="0.8" stroke-dasharray="2,2" />'
                svg_elem += f'<line x1="{tx(el.x2):.2f}" y1="{ty(el.y2):.2f}" x2="{tx(el.x2):.2f}" y2="{ty(el.dim_y):.2f}" stroke="{stroke_color}" stroke-width="0.8" stroke-dasharray="2,2" />'
                
                # 45 degree architectural tick marks at bounds
                tick = 0.3 * scale
                svg_elem += f'<line x1="{tx(el.x1)-tick:.2f}" y1="{ty(el.dim_y)+tick:.2f}" x2="{tx(el.x1)+tick:.2f}" y2="{ty(el.dim_y)-tick:.2f}" stroke="{stroke_color}" stroke-width="1.5" />'
                svg_elem += f'<line x1="{tx(el.x2)-tick:.2f}" y1="{ty(el.dim_y)+tick:.2f}" x2="{tx(el.x2)+tick:.2f}" y2="{ty(el.dim_y)-tick:.2f}" stroke="{stroke_color}" stroke-width="1.5" />'
                
                # Centered Text (above the dimension line)
                tx_x = tx((el.x1 + el.x2) / 2.0)
                tx_y = ty(el.dim_y) - 8.0  # slightly above
                svg_elem += f'<text x="{tx_x:.2f}" y="{tx_y:.2f}" font-family="Outfit, Inter, sans-serif" font-size="9px" fill="{stroke_color}" text-anchor="middle" dominant-baseline="baseline">{el.text}</text>'
            else:
                # Vertical dimension line
                svg_elem += f'<line x1="{tx(el.dim_x):.2f}" y1="{ty(el.y1):.2f}" x2="{tx(el.dim_x):.2f}" y2="{ty(el.y2):.2f}" stroke="{stroke_color}" stroke-width="1.0" />'
                # Extensions
                svg_elem += f'<line x1="{tx(el.x1):.2f}" y1="{ty(el.y1):.2f}" x2="{tx(el.dim_x):.2f}" y2="{ty(el.y1):.2f}" stroke="{stroke_color}" stroke-width="0.8" stroke-dasharray="2,2" />'
                svg_elem += f'<line x1="{tx(el.x2):.2f}" y1="{ty(el.y2):.2f}" x2="{tx(el.dim_x):.2f}" y2="{ty(el.y2):.2f}" stroke="{stroke_color}" stroke-width="0.8" stroke-dasharray="2,2" />'
                
                # Ticks
                tick = 0.3 * scale
                svg_elem += f'<line x1="{tx(el.dim_x)-tick:.2f}" y1="{ty(el.y1)+tick:.2f}" x2="{tx(el.dim_x)+tick:.2f}" y2="{ty(el.y1)-tick:.2f}" stroke="{stroke_color}" stroke-width="1.5" />'
                svg_elem += f'<line x1="{tx(el.dim_x)-tick:.2f}" y1="{ty(el.y2)+tick:.2f}" x2="{tx(el.dim_x)+tick:.2f}" y2="{ty(el.y2)-tick:.2f}" stroke="{stroke_color}" stroke-width="1.5" />'
                
                # Centered Text rotated 90 degrees (left side of the dimension line)
                tx_x = tx(el.dim_x) - 8.0
                tx_y = ty((el.y1 + el.y2) / 2.0)
                svg_elem += f'<text x="{tx_x:.2f}" y="{tx_y:.2f}" font-family="Outfit, Inter, sans-serif" font-size="9px" fill="{stroke_color}" text-anchor="middle" dominant-baseline="middle" transform="rotate(-90, {tx_x:.2f}, {tx_y:.2f})">{el.text}</text>'
                
            svg_elem += f'</g>'
            
        if svg_elem:
            layer_groups[layer].append(svg_elem)
            
    # 2. Construct final SVG String
    # Include Google Font imports for clean typography
    svg_header = (
        f'<svg width="100%" height="100%" viewBox="0 0 {view_w:.2f} {view_h:.2f}" '
        f'style="background-color: #0b0f19;" xmlns="http://www.w3.org/2000/svg">\n'
        f'<defs>\n'
        f'  <style>\n'
        f'    @import url("https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&amp;display=swap");\n'
        f'    text {{ font-family: "Outfit", sans-serif; }}\n'
        f'  </style>\n'
        f'</defs>\n'
    )

    
    svg_body = ""
    # Render layers in structured drafting order (background first, details/annotations on top)
    render_order = ["Grid", "Utilities", "Structural", "Walls", "Windows", "Doors", "Furniture", "Dimensions", "Annotations", "default"]
    
    for layer in render_order:
        elements = layer_groups.get(layer, [])
        if elements:
            svg_body += f'  <g id="layer_{layer.lower()}" name="{layer}">\n'
            for elem in elements:
                svg_body += f'    {elem}\n'
            svg_body += f'  </g>\n'
            
    svg_footer = '</svg>'
    
    return svg_header + svg_body + svg_footer
