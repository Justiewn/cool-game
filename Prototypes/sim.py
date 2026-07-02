"""Headless battle simulator.

Runs full AI-vs-AI battles without pygame, using the same Battle, Unit, and
ai modules the GUI uses. Results reflect real gameplay for tuning strategies
and comparing team compositions.

Usage:
    python sim.py K,P,K A,A,A --runs 1000
    python sim.py K,K,K TH,TH,TH,TH,TH --runs 500 -v

Class keys: T (Thug), K (Knight), P (Priest), TH (Thief), B (Berserker), A (Assassin)
"""

import argparse
import builtins
import os
import sys
import time
from collections import Counter

# Ensure we can import from this directory when run from elsewhere
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from battle import Battle
from Units import (
    Unit, Unit_Knight, Unit_Priest, Unit_Thief,
    Unit_Berserker, Unit_Assassin, Unit_Thug,
)
from Abilities import Ability
import ai


_CLASS_MAP = {
    'T':  Unit_Thug,
    'K':  Unit_Knight,
    'P':  Unit_Priest,
    'TH': Unit_Thief,
    'B':  Unit_Berserker,
    'A':  Unit_Assassin,
}

# Cap runaway battles as draws. Any typical fight resolves in well under this.
MAX_TURNS = 400

# Cached at import time so we don't rescan the ability dict on every helper call.
_INCAP_STATUSES = {
    attrs["EFFECT_STATUS"]
    for attrs in Ability.AbilitiesDict.values()
    if attrs.get("PREVENTS_ACTION") and attrs.get("EFFECT_STATUS")
}


# ─────────────────────────────── helpers ────────────────────────────────

def parse_team(spec):
    """Parses 'K,P,K' into [Unit_Knight, Unit_Priest, Unit_Knight]."""
    classes = []
    for key in spec.split(','):
        key = key.strip().upper()
        if not key:
            continue
        if key not in _CLASS_MAP:
            raise ValueError(
                f"Unknown class key '{key}'. Options: {sorted(_CLASS_MAP)}"
            )
        classes.append(_CLASS_MAP[key])
    if not classes:
        raise ValueError("Team spec is empty")
    return classes


def _incap_status(unit):
    for status in unit.effect_stacks_dict:
        if status in _INCAP_STATUSES:
            return status
    return None


def _pickable_units(team_id):
    """Alive, non-incapacitated units on this team — those that need to act."""
    return [
        u for u in Unit.get_units("all", team_id)
        if u.alive and not u.dead and not _incap_status(u)
    ]


def _fire_team_start_ticks(battle, team_id):
    """PHASE=0 batch tick at team turn start. Mirrors GUI._fire_team_turn_start_ticks."""
    for unit in Unit.get_units("alive", team_id):
        if _incap_status(unit):
            continue
        battle.resolve_turn_start(unit)
        battle.resolve_before_action(unit)
    Unit.process_downed(battle)


def _fire_team_end_batch(battle, team_id):
    """At team-turn-end: run the full four-phase tick cycle for units that
    skipped their action (incapacitated), then ghost-caster ticks for downed."""
    for unit in Unit.get_units("all", team_id):
        if unit.dead or not unit.alive:
            continue
        if _incap_status(unit):
            battle.resolve_turn_start(unit)
            battle.resolve_before_action(unit)
            battle.resolve_after_action(unit)
            battle.resolve_turn_end(unit)
    for unit in Unit.get_units("all", team_id):
        if unit.downed:
            battle.resolve_ghost_caster_turns(unit)
    Unit.process_downed(battle)


# ────────────────────────────── one battle ──────────────────────────────

def simulate_one(team0_classes, team1_classes):
    """Runs a single battle to completion. Returns a result dict.
    Assumes the caller has silenced print() (e.g. by monkey-patching builtins.print)."""
    Unit.remove_all()
    Ability._combat_events.clear()

    # Spawn units. Generic names — sim doesn't care about flavour.
    for i, cls in enumerate(team0_classes):
        cls(f"P{i + 1}", 0)
    for i, cls in enumerate(team1_classes):
        cls(f"E{i + 1}", 1)

    battle = Battle()
    turns = 0
    rounds = 0
    current_team = 0
    ability_uses = Counter()   # ability name -> count

    awaiting = _pickable_units(0)
    _fire_team_start_ticks(battle, 0)

    while not battle.is_battle_over() and turns < MAX_TURNS:
        # Prune awaiting for mid-round deaths / stuns
        awaiting = [
            u for u in awaiting
            if u.alive and not u.dead and not _incap_status(u)
        ]

        if not awaiting:
            _fire_team_end_batch(battle, current_team)
            if battle.is_battle_over():
                break
            current_team = 1 - current_team
            awaiting = _pickable_units(current_team)
            _fire_team_start_ticks(battle, current_team)
            rounds += 1
            continue

        picked = ai.choose_next_unit(awaiting, battle)
        if picked is None:
            picked = awaiting[0]

        move_name, targets = ai.choose_action(battle, picked)
        if move_name and targets:
            selected = Ability(move_name, Ability.ability_ID_counter)
            selected.initial_cast(targets, picked, battle)
            battle.resolve_after_action(picked)
            battle.resolve_turn_end(picked)
            Unit.process_downed(battle)
            ability_uses[move_name] += 1

        try:
            awaiting.remove(picked)
        except ValueError:
            pass
        turns += 1
        # Prevent the combat-event queue from growing unboundedly.
        Ability._combat_events.clear()

    alive_0 = Unit.num_units(0, "alive")
    alive_1 = Unit.num_units(1, "alive")
    if alive_0 > 0 and alive_1 == 0:
        winner = 0
    elif alive_1 > 0 and alive_0 == 0:
        winner = 1
    else:
        winner = None   # draw / timed out / mutual kill

    return {
        'winner': winner,
        'turns': turns,
        'rounds': rounds,
        'timed_out': turns >= MAX_TURNS,
        'survivors_0': alive_0,
        'survivors_1': alive_1,
        'ability_uses': ability_uses,
    }


