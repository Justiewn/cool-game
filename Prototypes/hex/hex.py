"""Axial hex coordinate math.

Reference: https://www.redblobgames.com/grids/hexagons/ — we use axial
coordinates (q, r) with pointy-top hex orientation. Cube coordinate
(x, y, z) is derived as (q, -q-r, r) when needed for distance.

Pure Python — no pygame, no game state. Fully unit-testable.
"""

import heapq
import math


# 6 axial neighbour offsets (pointy-top). Order: E, NE, NW, W, SW, SE.
AXIAL_DIRS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]


def neighbors(hex_):
    """Six axial neighbours of `hex_`."""
    q, r = hex_
    return [(q + dq, r + dr) for dq, dr in AXIAL_DIRS]


def distance(a, b):
    """Axial hex distance between two coords."""
    aq, ar = a
    bq, br = b
    return (abs(aq - bq) + abs(ar - br) + abs(aq + ar - bq - br)) // 2


def hexes_within(center, radius):
    """All hex coords within `radius` of `center` (inclusive), including centre."""
    cq, cr = center
    result = []
    for dq in range(-radius, radius + 1):
        r1 = max(-radius, -dq - radius)
        r2 = min(radius, -dq + radius)
        for dr in range(r1, r2 + 1):
            result.append((cq + dq, cr + dr))
    return result


def ring(center, radius):
    """Hexes at exactly `radius` from centre."""
    if radius <= 0:
        return [center]
    cq, cr = center
    q, r = cq + AXIAL_DIRS[4][0] * radius, cr + AXIAL_DIRS[4][1] * radius
    result = []
    for i in range(6):
        for _ in range(radius):
            result.append((q, r))
            dq, dr = AXIAL_DIRS[i]
            q, r = q + dq, r + dr
    return result


def _cube_lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t)


def _axial_to_cube(h):
    q, r = h
    return (q, -q - r, r)


def _cube_round(c):
    rx, ry, rz = round(c[0]), round(c[1]), round(c[2])
    dx, dy, dz = abs(rx - c[0]), abs(ry - c[1]), abs(rz - c[2])
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry
    return (rx, ry, rz)


def line(a, b):
    """Straight line of hexes from a to b (inclusive)."""
    n = distance(a, b)
    if n == 0:
        return [a]
    ca, cb = _axial_to_cube(a), _axial_to_cube(b)
    result = []
    for i in range(n + 1):
        t = i / n
        cx, cy, cz = _cube_round(_cube_lerp(ca, cb, t))
        result.append((cx, cz))
    return result


# ─────────────────────────────── pixel conversion ────────────────────────────

SQRT3 = math.sqrt(3)


def axial_to_pixel(hex_, size, origin=(0, 0)):
    """Pointy-top hex centre in pixels. `size` = distance from centre to corner."""
    q, r = hex_
    x = size * (SQRT3 * q + SQRT3 / 2 * r)
    y = size * (3 / 2 * r)
    return (x + origin[0], y + origin[1])


def pixel_to_axial(px, size, origin=(0, 0)):
    """Inverse of axial_to_pixel; returns rounded axial coord."""
    x = (px[0] - origin[0]) / size
    y = (px[1] - origin[1]) / size
    q = (SQRT3 / 3 * x - 1 / 3 * y)
    r = (2 / 3 * y)
    cx, cy, cz = _cube_round((q, -q - r, r))
    return (cx, cz)


def corners(center_pixel, size):
    """Six corner pixel coords of a pointy-top hex."""
    cx, cy = center_pixel
    result = []
    for i in range(6):
        angle = math.pi / 180 * (60 * i - 30)  # pointy-top: -30° offset
        result.append((cx + size * math.cos(angle), cy + size * math.sin(angle)))
    return result


# ─────────────────────────────── pathfinding ──────────────────────────────────

def bfs_reachable(start, max_cost, blocked=None, in_bounds=None):
    """Returns {hex: cost} for every tile reachable from start in ≤ max_cost
    steps. Each step costs 1. `blocked` (set of coords) can't be entered but
    doesn't block adjacency. `in_bounds(h)->bool` restricts the frontier."""
    blocked = blocked or set()
    seen = {start: 0}
    frontier = [start]
    while frontier:
        nxt = []
        for h in frontier:
            cost = seen[h]
            if cost >= max_cost:
                continue
            for n in neighbors(h):
                if n in seen or n in blocked:
                    continue
                if in_bounds is not None and not in_bounds(n):
                    continue
                seen[n] = cost + 1
                nxt.append(n)
        frontier = nxt
    return seen


def a_star(start, goal, blocked=None, in_bounds=None):
    """Shortest path (list of hexes, inclusive of start and goal) or None."""
    if start == goal:
        return [start]
    blocked = blocked or set()
    open_set = [(distance(start, goal), 0, start)]
    came_from = {start: None}
    g = {start: 0}
    while open_set:
        _, cost, current = heapq.heappop(open_set)
        if current == goal:
            path = [current]
            while came_from[path[-1]] is not None:
                path.append(came_from[path[-1]])
            path.reverse()
            return path
        for n in neighbors(current):
            if n in blocked and n != goal:
                continue
            if in_bounds is not None and not in_bounds(n):
                continue
            new_g = cost + 1
            if n not in g or new_g < g[n]:
                g[n] = new_g
                came_from[n] = current
                heapq.heappush(open_set, (new_g + distance(n, goal), new_g, n))
    return None


if __name__ == "__main__":
    # Self-check
    origin = (0, 0)
    assert all(distance(origin, n) == 1 for n in neighbors(origin))
    assert len(hexes_within(origin, 0)) == 1
    assert len(hexes_within(origin, 1)) == 7
    assert len(hexes_within(origin, 2)) == 19
    assert len(hexes_within(origin, 3)) == 37
    assert len(ring(origin, 0)) == 1
    assert len(ring(origin, 1)) == 6
    assert len(ring(origin, 3)) == 18
    # Line: consecutive hexes are adjacent.
    ln = line((0, 0), (3, -1))
    assert ln[0] == (0, 0) and ln[-1] == (3, -1)
    for a, b in zip(ln, ln[1:]):
        assert distance(a, b) == 1
    # BFS reachable in 3 steps from centre = hexes_within(3).
    reach = bfs_reachable(origin, 3)
    assert set(reach) == set(hexes_within(origin, 3))
    # A* path length matches hex distance.
    path = a_star((0, 0), (4, -2))
    assert path is not None and len(path) - 1 == distance((0, 0), (4, -2))
    # Pixel roundtrip.
    for h in hexes_within(origin, 3):
        px = axial_to_pixel(h, 40)
        assert pixel_to_axial(px, 40) == h
    print("hex.py self-check OK")
