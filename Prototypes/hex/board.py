"""Hex board state — which tiles exist, who's on them.

Rectangular layout: width columns, height rows in axial coords with
offset skew (r ranges 0..height-1, q ranges are shifted per row so the
board renders as a parallelogram-ish rectangle).
"""

from hex import hexes_within, neighbors


class Board:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        # Axial rectangle: for each row r in [0, height), columns q in
        # [-r//2, width - r//2). This keeps the board roughly rectangular
        # when rendered pointy-top.
        self.tiles = set()
        for r in range(height):
            q_offset = -(r // 2)
            for q in range(q_offset, width + q_offset):
                self.tiles.add((q, r))
        self._unit_at = {}   # hex -> Unit
        # Traps placed on tiles. hex -> {"owner_team": int, "damage": int,
        # "ability": str}. Triggered when an enemy of owner_team steps onto
        # the tile (see ability_hex.move_unit). Consumed on trigger.
        self.traps = {}

    def in_bounds(self, h):
        return h in self.tiles

    def unit_at(self, h):
        return self._unit_at.get(h)

    def occupied(self):
        """Set of hexes currently holding a unit."""
        return set(self._unit_at.keys())

    def place(self, unit, h):
        if not self.in_bounds(h):
            raise ValueError(f"tile {h} out of bounds")
        if h in self._unit_at:
            raise ValueError(f"tile {h} already occupied")
        self._unit_at[h] = unit
        unit.hex = h

    def remove(self, unit):
        h = getattr(unit, "hex", None)
        if h is not None and self._unit_at.get(h) is unit:
            del self._unit_at[h]
        unit.hex = None

    def move(self, unit, dest):
        """Teleport a unit to `dest`. Callers use a_star for the actual path."""
        if not self.in_bounds(dest):
            raise ValueError(f"tile {dest} out of bounds")
        if dest in self._unit_at and self._unit_at[dest] is not unit:
            raise ValueError(f"tile {dest} already occupied")
        src = getattr(unit, "hex", None)
        if src is not None and self._unit_at.get(src) is unit:
            del self._unit_at[src]
        self._unit_at[dest] = unit
        unit.hex = dest

    def place_trap(self, h, owner_team, damage, ability="Trap"):
        self.traps[h] = {"owner_team": owner_team, "damage": damage, "ability": ability}

    def pop_trap(self, h):
        return self.traps.pop(h, None)

    def blocked_for(self, unit):
        """Tiles this unit can't path into (all occupied by anyone else)."""
        return {h for h, u in self._unit_at.items() if u is not unit}


if __name__ == "__main__":
    b = Board(5, 5)
    assert len(b.tiles) == 25
    class _U:
        hex = None
    u = _U()
    b.place(u, (0, 0))
    assert b.unit_at((0, 0)) is u
    b.move(u, (1, 0))
    assert b.unit_at((0, 0)) is None
    assert b.unit_at((1, 0)) is u
    b.remove(u)
    assert not b.occupied()
    print("board.py self-check OK")
