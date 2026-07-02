"""Enemy AI strategy layer.

Public API:
    choose_action(battle, unit) -> (ability_name: str, targets: list[Unit])

Called by GUI.execute_enemy_ai when a unit is AI-controlled. Returns the ability
name and pre-selected target list ready for cast_selected_ability.

Design:
  - Per-class strategy functions in _STRATEGIES pick a move based on the class's
    kit and the current battle state (own HP/MP, active effects, allies/enemies).
  - Shared helpers below handle common concerns: legality checks, target scoring,
    kill-shot detection.
  - If a class strategy returns nothing usable, `_fallback` picks a random legal
    move — mirrors the old Unit.choose_ai_move behaviour.

Kept free of pygame imports so it can be exercised headlessly.
"""

import random

from Units import Unit
from Abilities import Ability


# ─────────────────────────────── helpers ────────────────────────────────

def _hp_ratio(u):
    return u.hp / u.max_hp if u.max_hp else 0.0

def _has_effect(unit, status):
    return status in unit.effect_stacks_dict

def _stacks(unit, status):
    return unit.effect_stacks_dict.get(status, 0)

def _mp_cost(name):
    return Ability.get_attr(name, "MP_COST") or 0

def _can_afford(caster, name):
    return caster.mp >= _mp_cost(name)

def _has_move(caster, name):
    return name in caster.movesList

def _valid_targets(caster, name):
    """Wrapper around Ability.get_valid_targets — instantiates a throwaway Ability."""
    return Ability(name, Ability.ability_ID_counter).get_valid_targets(caster)

def _enemies(caster):
    return list(Unit.get_units("alive", 1 - caster.team))

def _allies(caster):
    return list(Unit.get_units("alive", caster.team))


# ─────────────────────────────── scoring ────────────────────────────────

def _threat_score(u):
    """Rough offensive-danger heuristic; higher = kill/debuff sooner."""
    return u.ATK * 2 + u.MAGIC * 2 + u.CRIT

def _lowest_hp(units):
    return min(units, key=lambda u: u.hp) if units else None

def _highest_threat(units):
    return max(units, key=_threat_score) if units else None


def _damage_target(caster, name, enemies):
    """Preferred target for a damage move:
       1. an enemy the max roll can outright kill (lowest-HP first);
       2. otherwise the highest-threat enemy in range."""
    if not enemies:
        return None
    base = Ability.get_attr(name, "DMG_BASE") or 0
    roll = Ability.get_attr(name, "DMG_ROLL") or 0
    dmg_type = Ability.get_attr(name, "DMG_TYPE")
    for e in sorted(enemies, key=lambda x: x.hp):
        if dmg_type == "NORMAL":
            max_dmg = caster.ATK + base + roll - e.DEF
        elif dmg_type == "MAGIC":
            max_dmg = caster.MAGIC + base + roll - e.MAGIC_DEF
        else:
            break
        if max_dmg >= e.hp:
            return e
    return _highest_threat(enemies)


# ─────────────────────────── per-class strategies ─────────────────────────
# Each returns (ability_name, targets_list) or (None, None) to defer to fallback.

def _strategy_priest(caster):
    allies = _allies(caster)
    enemies = _enemies(caster)

    # 1. Emergency heal on lowest-HP wounded ally
    wounded = [a for a in allies if _hp_ratio(a) < 0.4]
    if wounded and _has_move(caster, "Heal") and _can_afford(caster, "Heal"):
        return "Heal", [_lowest_hp(wounded)]

    # 2. Team-wide Rejuvenation when several are hurt
    if allies and _has_move(caster, "Rejuvenation") and _can_afford(caster, "Rejuvenation"):
        avg = sum(_hp_ratio(a) for a in allies) / len(allies)
        if avg < 0.7:
            targets = _valid_targets(caster, "Rejuvenation")
            if targets:
                return "Rejuvenation", targets

    # 3. Bless upkeep — cast if no ally has it
    if (_has_move(caster, "Bless") and _can_afford(caster, "Bless")
            and not any(_has_effect(a, "BLESS") for a in allies)):
        targets = _valid_targets(caster, "Bless")
        if targets:
            return "Bless", targets

    # 4. Otherwise, smite
    if enemies and _has_move(caster, "Smite") and _can_afford(caster, "Smite"):
        return "Smite", [_damage_target(caster, "Smite", enemies)]

    return None, None


