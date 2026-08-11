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

import math
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

def _min_turns_left(unit, status):
    """Minimum turns_left across all live effects of `status` on `unit`.
    Returns 0 when the status isn't active — callers should gate on _stacks first."""
    matching = [e for e in unit.target_Ability_queue
                if e.AttrValDict.get("EFFECT_STATUS") == status]
    if not matching:
        return 0
    return min(e.turns_left for e in matching)

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


def _priests(units):
    """Filter for Priest-class units — targets the AI wants to focus down first
    because Priests heal enemy teammates and reset our damage progress."""
    return [u for u in units if getattr(type(u), "className", "") == "Priest"]

def _priority_target(enemies):
    """Preferred non-kill-shot target: Priest first (lowest-HP among them if
    multiple), else the highest-threat enemy overall."""
    if not enemies:
        return None
    priests = _priests(enemies)
    if priests:
        return _lowest_hp(priests)
    return _highest_threat(enemies)


def _damage_target(caster, name, enemies):
    """Preferred target for a damage move:
       1. an enemy the max roll can outright kill (lowest-HP first);
       2. otherwise a Priest if any is alive (focus the healer down first);
       3. otherwise the highest-threat enemy in range."""
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
    return _priority_target(enemies)


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
    # 2. Taunt FIRST — team-wide DEF debuff. Only cast if not every enemy
    #    already has TAUNT (Taunt hits all enemies at once, so one cast
    #    covers the whole team; recasting is wasted MP).
    if enemies and _has_move(caster, "Taunt") and _can_afford(caster, "Taunt"):
        if not all(_has_effect(e, "TAUNT") for e in enemies):
            targets = _valid_targets(caster, "Taunt")
            if targets:
                return "Taunt", targets
    # 3. Frenzy AFTER Taunt — Frenzy drops our DEF, so we want enemies
    #    already debuffed (Taunted) so their return damage is minimised.
    if (_has_move(caster, "Frenzy") and _can_afford(caster, "Frenzy")
            and not _has_effect(caster, "FRENZY")):
        return "Frenzy", [caster]
    # 4. Cleave — always solid when 2+ enemies live
    if len(enemies) >= 2 and _has_move(caster, "Cleave") and _can_afford(caster, "Cleave"):
        return "Cleave", enemies
    # 5. Single enemy: still Cleave if that's all we've got
    if enemies and _has_move(caster, "Cleave") and _can_afford(caster, "Cleave"):
        return "Cleave", enemies
    return None, None


