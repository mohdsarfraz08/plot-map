"""
Post-MILP A* Negative Space Corridor Router (Stage 3B.4D / Phase 2).

Converts continuous layout bounding boxes to a discrete 2D grid matrix, scans room
perimeters for valid negative-space doorway thresholds, executes multi-target A*
pathfinding, buffers the 1D circulation graph into legal 2D corridor polygons (3.5 ft width),
and injects them into the Topological Building Model (TBM).

STRICT BOUNDARY RULES:
- Continuous -> Discrete -> Continuous transformations only.
- Doorway anchors MUST be dynamically discovered via perimeter negative-space scan (No blind midpoints).
- Corridors are clipped to the legal envelope and must not overlap room interiors.
- Purely deterministic and data-driven.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any, List, Optional, Set, Tuple

from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    box,
)
from shapely.ops import unary_union


@dataclass
class GridCell:
    row: int
    col: int
    x: float
    y: float
    walkable: bool = True


@dataclass
class DoorwayThreshold:
    room_id: str
    grid_row: int
    grid_col: int
    world_x: float
    world_y: float
    clearance: float = 1.0


class DiscreteGridMatrix:
    """
    2D Grid Discretizer & Obstacle Masker for negative space routing.
    """

    def __init__(
        self,
        plot_width: float,
        plot_depth: float,
        setbacks: dict[str, float],
        resolution: float = 0.5,
    ) -> None:
        self.plot_width = plot_width
        self.plot_depth = plot_depth
        self.resolution = resolution
        self.setbacks = setbacks or {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}

        self.min_x = self.setbacks.get("left", 0.0)
        self.max_x = self.plot_width - self.setbacks.get("right", 0.0)
        self.min_y = self.setbacks.get("bottom", 0.0)
        self.max_y = self.plot_depth - self.setbacks.get("top", 0.0)

        self.cols = max(1, math.ceil(self.plot_width / self.resolution))
        self.rows = max(1, math.ceil(self.plot_depth / self.resolution))

        # 0 = UNWALKABLE, 1 = WALKABLE
        # Initialize everything outside the legal envelope as UNWALKABLE (0)
        self.grid: list[list[int]] = [[0 for _ in range(self.cols)] for _ in range(self.rows)]
        self._init_legal_envelope()

    def _init_legal_envelope(self) -> None:
        """Mark cells inside legal envelope as WALKABLE (1)."""
        for r in range(self.rows):
            for c in range(self.cols):
                x, y = self.grid_to_world(r, c)
                if self.min_x <= x <= self.max_x and self.min_y <= y <= self.max_y:
                    self.grid[r][c] = 1
                else:
                    self.grid[r][c] = 0

    def world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        c = math.floor(x / self.resolution)
        r = math.floor(y / self.resolution)
        c = max(0, min(self.cols - 1, c))
        r = max(0, min(self.rows - 1, r))
        return r, c

    def grid_to_world(self, r: int, c: int) -> tuple[float, float]:
        x = (c + 0.5) * self.resolution
        y = (r + 0.5) * self.resolution
        return x, y

    def mask_room_obstacle(
        self,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> None:
        """
        Mask a room bounding box as UNWALKABLE (0) in grid space.
        """
        r_start, c_start = self.world_to_grid(min_x, min_y)
        r_end, c_end = self.world_to_grid(max_x, max_y)

        for r in range(r_start, r_end + 1):
            for c in range(c_start, c_end + 1):
                if 0 <= r < self.rows and 0 <= c < self.cols:
                    x, y = self.grid_to_world(r, c)
                    # Strict interior check
                    if min_x <= x <= max_x and min_y <= y <= max_y:
                        self.grid[r][c] = 0

    def is_walkable(self, r: int, c: int) -> bool:
        if 0 <= r < self.rows and 0 <= c < self.cols:
            return self.grid[r][c] == 1
        return False

    def get_neighbors(self, r: int, c: int) -> list[tuple[int, int, float]]:
        """
        Returns walkable 4-connected and 8-connected neighbors with step cost.
        """
        neighbors = []
        # Cardinal directions (cost = 1.0)
        cardinals = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0)]
        for dr, dc, cost in cardinals:
            nr, nc = r + dr, c + dc
            if self.is_walkable(nr, nc):
                neighbors.append((nr, nc, cost))

        # Diagonals (cost = sqrt(2) ~ 1.414)
        diagonals = [(-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]
        for dr, dc, cost in diagonals:
            nr, nc = r + dr, c + dc
            if self.is_walkable(nr, nc):
                # Ensure corner cutting check: both adjacent cardinal cells must be walkable
                if self.is_walkable(r + dr, c) and self.is_walkable(r, c + dc):
                    neighbors.append((nr, nc, cost))

        return neighbors


class DoorwayAnchorExtractor:
    """
    Perimeter Negative-Space Doorway Threshold Scanner.
    Scans entire room perimeter in grid space to identify cells sharing an edge with WALKABLE space.
    """

    @classmethod
    def extract_thresholds(
        cls,
        grid_matrix: DiscreteGridMatrix,
        room_bounds: dict[str, tuple[float, float, float, float]],
        origin_xy: tuple[float, float] = (0.0, 0.0),
    ) -> dict[str, DoorwayThreshold]:
        """
        Extract valid doorway thresholds for every room by scanning its perimeter against WALKABLE cells.
        """
        thresholds: dict[str, DoorwayThreshold] = {}

        for room_id, (min_x, min_y, max_x, max_y) in room_bounds.items():
            valid_candidates: list[tuple[int, int, float, float, float]] = []

            # Step along perimeter in grid space
            r_min, c_min = grid_matrix.world_to_grid(min_x, min_y)
            r_max, c_max = grid_matrix.world_to_grid(max_x, max_y)

            perimeter_cells = set()
            # Top & Bottom edges
            for c in range(c_min, c_max + 1):
                perimeter_cells.add((r_min, c))
                perimeter_cells.add((r_max, c))
            # Left & Right edges
            for r in range(r_min, r_max + 1):
                perimeter_cells.add((r, c_min))
                perimeter_cells.add((r, c_max))

            # Check neighbors of each perimeter cell for adjacent walkable negative space
            cardinal_offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]

            for r_p, c_p in perimeter_cells:
                for dr, dc in cardinal_offsets:
                    nr, nc = r_p + dr, c_p + dc
                    if grid_matrix.is_walkable(nr, nc):
                        wx, wy = grid_matrix.grid_to_world(nr, nc)
                        # Distance to global origin as tie-breaker/heuristic
                        dist_to_orig = math.hypot(wx - origin_xy[0], wy - origin_xy[1])
                        # Count local walkable clearance
                        clearance = sum(
                            1 for cdr, cdc in cardinal_offsets if grid_matrix.is_walkable(nr + cdr, nc + cdc)
                        )
                        valid_candidates.append((nr, nc, wx, wy, dist_to_orig - clearance * 0.5))

            if valid_candidates:
                # Pick candidate with best clearance / proximity to origin
                valid_candidates.sort(key=lambda item: item[4])
                best_r, best_c, best_x, best_y, _ = valid_candidates[0]
                thresholds[room_id] = DoorwayThreshold(
                    room_id=room_id,
                    grid_row=best_r,
                    grid_col=best_c,
                    world_x=best_x,
                    world_y=best_y,
                )

        return thresholds


class AStarCorridorPathfinder:
    """
    A* Graph Pathfinder connecting Circulation Origin to Room Doorway Thresholds.
    """

    @classmethod
    def find_path(
        cls,
        grid_matrix: DiscreteGridMatrix,
        start_rc: tuple[int, int],
        goal_rc: tuple[int, int],
    ) -> list[tuple[int, int]]:
        """
        Standard A* pathfinding on discrete grid between start and goal.
        """
        if not grid_matrix.is_walkable(start_rc[0], start_rc[1]) or not grid_matrix.is_walkable(
            goal_rc[0], goal_rc[1]
        ):
            return []

        open_set: list[tuple[float, float, int, int]] = []
        # (f_score, g_score, r, c)
        heapq.heappush(open_set, (0.0, 0.0, start_rc[0], start_rc[1]))

        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        g_scores: dict[tuple[int, int], float] = {start_rc: 0.0}

        def heuristic(r1: int, c1: int, r2: int, c2: int) -> float:
            # Octile distance heuristic
            dr = abs(r1 - r2)
            dc = abs(c1 - c2)
            return (dr + dc) + (1.414 - 2) * min(dr, dc)

        while open_set:
            _, current_g, cr, cc = heapq.heappop(open_set)

            if (cr, cc) == goal_rc:
                # Reconstruct path
                path = [(cr, cc)]
                curr = (cr, cc)
                while curr in came_from:
                    curr = came_from[curr]
                    path.append(curr)
                path.reverse()
                return path

            for nr, nc, step_cost in grid_matrix.get_neighbors(cr, cc):
                tentative_g = current_g + step_cost
                if (nr, nc) not in g_scores or tentative_g < g_scores[(nr, nc)]:
                    g_scores[(nr, nc)] = tentative_g
                    f = tentative_g + heuristic(nr, nc, goal_rc[0], goal_rc[1])
                    came_from[(nr, nc)] = (cr, cc)
                    heapq.heappush(open_set, (f, tentative_g, nr, nc))

        return []

    @classmethod
    def route_circulation_tree(
        cls,
        grid_matrix: DiscreteGridMatrix,
        origin_xy: tuple[float, float],
        targets: dict[str, DoorwayThreshold],
    ) -> list[list[tuple[float, float]]]:
        """
        Routes all doorway thresholds back to the circulation origin, creating
        a continuous circulation polyline network.
        """
        origin_rc = grid_matrix.world_to_grid(origin_xy[0], origin_xy[1])
        
        # If origin cell is not directly walkable (e.g. on boundary), snap to nearest walkable neighbor
        if not grid_matrix.is_walkable(origin_rc[0], origin_rc[1]):
            for r in range(grid_matrix.rows):
                for c in range(grid_matrix.cols):
                    if grid_matrix.is_walkable(r, c):
                        origin_rc = (r, c)
                        break
                if grid_matrix.is_walkable(origin_rc[0], origin_rc[1]):
                    break

        paths_world: list[list[tuple[float, float]]] = []

        for room_id, target in targets.items():
            target_rc = (target.grid_row, target.grid_col)
            path_grid = cls.find_path(grid_matrix, origin_rc, target_rc)
            if path_grid:
                path_xy = [grid_matrix.grid_to_world(r, c) for r, c in path_grid]
                paths_world.append(path_xy)

        return paths_world


def extract_valid_corridor_polygons(
    geom: Any,
    min_area: float = 0.1,
) -> list[Polygon]:
    """
    Recursively and robustly extracts 2D Polygon components from any Shapely geometry
    (Polygon, MultiPolygon, GeometryCollection), discarding non-area geometries
    (Point, MultiPoint, LineString, MultiLineString) and polygon components with area < min_area.
    """
    if geom is None or geom.is_empty:
        return []

    valid_polys: list[Polygon] = []

    if isinstance(geom, Polygon):
        if geom.area >= min_area:
            valid_polys.append(geom)
    elif isinstance(geom, MultiPolygon):
        for poly in geom.geoms:
            if isinstance(poly, Polygon) and not poly.is_empty and poly.area >= min_area:
                valid_polys.append(poly)
    elif isinstance(geom, GeometryCollection):
        for sub_geom in geom.geoms:
            valid_polys.extend(extract_valid_corridor_polygons(sub_geom, min_area=min_area))

    return valid_polys


class CorridorPolygonGenerator:
    """
    Converts 1D circulation polylines to 2D continuous corridor polygons (buffered to 3.5 ft width)
    and clips them to the legal envelope while avoiding room collisions and sanitizing GEOS slivers.
    """

    MIN_AREA_THRESHOLD: float = 0.1  # Minimum functional corridor area in sq ft (14.4 sq inches)

    @classmethod
    def generate_corridor_polygons(
        cls,
        paths: list[list[tuple[float, float]]],
        corridor_width: float = 3.5,
        legal_envelope: Polygon | None = None,
        room_polygons: list[Polygon] | None = None,
    ) -> Polygon | MultiPolygon | None:
        """
        Buffer 1D polyline paths into 2D polygon with flat/mitre caps, subtract room obstacles,
        and sanitize GEOS/Shapely slivers and non-polygonal remnants.
        """
        if not paths:
            return None

        lines = []
        for path in paths:
            if len(path) >= 2:
                lines.append(LineString(path))

        if not lines:
            return None

        multi_line = MultiLineString(lines) if len(lines) > 1 else lines[0]
        half_width = corridor_width / 2.0

        # Buffer path network
        buffered = multi_line.buffer(half_width, cap_style="flat", join_style="mitre")

        if legal_envelope and not legal_envelope.is_empty:
            buffered = buffered.intersection(legal_envelope)

        if room_polygons:
            rooms_union = unary_union(room_polygons)
            buffered = buffered.difference(rooms_union)

        # 1. Empty geometry check
        if buffered.is_empty:
            return None

        # 2-5. Extract valid 2D polygon components (discarding 0D/1D geometries and components < min_area)
        valid_polys = extract_valid_corridor_polygons(buffered, min_area=cls.MIN_AREA_THRESHOLD)
        if not valid_polys:
            return None

        # 6. Recombine retained polygon components
        if len(valid_polys) == 1:
            sanitized = valid_polys[0]
        else:
            sanitized = unary_union(valid_polys)

        # 7-8. Final sanity checks: non-empty, area >= min_area, and strictly Polygon or MultiPolygon
        if sanitized.is_empty or sanitized.area < cls.MIN_AREA_THRESHOLD:
            return None

        if not isinstance(sanitized, (Polygon, MultiPolygon)):
            return None

        return sanitized