def _strategy_knight(caster):
    enemies = _enemies(caster)
    allies = _allies(caster)
    has_slash = _has_move(caster, "Sword slash") and _can_afford(caster, "Sword slash")

    # 1. Sword slash for a guaranteed kill (max roll can KO). Never miss a KO.
    if enemies and has_slash:
        base = Ability.get_attr("Sword slash", "DMG_BASE") or 0
        roll = Ability.get_attr("Sword slash", "DMG_ROLL") or 0
        killable = None
        for e in sorted(enemies, key=lambda x: x.hp):
            if caster.ATK + base + roll - e.DEF >= e.hp:
                killable = e
                break
        if killable:
            return "Sword slash", [killable]

    # 2. Desperate at <10 HP — skip setup/defensive plays, just swing
    if caster.hp < 10:
        if enemies and has_slash:
            return "Sword slash", [_damage_target(caster, "Sword slash", enemies)]
        return None, None

    # 3. Sharpen sword if the buff isn't already active — damage window opener
    if (_has_move(caster, "Sharpen sword") and _can_afford(caster, "Sharpen sword")
            and not _has_effect(caster, "SHRPN")):
        return "Sharpen sword", [caster]

    # 4. Shield up only if THIS Knight is the softest ally and below 40 HP
    if (allies and _has_move(caster, "Raise shield") and _can_afford(caster, "Raise shield")
            and not _has_effect(caster, "SHLD") and caster.hp < 40):
        if _lowest_hp(allies) is caster:
            return "Raise shield", [caster]

    # 5. Default: slash the softest / kill-shot target
    if enemies and has_slash:
        return "Sword slash", [_damage_target(caster, "Sword slash", enemies)]
    return None, None


def _strategy_berserker(caster):
    enemies = _enemies(caster)
    # 1. Desperate at <10 HP — skip setup, just Cleave
    if caster.hp < 10:
        if enemies and _has_move(caster, "Cleave") and _can_afford(caster, "Cleave"):
            return "Cleave", enemies
        return None, None
    # 2. Frenzy self-buff first — huge ATK/CRIT
    if (_has_move(caster, "Frenzy") and _can_afford(caster, "Frenzy")
            and not _has_effect(caster, "FRENZY")):
        return "Frenzy", [caster]
    # 2. Taunt the biggest threat if not already taunted
    if enemies and _has_move(caster, "Taunt") and _can_afford(caster, "Taunt"):
        untaunted = [e for e in enemies if not _has_effect(e, "TAUNT")]
        if untaunted:
            return "Taunt", [_highest_threat(untaunted)]
    # 3. Cleave — always solid when 2+ enemies live
    if len(enemies) >= 2 and _has_move(caster, "Cleave") and _can_afford(caster, "Cleave"):
        return "Cleave", enemies
    # 4. Single enemy: still Cleave if that's all we've got
    if enemies and _has_move(caster, "Cleave") and _can_afford(caster, "Cleave"):
        return "Cleave", enemies
    return None, None


def _strategy_assassin(caster):
    """Optimal cycle: Mark → Poison → Poison per enemy (setting up all of them),
    then Stab anyone the ticks have pushed under 50% HP. Shroud is a stall when
    HP/MP get low so the poison ticks finish the job."""
    enemies = _enemies(caster)
    if not enemies:
        return None, None

    max_psn = Ability.get_attr("Poison", "EFFECT_STACKS") or 2
    hp_low = _hp_ratio(caster) < 0.4
    mp_low = caster.mp < caster.max_mp * 0.4

    # 1. Emergency Shroud — stall while poison ticks finish, refill MP, gain dodge
    if ((hp_low or mp_low) and _has_move(caster, "Shroud")
            and _can_afford(caster, "Shroud") and not _has_effect(caster, "SHROUD")):
        return "Shroud", [caster]

    # 2. Finisher — anyone below 50% HP gets Stabbed. Prefer Marked targets
    #    (bonus damage from Stab/Backstab against MARKED).
    weakened = [e for e in enemies if _hp_ratio(e) < 0.5]
    if weakened and _has_move(caster, "Stab/Backstab") and _can_afford(caster, "Stab/Backstab"):
        marked_weak = [e for e in weakened if _has_effect(e, "MARKED")]
        target = _lowest_hp(marked_weak or weakened)
        return "Stab/Backstab", [target]

    # 3. Setup cycle. Process enemies in threat order — highest threat first —
    #    and for each, apply Mark then Poison-to-cap before moving to the next.
    for e in sorted(enemies, key=_threat_score, reverse=True):
        if not _has_effect(e, "MARKED"):
            if _has_move(caster, "Mark") and _can_afford(caster, "Mark"):
                return "Mark", [e]
            break  # can't afford Mark on the current target — bail to stall/fallback
        if _stacks(e, "PSN") < max_psn:
            if _has_move(caster, "Poison") and _can_afford(caster, "Poison"):
                return "Poison", [e]
            break

    # 4. Everyone's fully set up — stall with Shroud (regen MP, gain dodge)
    #    while the poison ticks bring them under 50%.
    if (_has_move(caster, "Shroud") and _can_afford(caster, "Shroud")
            and not _has_effect(caster, "SHROUD")):
        return "Shroud", [caster]

    # 5. Last resort — Stab whoever's weakest, preferring Marked
    if _has_move(caster, "Stab/Backstab") and _can_afford(caster, "Stab/Backstab"):
        marked = [e for e in enemies if _has_effect(e, "MARKED")]
        target = _lowest_hp(marked or enemies)
        return "Stab/Backstab", [target]

    return None, None