def _strategy_assassin(caster):
    """Focus one enemy at a time. Squishiest (lowest DEF) is always the current
    focus. Full setup on that target = MARKED + max Poison stacks; poison is
    skipped once the target is <50% HP (they'll die faster to a Stab). Move to
    the next squishiest target once the current one is either fully set up
    (and still healthy) or below 50% HP (and stabbable). Shroud is a stall for
    low HP/MP and a "nothing else to do" fallback."""
    enemies = _enemies(caster)
    if not enemies:
        return None, None

    max_psn = Ability.get_attr("Poison", "EFFECT_STACKS") or 2
    hp_low = caster.hp < 30
    mp_low = caster.mp < caster.max_mp * 0.4

    # 0. Guaranteed kill: any enemy that Stab/Backstab can drop this turn (with
    #    or without MARK) gets stabbed NOW — that's the highest priority.
    #    Assumes max damage roll + crit multiplier; adds the missing-HP backstab
    #    bonus for MARKED targets. Prefer Priest, then lowest HP.
    if _has_move(caster, "Stab/Backstab") and _can_afford(caster, "Stab/Backstab"):
        base = Ability.get_attr("Stab/Backstab", "DMG_BASE") or 0
        roll = Ability.get_attr("Stab/Backstab", "DMG_ROLL") or 0
        def _stab_max(target):
            raw = caster.ATK + base + roll - target.DEF
            # crit multiplier
            with_crit = math.ceil(max(raw, 0) * 1.5) if raw > 0 else 0
            best = max(raw, with_crit)
            # Marked backstab bonus (ignores DEF)
            if _has_effect(target, "MARKED"):
                best += math.floor((target.max_hp - target.hp) * 0.2)
            return best
        kill_ready = [e for e in enemies if _stab_max(e) >= e.hp]
        if kill_ready:
            target = min(kill_ready, key=lambda e: (getattr(type(e), "className", "") != "Priest", e.hp))
            return "Stab/Backstab", [target]

    # 1. Shroud — only when caster is genuinely in trouble (HP<30) or MP-starved.
    #    Never Shroud at full MP: the MP-regen benefit is wasted and stalling
    #    delays killing the weakest enemy in the setup/finish cycle below.
    if ((hp_low or mp_low) and caster.mp < caster.max_mp
            and _has_move(caster, "Shroud")
            and _can_afford(caster, "Shroud") and not _has_effect(caster, "SHROUD")):
        return "Shroud", [caster]

    # 2. Finisher — any enemy at or below 50% HP.
    #    Among the wounded, prefer a MARKED one; else pick the squishiest (lowest DEF).
    #    On ties, prefer the Priest (heal-blocker priority).
    #    If the chosen target isn't Marked yet → Mark first, so the backstab bonus lands.
    #    Otherwise Stab/Backstab it.
    weak = [e for e in enemies if _hp_ratio(e) <= 0.5]
    if weak:
        marked_weak = [e for e in weak if _has_effect(e, "MARKED")]
        pool = marked_weak or weak
        # (is_not_priest, DEF) → priests sort first; then by increasing DEF
        target = min(pool, key=lambda e: (getattr(type(e), "className", "") != "Priest", e.DEF))
        if not _has_effect(target, "MARKED"):
            if _has_move(caster, "Mark") and _can_afford(caster, "Mark"):
                return "Mark", [target]
        else:
            if _has_move(caster, "Stab/Backstab") and _can_afford(caster, "Stab/Backstab"):
                return "Stab/Backstab", [target]

    # 3. Priest priority — Mark then Stab, skip Poison entirely.
    #    Priests can undo poison ticks via Heal, so drain them directly with
    #    Stab/Backstab (bonus damage scales with their missing HP anyway).
    #    If any priest is already MARKED, Stab that one — never Mark a second
    #    priest while one is still marked (focus one target at a time).
    priests = _priests(enemies)
    if priests:
        marked_priests = [p for p in priests if _has_effect(p, "MARKED")]
        if marked_priests:
            target = _lowest_hp(marked_priests)
            if _has_move(caster, "Stab/Backstab") and _can_afford(caster, "Stab/Backstab"):
                return "Stab/Backstab", [target]
        else:
            target = _lowest_hp(priests)
            if _has_move(caster, "Mark") and _can_afford(caster, "Mark"):
                return "Mark", [target]

    # 4. Setup cycle for non-Priest enemies. Squishiness order (lowest DEF first).
    #    A target is "set up" if MARKED and at Poison cap; fully-set-up healthy
    #    targets get skipped so focus moves to the next in order.
    for target in sorted(enemies, key=lambda e: e.DEF):
        if getattr(type(target), "className", "") == "Priest":
            continue  # handled by branch 3
        # Below-50% targets are handled by branch 2 above; only apply setup to healthy ones.
        if _hp_ratio(target) <= 0.5:
            continue
        needs_mark = not _has_effect(target, "MARKED")
        needs_poison = _stacks(target, "PSN") < max_psn
        if not (needs_mark or needs_poison):
            continue  # already set up — try next target in squishiness order
        # Mark before poison so the backstab bonus is ready when they drop.
        if needs_mark:
            if _has_move(caster, "Mark") and _can_afford(caster, "Mark"):
                return "Mark", [target]
        elif needs_poison:
            if _has_move(caster, "Poison") and _can_afford(caster, "Poison"):
                return "Poison", [target]
        break  # can't afford current step — bail to stall/fallback rather than jump ahead

    # 4. Everyone set up (or unhittable) — stall with Shroud while poison ticks
    #    work. Skip the stall at full MP: nothing to regen, so fall through to
    #    Stab and keep the pressure on the weakest enemy.
    if (caster.mp < caster.max_mp
            and _has_move(caster, "Shroud") and _can_afford(caster, "Shroud")
            and not _has_effect(caster, "SHROUD")):
        return "Shroud", [caster]

    # 5. Last resort — Stab whoever's softest, preferring Marked, Priest first on ties.
    if _has_move(caster, "Stab/Backstab") and _can_afford(caster, "Stab/Backstab"):
        marked = [e for e in enemies if _has_effect(e, "MARKED")]
        pool = marked or enemies
        target = min(pool, key=lambda e: (getattr(type(e), "className", "") != "Priest", e.DEF))
        return "Stab/Backstab", [target]

    return None, None


