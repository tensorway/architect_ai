from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, List, Mapping, Sequence

from agent.workflow_steps.planner_types import PlannerDraftOutput
from agent.workflow_steps.workflow import WorkflowStep

Point = tuple[float, float]
Segment = tuple[Point, Point]


@dataclass
class RoomSegmentationInput:
    walls: Sequence[Mapping[str, Any]]
    snap_eps: float = 1e-3
    min_area: float = 1.0


class RoomSegmentationStep(
    WorkflowStep[RoomSegmentationInput, List[PlannerDraftOutput]]
):
    """Deterministically derives room polygons (bounded faces) from wall segments."""

    def _run(self, input: RoomSegmentationInput) -> List[PlannerDraftOutput]:
        segments = _extract_segments(input.walls, input.snap_eps)
        vertices, edges = _build_planar_graph(segments, input.snap_eps)
        rooms = _walk_faces(vertices, edges, input.min_area)

        outputs: list[PlannerDraftOutput] = []
        for idx, points in enumerate(rooms):
            room_payload = {
                "id": f"r{idx + 1}",
                "vertices": [{"x": x, "y": y} for (x, y) in _dedupe_ring(points)],
                "area": abs(_polygon_area(points)),
            }
            plan = {"walls": list(input.walls), "rooms": [room_payload], "assets": []}
            outputs.append(PlannerDraftOutput(plan=plan, view=None, prompt="", notes=""))

        return outputs


def _extract_segments(walls: Sequence[Mapping[str, Any]], snap_eps: float) -> list[Segment]:
    segments: list[Segment] = []
    for wall in walls:
        a_raw = wall.get("a") if isinstance(wall, Mapping) else None
        b_raw = wall.get("b") if isinstance(wall, Mapping) else None
        if not (isinstance(a_raw, Mapping) and isinstance(b_raw, Mapping)):
            continue

        try:
            a = (float(a_raw.get("x")), float(a_raw.get("y")))
            b = (float(b_raw.get("x")), float(b_raw.get("y")))
        except (TypeError, ValueError):
            continue

        a = _snap_point(a, snap_eps)
        b = _snap_point(b, snap_eps)

        if _is_too_close(a, b, snap_eps):
            continue

        segments.append((a, b))

    return segments


def _build_planar_graph(
    segments: list[Segment], snap_eps: float
) -> tuple[list[Point], list[tuple[int, int]]]:
    # Collect split points for every segment (t parameter, point)
    split_points: list[list[tuple[float, Point]]] = [
        [(0.0, seg[0]), (1.0, seg[1])] for seg in segments
    ]

    for i, seg_a in enumerate(segments):
        for j in range(i + 1, len(segments)):
            seg_b = segments[j]
            intersection = _segment_intersection(seg_a, seg_b, snap_eps)
            if intersection is None:
                continue
            point, t_a, t_b = intersection
            split_points[i].append((t_a, point))
            split_points[j].append((t_b, point))

    vertex_lookup: dict[tuple[int, int], int] = {}
    vertices: list[Point] = []
    edges: list[tuple[int, int]] = []
    undirected_edge_set: set[tuple[int, int]] = set()

    for points in split_points:
        points.sort(key=lambda item: item[0])

        cleaned: list[tuple[float, Point]] = []
        for t, pt in points:
            if not cleaned or not _is_too_close(pt, cleaned[-1][1], snap_eps):
                cleaned.append((t, _snap_point(pt, snap_eps)))

        for (_, p_start), (_, p_end) in zip(cleaned, cleaned[1:]):
            if _is_too_close(p_start, p_end, snap_eps):
                continue
            start_idx = _get_or_add_vertex(p_start, snap_eps, vertex_lookup, vertices)
            end_idx = _get_or_add_vertex(p_end, snap_eps, vertex_lookup, vertices)
            if start_idx == end_idx:
                continue
            edge_key = (min(start_idx, end_idx), max(start_idx, end_idx))
            if edge_key in undirected_edge_set:
                continue
            undirected_edge_set.add(edge_key)
            edges.append((start_idx, end_idx))

    return vertices, edges


def _walk_faces(
    vertices: list[Point], edges: list[tuple[int, int]], min_area: float
) -> list[list[Point]]:
    adj = _build_sorted_adjacency(vertices, edges)
    visited: set[tuple[int, int]] = set()
    faces: list[list[int]] = []

    for u, neighbors in adj.items():
        for v in neighbors:
            if (u, v) in visited:
                continue
            cycle = _trace_face(u, v, adj, visited)
            if len(cycle) < 3:
                continue
            coords = [vertices[idx] for idx in cycle]
            area = abs(_polygon_area(coords))
            if area < min_area:
                continue
            faces.append(cycle)

    if not faces:
        return []

    areas = [abs(_polygon_area([vertices[idx] for idx in face])) for face in faces]
    outer_idx = areas.index(max(areas))

    room_faces = [face for idx, face in enumerate(faces) if idx != outer_idx]
    return [[vertices[idx] for idx in face] for face in room_faces]


