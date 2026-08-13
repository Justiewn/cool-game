"""Spatial targeting layer over FRAY's Ability.

FRAY abilities are unit-target: `get_valid_targets(caster)` returns "any
alive unit on the enemy team". We bolt on three notions:

  RANGE      : max hex distance from caster to primary target
  AOE_SHAPE  : "single" | "blast" (circle) | "line" | "cone" | "self"
  AOE_RADIUS : radius of the shape (0 = single tile)

Everything else — damage math, effects, ticks, MP, downed, special
methods — comes from Abilities.Ability unchanged. This module only
gates the candidate set and expands AoE into an affected-unit list.
"""

import _bootstrap  # noqa: F401

from Abilities import Ability
import hex as H


# ─────────────────────────── ability spatial config ──────────────────────────

# (range, aoe_shape, aoe_radius). Every FRAY ability + a new Move.
# Defaults tuned for a small board (radius ~3-6 from most units).
HEX_CONFIG = {
    # Basic attacks
    "Punch":         (1, "single", 0),
    "Sword slash":   (1, "single", 0),
    "Shiv":          (1, "single", 0),
    "Tackle":        (2, "single", 0),  # charge attack
    "Stab/Backstab": (1, "single", 0),
    "Finish":        (1, "single", 0),
    # Ranged / magic
    "Smite":         (3, "single", 0),
    "Bless":         (0, "self_burst", 2),
    "Heal":          (3, "single", 0),
    "Bandage":       (1, "single", 0),
    "Leech":         (2, "single", 0),
    "Mark":          (4, "single", 0),
    "Poison":        (3, "single", 0),
    "Disquiet":      (3, "single", 0),
    "Distract":      (3, "single", 0),
    # Team buffs. Riot restricted to teammates within 2; Rejuvenation stays whole-team.
    "Riot":          (0, "self_burst", 2),
    "Rejuvenation":  (0, "team", 0),
    "Frenzy":        (0, "self", 0),
    "Sharpen sword": (0, "self", 0),
    "Sneak":         (0, "self", 0),
    "Shroud":        (0, "self", 0),
    "Raise shield":  (0, "self", 0),
    "Uproar":        (0, "team", 0),
    "Rest":          (0, "self", 0),
    # AoE damage — Cleave sweeps in an arc: the target hex + the two hexes
    # adjacent to BOTH the caster and the target (the "sweep neighbours").
    "Cleave":        (1, "cleave_arc", 0),
    # Effects applied by other abilities (registered but not chosen)
    "Stun":          (0, "single", 0),
    "Taunt":         (0, "self_burst", 2),
    # Hunter kit
    "Arrow":         (4, "single", 0),
    "Lay Trap":      (3, "lay_trap", 0),
    "Focus":         (0, "self", 0),
    # Spellblade kit
    "Arcane Strike": (2, "single", 0),
    "Mana Sap":      (3, "single", 0),
    "Arcane Shield": (0, "self", 0),
}

# Damage dealt by a trap on trigger.
TRAP_DAMAGE = 12

# Move is a hex-only pseudo-ability. Not in FRAY's AbilitiesDict — targets
# a tile, not a unit. Resolution goes through `move_unit` below, not
# through Ability.initial_cast.
MOVE = "Move"


def get_config(ability_name):
    """(range, shape, radius) for `ability_name`. Defaults to (1, single, 0)."""
    return HEX_CONFIG.get(ability_name, (1, "single", 0))


# ────────────────────────────── candidate targets ────────────────────────────

def get_valid_target_units(caster, ability_name, board):
    """Units the caster can pick as the primary target — filtered by RANGE
    and by FRAY's own TARGET_TYPE/TARGET_ENEMY (self / ally / enemy)."""
    if ability_name == MOVE:
        return []  # Move targets tiles, not units
    attrs = Ability.AbilitiesDict.get(ability_name, {})
    target_type = attrs.get("TARGET_TYPE")
    target_enemy = attrs.get("TARGET_ENEMY")
    rng, _, _ = get_config(ability_name)
    if target_type == 0:
        return [caster]
    # Team pool
    from Units import Unit
    if target_enemy:
        pool = Unit.get_units("alive", 1 - caster.team)
    else:
        pool = Unit.get_units("alive", caster.team)
    if target_type == 3:
        # Team-wide — no per-unit range filter needed (rng defaults to 99).
        return list(pool)
    # target_type 1 (single) or the dead 2/4 branches — filter by range.
    if caster.hex is None:
        return list(pool)
    candidates = [u for u in pool
                  if u.hex is not None and H.distance(caster.hex, u.hex) <= rng]
    # Tackle at range 2 requires a free landing hex adjacent to the target
    # (the caster charges into that gap). Filter out targets where the gap
    # is off-board or occupied — the cast simply isn't legal there.
    if ability_name == "Tackle":
        candidates = [u for u in candidates
                      if _tackle_landing_hex(caster.hex, u.hex, board) is not None]
    return candidates