def _strategy_thief(caster):
    """Focus one target at a time: the squishiest enemy (lowest DEF), Priest
    first if any alive. Sneak → Distract → Shiv, then keep Shivving until the
    focus dies, then pick the next squishiest. Distract doesn't stack, so only
    one Thief needs to apply it per target."""
    enemies = _enemies(caster)
    if not enemies:
        return None, None

    # Focus target: Priest first, then squishiest (lowest DEF), HP as tiebreaker
    focus = min(
        enemies,
        key=lambda e: (getattr(type(e), "className", "") != "Priest", e.DEF, e.hp),
    )

    # 1. Sneak self-buff first — big CRIT / DODGE for the incoming Shivs
    if (_has_move(caster, "Sneak") and _can_afford(caster, "Sneak")
            and not _has_effect(caster, "SNEAK")):
        return "Sneak", [caster]

    # 2. Distract the focus target if not already distracted (EFFECT_STACKS=1
    #    so recasting on an already-distracted target is wasted MP)
    if (_has_move(caster, "Distract") and _can_afford(caster, "Distract")
            and not _has_effect(focus, "DISTRACT")):
        return "Distract", [focus]

    # 3. Shiv the focus target
    if _has_move(caster, "Shiv") and _can_afford(caster, "Shiv"):
        return "Shiv", [focus]

    return None, None


def _strategy_thug(caster):
    allies = _allies(caster)
    enemies = _enemies(caster)
    # 1. Desperate at <10 HP — skip Riot/Rest/Tackle, throw Punches (no recoil)
    if caster.hp < 10:
        if enemies and _has_move(caster, "Punch") and _can_afford(caster, "Punch"):
            return "Punch", [_damage_target(caster, "Punch", enemies)]
        return None, None
    # 2. Riot: build stacks while under cap, then only refresh when the buff
    #    is about to lapse (turns_left == 1 → expires on the next caster turn,
    #    since resolve_before_action decrements before the AI picks). Between
    #    refreshes the AI falls through to Tackle/Punch instead of Riot-spamming.
    if allies and _has_move(caster, "Riot") and _can_afford(caster, "Riot"):
        cap = Ability.get_attr("Riot", "EFFECT_STACKS") or 5
        min_stacks = min(_stacks(a, "RIOT") for a in allies)
        lapse_soon = any(0 < _min_turns_left(a, "RIOT") <= 1 for a in allies)
        if min_stacks < cap or lapse_soon:
            targets = _valid_targets(caster, "Riot")
            if targets:
                return "Riot", targets
    # 2. Rest when hurt (Tackle costs HP; recover first)
    if _hp_ratio(caster) < 0.4:
        return "Rest", [caster]
    # 3a. Punch instead of Tackle when a min-roll Punch is a guaranteed KO.
    #     Punch has no recoil, so save the HP cost when it isn't needed.
    if enemies and _has_move(caster, "Punch") and _can_afford(caster, "Punch"):
        pbase = Ability.get_attr("Punch", "DMG_BASE") or 0
        proll = Ability.get_attr("Punch", "DMG_ROLL") or 0
        finish = None
        for e in sorted(enemies, key=lambda x: x.hp):
            if caster.ATK + pbase - proll - e.DEF >= e.hp:
                finish = e
                break
        if finish:
            return "Punch", [finish]
    # 3. Tackle: primary attack — higher damage + 20% stun, at HP cost.
    #    Don't stack Tackle on an already-stunned enemy (they're skipping
    #    their turn — spreading stuns to another target is worth more)
    #    unless the tackle can KO them.
    if enemies and _has_move(caster, "Tackle") and _can_afford(caster, "Tackle"):
        target = _damage_target(caster, "Tackle", enemies)
        if target:
            if _has_effect(target, "STUN"):
                base = Ability.get_attr("Tackle", "DMG_BASE") or 0
                roll = Ability.get_attr("Tackle", "DMG_ROLL") or 0
                is_killshot = caster.ATK + base + roll - target.DEF >= target.hp
                if not is_killshot:
                    non_stunned = [e for e in enemies if not _has_effect(e, "STUN")]
                    if non_stunned:
                        alt = _damage_target(caster, "Tackle", non_stunned)
                        if alt:
                            target = alt
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


def choose_next_unit(units, battle):
    """Picks which of `units` (all on the same AI-controlled team, awaiting
    their turn) should act next. Heuristic: prefer high-threat units so
    buffs land before the finishers, but demote units that are stunned or
    asleep (they'd skip anyway)."""
    if not units:
        return None
    incap_statuses = {"STUN", "SLEEP"}
    def score(u):
        s = _threat_score(u)
        # Demote incapacitated units — let them tick off before doing anything meaningful
        if any(st in incap_statuses for st in u.effect_stacks_dict):
            s -= 10_000
        return s
    return max(units, key=score)


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
