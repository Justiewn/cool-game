"""Positional AI over FRAY's threat scoring.

For each AI-controlled unit we do a bounded 1-ply search:

    for dest in reachable_tiles(unit):
        for ability in affordable_moves(unit):
            for target_tile in valid_tiles(unit@dest, ability):
                score = evaluate(unit, ability, target_tile, aoe_units)
        # also score "do nothing but reposition"

Returns the best (dest_or_None, ability_name_or_None, target_tile_or_None).
The turn runner then does perform_move(dest) → perform_ability(ability, tile)
in that order, skipping either if None.

Reuses FRAY's ai._threat_score / kill-shot detection where possible.
"""

import _bootstrap  # noqa: F401

import math
from Units import Unit
from Abilities import Ability
import hex as H
import ai as fray_ai

from ability_hex import (
    get_valid_target_tiles, aoe_affected_units, get_config, MOVE,
)


DO_NOTHING = (None, None, None)


def _affordable_moves(unit):
    moves = []
    for m in unit.movesList:
        if m == "Rest":
            continue  # engage first; Rest handled by fallback
        cost = Ability.get_attr(m, "MP_COST") or 0
        if cost <= unit.mp:
            moves.append(m)
    return moves


def _closest_enemy_dist(unit, board):
    enemies = [u for u in Unit.get_units("alive", 1 - unit.team)
               if u.hex is not None]
    if not enemies:
        return 0
    return min(H.distance(unit.hex, e.hex) for e in enemies)


def _score(caster, ability_name, target_tile, board):
    """Score a candidate (ability, target_tile). Positive = good for caster."""
    hit = aoe_affected_units(target_tile, ability_name, caster, board)
    if not hit:
        return -1e6
    attrs = Ability.AbilitiesDict.get(ability_name, {})
    dmg_type = attrs.get("DMG_TYPE")
    is_heal = attrs.get("IS_HEAL")
    is_effect = attrs.get("IS_EFFECT")
    score = 0.0
    for t in hit:
        friend = (t.team == caster.team)
        if dmg_type in ("NORMAL", "MAGIC"):
            # Estimated max damage: caster ATK/MAGIC + DMG_BASE + DMG_ROLL, pre-DEF
            base = attrs.get("DMG_BASE", 0) + attrs.get("DMG_ROLL", 0)
            stat = caster.ATK if dmg_type == "NORMAL" else caster.MAGIC
            defence = t.DEF if dmg_type == "NORMAL" else t.MAGIC_DEF
            est = max(1, stat + base - defence)
            # Killshot bonus (guaranteed swing at their HP).
            if est >= t.hp:
                score += 500 + fray_ai._threat_score(t)
            else:
                score += est * 2
        if is_heal:
            gain = min(t.max_hp - t.hp, attrs.get("HP_GAIN", 0))
            score += gain * 3 if not friend else gain * 4
        if is_effect and attrs.get("EFFECT_STATUS"):
            status = attrs["EFFECT_STATUS"]
            already = t.effect_stacks_dict.get(status, 0)
            cap = attrs.get("EFFECT_STACKS", 1) or 1
            room = max(0, cap - already)
            # Debuffs on enemies = good; buffs on allies = good.
            weight = 20 if (friend != attrs.get("TARGET_ENEMY", False)) else -20
            score += weight * (1 if room > 0 else 0.2)
    # Priestess targeting bonus
    if any(getattr(type(t), "className", "") == "Priestess" and t.team != caster.team
           for t in hit):
        score += 30
    # Hunter: bias hard toward the weakest enemy on the board — finish
    # them off before pivoting to a fresh target.
    caster_class = getattr(type(caster), "className", "")
    if caster_class == "Hunter":
        weakest = _weakest_enemy(caster)
        if weakest is not None and weakest in hit:
            # Big bonus scaling with how much lower their HP is than the
            # median enemy — always positive.
            score += 40 + max(0, 60 - weakest.hp)
    return score


_MELEE_CLASSES = {"Knight", "Berserker", "Thug", "Thief", "Assassin"}


def _weakest_enemy(caster):
    """Weakest = lowest current HP; tie-break by lowest DEF, then MAGIC_DEF."""
    enemies = [u for u in Unit.get_units("alive", 1 - caster.team) if u.hex is not None]
    if not enemies:
        return None
    return min(enemies,
               key=lambda e: (e.hp, e.DEF, e.MAGIC_DEF))


def _positional_bonus(caster, dest, board):
    """Small bonus for being near enemies (encourages engagement) unless the
    unit is a Priestess/Hunter, which prefer to hang back."""
    className = getattr(type(caster), "className", "")
    enemies = [u for u in Unit.get_units("alive", 1 - caster.team) if u.hex is not None]
    if not enemies:
        return 0
    nearest = min(H.distance(dest, e.hex) for e in enemies)
    if className == "Priestess":
        # Prefer nearest ally at range 1-2, prefer being 3+ from enemies.
        allies = [u for u in Unit.get_units("alive", caster.team)
                  if u is not caster and u.hex is not None]
        ally_bonus = 0
        if allies:
            ally_nearest = min(H.distance(dest, a.hex) for a in allies)
            ally_bonus = max(0, 3 - ally_nearest) * 2
        return ally_bonus + max(0, nearest - 2) * 2 - max(0, 2 - nearest) * 5
    if className == "Hunter":
        return _hunter_positional_bonus(caster, dest)
    # Melee/attacker: reward closing in — unbounded so the AI keeps
    # marching toward the enemy team even from across a large board.
    # Small coefficient so it doesn't outweigh actual hit-scoring.
    return -nearest * 2