def cleave_arc_hexes(caster_hex, target_hex):
    """Cleave affects a 3-hex arc: the target hex plus its two neighbours
    that are also adjacent to the caster (the ones on either side of the
    target in the caster's ring of 6). If the target isn't adjacent to the
    caster (shouldn't happen — range gate is 1), just returns [target]."""
    if caster_hex is None or target_hex is None:
        return [target_hex] if target_hex is not None else []
    caster_neighbours = set(H.neighbors(caster_hex))
    if target_hex not in caster_neighbours:
        return [target_hex]
    flanks = [h for h in H.neighbors(target_hex) if h in caster_neighbours]
    return [target_hex] + flanks


def _tackle_landing_hex(caster_hex, target_hex, board):
    """Where the Tackle-caster ends up. Returns:
      - caster_hex itself if adjacent (no move needed);
      - the gap tile from H.line if at range 2 AND it's on-board AND unoccupied;
      - None otherwise (cast not legal).
    """
    d = H.distance(caster_hex, target_hex)
    if d == 1:
        return caster_hex
    if d == 2:
        los = H.line(caster_hex, target_hex)
        if len(los) >= 3:
            gap = los[1]
            if board.in_bounds(gap) and board.unit_at(gap) is None:
                return gap
    return None


def get_valid_target_tiles(caster, ability_name, board):
    """Tiles the caster can aim at. For unit-target abilities, returns the
    hexes of valid target units. For tile-target abilities (Move, cleave-arc,
    future ground-targeted AoE), returns the geometric tile set."""
    if ability_name == MOVE:
        blocked = board.blocked_for(caster)
        reach = H.bfs_reachable(caster.hex, caster.MOVE, blocked=blocked,
                                in_bounds=board.in_bounds)
        # Can't stay put and can't land on a friend/enemy tile (bfs already excludes).
        return [t for t in reach if t != caster.hex]
    # Cleave-arc aims at a *tile*, not a unit — the sweep can target an empty
    # adjacent hex and still connect via the flanking cells. Restrict to the
    # caster's six neighbours (in-bounds).
    rng, shape, _radius = get_config(ability_name)
    if shape == "cleave_arc" and caster.hex is not None:
        return [h for h in H.neighbors(caster.hex) if board.in_bounds(h)]
    if shape == "lay_trap" and caster.hex is not None:
        # Any in-range tile that's empty (no unit) and doesn't already hold
        # a trap. Includes the caster's own tile only if unoccupied — which
        # it never is, so effectively excluded.
        return [h for h in H.hexes_within(caster.hex, rng)
                if board.in_bounds(h)
                and board.unit_at(h) is None
                and h not in board.traps
                and h != caster.hex]
    return [u.hex for u in get_valid_target_units(caster, ability_name, board)
            if u.hex is not None]


def aoe_affected_units(target_tile, ability_name, caster, board):
    """Given a primary target tile, return the list of units that get hit
    by the ability's AoE. Respects TARGET_ENEMY (team filter)."""
    _, shape, radius = get_config(ability_name)
    attrs = Ability.AbilitiesDict.get(ability_name, {})
    target_enemy = attrs.get("TARGET_ENEMY")
    if shape == "self":
        return [caster]
    if shape == "team":
        # Whole allied team (or whole enemy team if TARGET_ENEMY is truthy).
        from Units import Unit
        team = 1 - caster.team if target_enemy else caster.team
        return [u for u in Unit.get_units("alive", team)]
    if shape == "self_burst":
        # Everyone of the appropriate team within `radius` of the caster,
        # including the caster themself when TARGET_ENEMY is falsy.
        if caster.hex is None:
            return []
        area = set(H.hexes_within(caster.hex, radius))
        target_team = 1 - caster.team if target_enemy else caster.team
        from Units import Unit
        return [u for u in Unit.get_units("alive", target_team)
                if u.hex is not None and u.hex in area]
    if shape == "single":
        u = board.unit_at(target_tile)
        return [u] if u is not None else []
    if shape == "blast":
        hexes = H.hexes_within(target_tile, radius)
        hit = [board.unit_at(h) for h in hexes]
    elif shape == "line":
        hexes = H.line(caster.hex, target_tile)
        hit = [board.unit_at(h) for h in hexes]
    elif shape == "cleave_arc":
        hexes = cleave_arc_hexes(caster.hex, target_tile)
        hit = [board.unit_at(h) for h in hexes]
    else:
        hit = []
    hit = [u for u in hit if u is not None and u.alive]
    if target_enemy is True:
        hit = [u for u in hit if u.team != caster.team]
    elif target_enemy is False:
        hit = [u for u in hit if u.team == caster.team]
    return hit


# ────────────────────────────── resolution ───────────────────────────────────

def _prime_focus_crit(caster):
    """If FOCUS is active on `caster`, prime the PRD counter so the next CRIT
    roll is guaranteed. FRAY's Sharpen-sword-style +CRIT bump also raises
    caster.CRIT to well over 100, which prd.roll clamps to p=1 anyway — this
    is belt-and-braces so the very first roll trips even before any ramp."""
    if caster is not None and "FOCUS" in caster.effect_stacks_dict:
        counters = getattr(caster, "_prd_counters", None)
        if counters is not None:
            counters["CRIT"] = 10_000  # arbitrarily large → n*C ≥ 1 always