def _strategy_thief(caster):
    enemies = _enemies(caster)
    # 1. Sneak self-buff first — big CRIT/DODGE
    if (_has_move(caster, "Sneak") and _can_afford(caster, "Sneak")
            and not _has_effect(caster, "SNEAK")):
        return "Sneak", [caster]
    # 2. Distract the tankiest enemy for a Shiv follow-up
    if enemies and _has_move(caster, "Distract") and _can_afford(caster, "Distract"):
        undistracted = [e for e in enemies if not _has_effect(e, "DISTRACT")]
        if undistracted:
            return "Distract", [max(undistracted, key=lambda e: e.DEF)]
    # 3. Shiv the softest / distracted target
    if enemies and _has_move(caster, "Shiv") and _can_afford(caster, "Shiv"):
        distracted = [e for e in enemies if _has_effect(e, "DISTRACT")]
        if distracted:
            return "Shiv", [_lowest_hp(distracted)]
        return "Shiv", [_damage_target(caster, "Shiv", enemies)]
    return None, None


def _strategy_thug(caster):
    allies = _allies(caster)
    enemies = _enemies(caster)
    # 1. Desperate at <10 HP — skip Riot/Rest/Tackle, throw Punches (no recoil)
    if caster.hp < 10:
        if enemies and _has_move(caster, "Punch") and _can_afford(caster, "Punch"):
            return "Punch", [_damage_target(caster, "Punch", enemies)]
        return None, None
    # 2. Riot if any ally isn't at cap (team ATK/CRIT buff)
    if allies and _has_move(caster, "Riot") and _can_afford(caster, "Riot"):
        cap = Ability.get_attr("Riot", "EFFECT_STACKS") or 5
        min_stacks = min(_stacks(a, "RIOT") for a in allies)
        if min_stacks < cap:
            targets = _valid_targets(caster, "Riot")
            if targets:
                return "Riot", targets
    # 2. Rest when hurt (Tackle costs HP; recover first)
    if _hp_ratio(caster) < 0.4:
        return "Rest", [caster]
    # 3. Tackle: primary attack — higher damage + 25% stun, at HP cost
    if enemies and _has_move(caster, "Tackle") and _can_afford(caster, "Tackle"):
        target = _damage_target(caster, "Tackle", enemies)
        if target:
            return "Tackle", [target]
    # 4. Fallback punch
    if enemies and _has_move(caster, "Punch") and _can_afford(caster, "Punch"):
        return "Punch", [_damage_target(caster, "Punch", enemies)]
    return None, None


# ─────────────────────────────── dispatch ───────────────────────────────

_STRATEGIES = {
    "Priest":    _strategy_priest,
    "Knight":    _strategy_knight,
    "Berserker": _strategy_berserker,
    "Assassin":  _strategy_assassin,
    "Thief":     _strategy_thief,
    "Thug":      _strategy_thug,
}


def choose_action(battle, unit):
    """Returns (ability_name, targets) for this AI-controlled unit's turn.
    Always returns a legal move if any exist; falls back to Rest otherwise."""
    strategy = _STRATEGIES.get(getattr(type(unit), "className", None))
    if strategy:
        try:
            move, targets = strategy(unit)
        except Exception:
            move, targets = None, None
        if move and targets and _can_afford(unit, move):
            return move, list(targets)
    return _fallback(unit)


def _fallback(unit):
    """Random legal move — same shape as the old Unit.choose_ai_move behaviour."""
    legal = []
    for move in unit.movesList:
        if not _can_afford(unit, move):
            continue
        targets = _valid_targets(unit, move)
        if not targets:
            continue
        legal.append((move, targets))
    if not legal:
        return "Rest", [unit]
    move, targets = random.choice(legal)
    target_type = Ability.get_attr(move, "TARGET_TYPE")
    if target_type == 1 and len(targets) > 1:
        targets = [random.choice(targets)]
    return move, targets