def _trace_face(
    start_u: int, start_v: int, adj: dict[int, list[int]], visited: set[tuple[int, int]]
) -> list[int]:
    cycle: list[int] = []
    u, v = start_u, start_v

    while True:
        visited.add((u, v))
        cycle.append(u)

        neighbors = adj.get(v)
        if not neighbors:
            return []

        try:
            idx = neighbors.index(u)
        except ValueError:
            return []

        next_vertex = neighbors[(idx - 1) % len(neighbors)]  # clockwise after reverse
        next_edge = (v, next_vertex)

        if next_edge == (start_u, start_v):
            cycle.append(v)
            visited.add(next_edge)
            break

        if next_edge in visited:
            return []

        u, v = next_edge

        if len(cycle) > len(adj) * 4:
            # Safety net against infinite loops on malformed graphs
            return []

    return cycle


def _build_sorted_adjacency(
    vertices: list[Point], edges: list[tuple[int, int]]
) -> dict[int, list[int]]:
    adj: dict[int, list[int]] = {idx: [] for idx in range(len(vertices))}
    for a, b in edges:
        if b not in adj[a]:
            adj[a].append(b)
        if a not in adj[b]:
            adj[b].append(a)

    for vid, neighbors in adj.items():
        neighbors.sort(
            key=lambda n: math.atan2(
                vertices[n][1] - vertices[vid][1], vertices[n][0] - vertices[vid][0]
            )
        )

    return adj


def _segment_intersection(
    seg_a: Segment, seg_b: Segment, eps: float
) -> tuple[Point, float, float] | None:
    (x1, y1), (x2, y2) = seg_a
    (x3, y3), (x4, y4) = seg_b

    dx1, dy1 = x2 - x1, y2 - y1
    dx2, dy2 = x4 - x3, y4 - y3
    denom = dx1 * dy2 - dy1 * dx2

    if abs(denom) < eps:
        # Parallel or collinear: ignore unless endpoints touch
        for pt in (seg_b[0], seg_b[1]):
            if _point_on_segment(pt, seg_a, eps):
                t_a = _project_param(seg_a, pt)
                t_b = 0.0 if pt == seg_b[0] else 1.0
                return pt, t_a, t_b
        for pt in (seg_a[0], seg_a[1]):
            if _point_on_segment(pt, seg_b, eps):
                t_b = _project_param(seg_b, pt)
                t_a = 0.0 if pt == seg_a[0] else 1.0
                return pt, t_a, t_b
        return None

    t = ((x3 - x1) * dy2 - (y3 - y1) * dx2) / denom
    u = ((x3 - x1) * dy1 - (y3 - y1) * dx1) / denom

    if -eps <= t <= 1 + eps and -eps <= u <= 1 + eps:
        ix, iy = x1 + t * dx1, y1 + t * dy1
        t_clamped = min(max(t, 0.0), 1.0)
        u_clamped = min(max(u, 0.0), 1.0)
        return (ix, iy), t_clamped, u_clamped

    return None


def _point_on_segment(pt: Point, seg: Segment, eps: float) -> bool:
    (x1, y1), (x2, y2) = seg
    (px, py) = pt
    cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
    if abs(cross) > eps:
        return False
    dot = (px - x1) * (px - x2) + (py - y1) * (py - y2)
    return dot <= eps


def _project_param(seg: Segment, pt: Point) -> float:
    (x1, y1), (x2, y2) = seg
    dx, dy = x2 - x1, y2 - y1
    denom = dx * dx + dy * dy
    if denom == 0:
        return 0.0
    return ((pt[0] - x1) * dx + (pt[1] - y1) * dy) / denom


def _get_or_add_vertex(
    pt: Point,
    snap_eps: float,
    lookup: dict[tuple[int, int], int],
    vertices: list[Point],
) -> int:
    key = _quantized_key(pt, snap_eps)
    existing = lookup.get(key)
    if existing is not None:
        return existing
    idx = len(vertices)
    lookup[key] = idx
    vertices.append(pt)
    return idx


def _is_too_close(a: Point, b: Point, eps: float) -> bool:
    return _dist2(a, b) <= eps * eps


def _dist2(a: Point, b: Point) -> float:
    dx, dy = a[0] - b[0], a[1] - b[1]
    return dx * dx + dy * dy


def _snap_point(pt: Point, eps: float) -> Point:
    if eps <= 0:
        return pt
    return (round(pt[0] / eps) * eps, round(pt[1] / eps) * eps)


def _quantized_key(pt: Point, eps: float) -> tuple[int, int]:
    if eps <= 0:
        return int(pt[0] * 1e6), int(pt[1] * 1e6)
    return int(round(pt[0] / eps)), int(round(pt[1] / eps))


def _polygon_area(points: Sequence[Point]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _dedupe_ring(points: Sequence[Point]) -> list[Point]:
    if not points:
        return []
    cleaned: list[Point] = []
    for pt in points:
        if not cleaned or pt != cleaned[-1]:
            cleaned.append(pt)
    if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        cleaned.pop()
    return cleaned


__all__ = ["RoomSegmentationInput", "RoomSegmentationStep"]