def _hunter_positional_bonus(caster, dest):
    """Hunter wants to:
       - stay far from melee enemies (heavy penalty when adjacent),
       - stand exactly at Arrow max range (5) from the weakest enemy so the
         Arrow distance bonus is maximised (+20% at dist 5, tapers below).
    """
    enemies = [u for u in Unit.get_units("alive", 1 - caster.team) if u.hex is not None]
    if not enemies:
        return 0
    melee_enemies = [e for e in enemies
                     if getattr(type(e).__bases__[0], "className", "") in _MELEE_CLASSES
                     or getattr(type(e), "className", "") in _MELEE_CLASSES]
    # Heavy penalty for standing next to any melee unit; smaller for being
    # within their charge/tackle reach.
    melee_penalty = 0
    for e in melee_enemies:
        d = H.distance(dest, e.hex)
        if d <= 1:
            melee_penalty -= 80    # adjacent = about to die
        elif d == 2:
            melee_penalty -= 40    # tackle range
        elif d == 3:
            melee_penalty -= 10
    # Arrow ideal distance to weakest enemy: sit at Arrow's max range for the
    # biggest distance bonus. Read the range from HEX_CONFIG so this tracks
    # any future retuning of Arrow.
    arrow_range = get_config("Arrow")[0]
    weakest = _weakest_enemy(caster)
    if weakest is not None:
        d = H.distance(dest, weakest.hex)
        if d > arrow_range:
            arrow_bonus = -(d - arrow_range) * 6   # out of Arrow range
        elif d < 2:
            arrow_bonus = -20                       # too close, prefer melee-safe distance
        else:
            # Peak at d = arrow_range, taper linearly down to d = 2.
            arrow_bonus = 10 + (d - 2) * 4
    else:
        arrow_bonus = 0
    return melee_penalty + arrow_bonus


def choose_turn(caster, board):
    """Returns (dest_or_None, ability_name_or_None, target_tile_or_None)."""
    if caster.hex is None:
        return DO_NOTHING
    blocked = board.blocked_for(caster)
    reach = H.bfs_reachable(caster.hex, caster.MOVE, blocked=blocked,
                            in_bounds=board.in_bounds)
    # Always allow "stay put".
    candidates = list(reach.keys())
    moves = _affordable_moves(caster)

    best = (-math.inf, DO_NOTHING)
    original_hex = caster.hex
    for dest in candidates:
        # Simulate being at `dest` for the targeting/AoE math. board.unit_at
        # is only consulted for `dest`'s aoe expansion which uses actual
        # positions of *other* units — safe as long as we restore.
        if dest != original_hex:
            board.move(caster, dest)
        try:
            positional = _positional_bonus(caster, dest, board)
            # Score doing nothing at this dest.
            best_at_dest = (positional, None, None)
            for m in moves:
                tiles = get_valid_target_tiles(caster, m, board)
                for t in tiles:
                    s = _score(caster, m, t, board) + positional
                    if s > best_at_dest[0]:
                        best_at_dest = (s, m, t)
            if best_at_dest[0] > best[0]:
                dest_choice = dest if dest != original_hex else None
                best = (best_at_dest[0], (dest_choice, best_at_dest[1], best_at_dest[2]))
        finally:
            if dest != original_hex:
                board.move(caster, original_hex)

    if best[1] == DO_NOTHING:
        # Fall back to Rest if we can and we're not full-MP.
        if "Rest" in caster.movesList and caster.mp < caster.max_mp:
            return (None, "Rest", caster.hex)
    return best[1]


if __name__ == "__main__":
    from board import Board
    from hex_unit import HexKnight, HexThug

    Unit.remove_all()
    b = Board(8, 8)
    k = HexKnight("Aldric", 0)
    t = HexThug("Brutus", 1)
    b.place(k, (0, 0))
    b.place(t, (5, 0))
    dest, move, tile = choose_turn(k, b)
    # Knight should want to close (move somewhere non-None) and probably
    # not be able to hit yet.
    assert dest is not None
    print(f"knight: move to {dest}, then {move} @ {tile}")
    # Bring them closer, re-evaluate — knight should now Sword slash the thug.
    b.move(k, (4, 0))
    dest2, move2, tile2 = choose_turn(k, b)
    assert move2 in ("Sword slash", "Tackle", "Sharpen sword", "Raise shield"), move2
    print(f"knight (adjacent-ish): move to {dest2}, then {move2} @ {tile2}")
    Unit.remove_all()
    print("ai_hex.py self-check OK")