# ─────────────────────────────── batch run ──────────────────────────────

def run_batch(team0_classes, team1_classes, runs=100, verbose=False):
    """Runs N battles. Returns aggregated stats + per-run details if verbose.
    Silences all print() output by replacing builtins.print with a no-op for
    the duration of the batch — much faster than redirect_stdout, which still
    incurs string ops on every ability's narration."""
    wins = Counter()
    turn_totals = 0
    round_totals = 0
    timed_out = 0
    ability_totals = Counter()
    per_run = []

    _orig_print = builtins.print
    _orig_sleep = time.sleep
    builtins.print = lambda *a, **kw: None
    time.sleep = lambda *a, **kw: None   # Unit.process_downed uses 0.4s pacing pauses; skip them
    try:
        for i in range(runs):
            result = simulate_one(team0_classes, team1_classes)
            wins[result['winner']] += 1
            turn_totals += result['turns']
            round_totals += result['rounds']
            if result['timed_out']:
                timed_out += 1
            ability_totals.update(result['ability_uses'])
            if verbose:
                per_run.append(result)
    finally:
        builtins.print = _orig_print
        time.sleep = _orig_sleep

    Unit.remove_all()
    Ability._combat_events.clear()

    return {
        'runs': runs,
        'wins_0': wins[0],
        'wins_1': wins[1],
        'draws': wins[None],
        'avg_turns': turn_totals / max(runs, 1),
        'avg_rounds': round_totals / max(runs, 1),
        'timed_out': timed_out,
        'ability_uses': ability_totals,
        'per_run': per_run,
    }


# ──────────────────────────────── CLI ────────────────────────────────

def _classes_to_names(classes):
    return [c.className for c in classes]


def main():
    parser = argparse.ArgumentParser(
        description="Headless AI battle simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n"
               "  python sim.py K,P,K A,A,A --runs 1000\n"
               "Class keys: T (Thug), K (Knight), P (Priest), TH (Thief), B (Berserker), A (Assassin)",
    )
    parser.add_argument("team0", help="Team 0 comp, comma-separated class keys")
    parser.add_argument("team1", help="Team 1 comp, comma-separated class keys")
    parser.add_argument("--runs", type=int, default=100, help="Battles to run (default 100)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print per-battle details")
    parser.add_argument("--top-abilities", type=int, default=10,
                        help="Show the N most-used abilities across all runs (default 10)")
    args = parser.parse_args()

    t0 = parse_team(args.team0)
    t1 = parse_team(args.team1)

    print(f"Team 0 ({len(t0)}): {', '.join(_classes_to_names(t0))}")
    print(f"Team 1 ({len(t1)}): {', '.join(_classes_to_names(t1))}")
    print(f"Running {args.runs} battles (max {MAX_TURNS} turns each)...")
    print()

    start = time.time()
    stats = run_batch(t0, t1, args.runs, verbose=args.verbose)
    elapsed = time.time() - start
    total = stats['runs']

    def pct(n):
        return f"{n / total * 100:5.1f}%"

    print(f"Results after {total} battles "
          f"({elapsed:.2f}s total, {elapsed / total * 1000:.1f} ms/battle):")
    print(f"  Team 0 wins:      {stats['wins_0']:5d}  ({pct(stats['wins_0'])})")
    print(f"  Team 1 wins:      {stats['wins_1']:5d}  ({pct(stats['wins_1'])})")
    print(f"  Draws / timeouts: {stats['draws']:5d}  ({pct(stats['draws'])})")
    print(f"  Avg turns / battle:  {stats['avg_turns']:.1f}")
    print(f"  Avg rounds / battle: {stats['avg_rounds']:.1f}")
    if stats['timed_out']:
        print(f"  Timed out (hit MAX_TURNS={MAX_TURNS}): {stats['timed_out']}")

    if args.top_abilities:
        print()
        print(f"Top {args.top_abilities} most-used abilities:")
        for name, count in stats['ability_uses'].most_common(args.top_abilities):
            avg = count / total
            print(f"  {name:20s}  {count:6d}  ({avg:.2f} / battle)")

    if args.verbose:
        print()
        print("Per-battle results:")
        for i, r in enumerate(stats['per_run']):
            winner = 'draw' if r['winner'] is None else f"team {r['winner']}"
            print(f"  #{i + 1:4d}  winner={winner:6s}  turns={r['turns']:3d}  "
                  f"survivors 0/1 = {r['survivors_0']}/{r['survivors_1']}"
                  + ("  [TIMED OUT]" if r['timed_out'] else ""))


if __name__ == "__main__":
    main()
