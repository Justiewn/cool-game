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
    # 1. Sharpen sword if the buff isn't up — big damage window opener
    if (_has_move(caster, "Sharpen sword") and _can_afford(caster, "Sharpen sword")
            and not _has_effect(caster, "SHRPN")):
        return "Sharpen sword", [caster]
    # 2. Shield up when hurt and no shield active
    if (_hp_ratio(caster) < 0.55 and _has_move(caster, "Raise shield")
            and _can_afford(caster, "Raise shield") and not _has_effect(caster, "SHLD")):
        return "Raise shield", [caster]
    # 3. Attack
    if enemies and _has_move(caster, "Sword slash") and _can_afford(caster, "Sword slash"):
        return "Sword slash", [_damage_target(caster, "Sword slash", enemies)]
    return None, None


def _strategy_berserker(caster):
    enemies = _enemies(caster)
    # 1. Frenzy self-buff first — huge ATK/CRIT
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
    enemies = _enemies(caster)
    marked = [e for e in enemies if _has_effect(e, "MARKED")]
    # 1. Regen MP + dodge with Shroud when low on mana and unshrouded
    if (caster.mp < caster.max_mp * 0.4 and _has_move(caster, "Shroud")
            and _can_afford(caster, "Shroud") and not _has_effect(caster, "SHROUD")):
        return "Shroud", [caster]
    # 2. Finish marked targets with Stab/Backstab (bonus damage)
    if marked and _has_move(caster, "Stab/Backstab") and _can_afford(caster, "Stab/Backstab"):
        return "Stab/Backstab", [_lowest_hp(marked)]
    # 3. Mark the biggest threat if unmarked
    if enemies and _has_move(caster, "Mark") and _can_afford(caster, "Mark"):
        unmarked = [e for e in enemies if not _has_effect(e, "MARKED")]
        if unmarked:
            return "Mark", [_highest_threat(unmarked)]
    # 4. Poison a soft target that isn't already at cap
    if enemies and _has_move(caster, "Poison") and _can_afford(caster, "Poison"):
        max_psn = Ability.get_attr("Poison", "EFFECT_STACKS") or 2
        soft = [e for e in enemies if _stacks(e, "PSN") < max_psn]
        if soft:
            return "Poison", [min(soft, key=lambda e: e.DEF)]
    # 5. Otherwise Stab whoever's weakest
    if enemies and _has_move(caster, "Stab/Backstab") and _can_afford(caster, "Stab/Backstab"):
        return "Stab/Backstab", [_lowest_hp(enemies)]
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
    # 1. Uproar if any ally isn't at cap
    if allies and _has_move(caster, "Uproar") and _can_afford(caster, "Uproar"):
        cap = Ability.get_attr("Uproar", "EFFECT_STACKS") or 5
        min_stacks = min(_stacks(a, "UPROAR") for a in allies)
        if min_stacks < cap:
            targets = _valid_targets(caster, "Uproar")
            if targets:
                return "Uproar", targets
    # 2. Self-heal when hurt
    if (_hp_ratio(caster) < 0.45 and _has_move(caster, "Bandage")
            and _can_afford(caster, "Bandage")):
        return "Bandage", [caster]
    # 3. Punch weakest
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