def cast_ability(caster, ability_name, target_tile, board, battle):
    """Instantiate the FRAY Ability, expand AoE, hand off to initial_cast.
    Returns the same value initial_cast returns, or None if the target
    tile is out of range for this ability."""
    rng, shape, _ = get_config(ability_name)
    if shape != "self" and caster.hex is not None and target_tile is not None:
        if H.distance(caster.hex, target_tile) > rng:
            return None
    # Lay Trap is intercepted here: don't route it through FRAY's damage /
    # effect resolution. Build a throwaway ability just for MP + log side
    # effects, then drop the trap on the board.
    if ability_name == "Lay Trap":
        if target_tile is None or not board.in_bounds(target_tile):
            return None
        if board.unit_at(target_tile) is not None or target_tile in board.traps:
            return None
        ability = Ability(ability_name, Ability.ability_ID_counter)
        ability.initial_cast([caster], caster, battle)   # MP + "used" log
        board.place_trap(target_tile, caster.team, TRAP_DAMAGE, ability="Trap")
        return True
    _prime_focus_crit(caster)
    ability = Ability(ability_name, Ability.ability_ID_counter)
    targets = aoe_affected_units(target_tile, ability_name, caster, board)
    if not targets:
        return None
    # Arrow's flavour bonus: +10% base damage per hex of distance to the
    # target, capped at +30%. Implemented by temporarily bumping the
    # caster's _ATK before the cast and restoring it after — the standard
    # damage path picks it up naturally.
    atk_restore = None
    if ability_name == "Arrow" and caster.hex is not None and target_tile is not None:
        dist = H.distance(caster.hex, target_tile)
        bonus = min(0.3, (dist - 1) * 0.1)
        if bonus > 0:
            atk_restore = caster._ATK
            caster._ATK = int(round(caster._ATK * (1 + bonus)))
    try:
        return ability.initial_cast(targets, caster, battle)
    finally:
        if atk_restore is not None:
            caster._ATK = atk_restore


def _trigger_trap(unit, board, battle):
    """If `unit`'s current hex holds an enemy-team trap, apply damage and
    consume the trap. Returns True if it fired (movement should stop here)."""
    if unit is None or unit.hex is None:
        return False
    trap = board.traps.get(unit.hex)
    if trap is None or trap["owner_team"] == unit.team:
        return False
    board.pop_trap(unit.hex)
    dmg = trap["damage"]
    # Route through Ability.damage_target so splashes + hit sounds work.
    Ability.damage_target(dmg, unit, "NORMAL", False)
    print("{} triggers a trap! Took {} damage.".format(str(unit), dmg))
    return True


def move_unit(unit, dest, board):
    """Path from unit.hex to dest via A*. Walks the path hex-by-hex; if a
    hostile trap sits on any intermediate tile the movement stops there
    and the trap fires. Returns the actual path taken (may be shorter than
    the requested destination if a trap intercepted)."""
    blocked = board.blocked_for(unit)
    path = H.a_star(unit.hex, dest, blocked=blocked, in_bounds=board.in_bounds)
    if path is None:
        return None
    # Walk the path. If we hit an enemy trap before reaching dest, land on
    # that tile and stop. Skip the starting tile (path[0]).
    from Units import Unit as _U  # avoid top-level circularity
    for i in range(1, len(path)):
        step = path[i]
        board.move(unit, step)
        # Ability._combat_events / process_downed happen inside cast_ability's
        # caller — here we only apply the trap's raw HP delta so bar/splash
        # detection can pick it up.
        trap = board.traps.get(step)
        if trap is not None and trap["owner_team"] != unit.team:
            board.pop_trap(step)
            dmg = trap["damage"]
            Ability.damage_target(dmg, unit, "NORMAL", False)
            # Immobilise the trapped unit next team turn: HexBattle consumes
            # this flag in _reset_awaiting to pre-populate its move budget.
            unit._trap_immobilised = True
            print("{} triggers a trap! Took {} damage and is immobilised next turn.".format(
                str(unit), dmg))
            return path[: i + 1]
    return path


if __name__ == "__main__":
    # Basic sanity — needs board + units set up.
    from Units import Unit
    from board import Board
    from hex_unit import HexKnight, HexThug

    Unit.remove_all()
    b = Board(6, 6)
    k = HexKnight("Aldric", 0)
    t = HexThug("Brutus", 1)
    b.place(k, (0, 0))
    b.place(t, (2, 0))
    # Punch (range 1): thug not in range from origin
    assert (2, 0) not in get_valid_target_tiles(k, "Punch", b)
    # Sword slash (range 1): same
    assert (2, 0) not in get_valid_target_tiles(k, "Sword slash", b)
    # Tackle (range 2): thug is in range
    assert (2, 0) in get_valid_target_tiles(k, "Tackle", b)
    # Move: reachable tiles exclude occupied ones
    move_tiles = get_valid_target_tiles(k, MOVE, b)
    assert (2, 0) not in move_tiles  # thug is there
    assert (1, 0) in move_tiles      # 1-step neighbour is free
    Unit.remove_all()
    print("ability_hex.py self-check OK")
