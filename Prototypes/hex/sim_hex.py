"""Headless AI-vs-AI runner for the hex prototype.

Usage:
    python sim_hex.py K,P,K T,T,T --runs 100

Class keys: K P TH B A T (same as FRAY).
Reports win rate, turn counts, and any crashes.
"""

import _bootstrap  # noqa: F401

import argparse
import builtins
import sys
import time

from Units import Unit
from board import Board
from hex_unit import HEX_CLASS_MAP
from battle_hex import HexBattle
from ai_hex import choose_turn


def parse_team(spec):
    return [HEX_CLASS_MAP[k.strip().upper()] for k in spec.split(",")]


def place_teams(board, team0_classes, team1_classes, name_index=0):
    # Simple two-column starting formation.
    for i, cls in enumerate(team0_classes):
        name = cls.name_pool[(name_index + i) % len(cls.name_pool)]
        u = cls(name, 0)
        board.place(u, (0, i))
    for i, cls in enumerate(team1_classes):
        name = cls.name_pool[(name_index + i) % len(cls.name_pool)]
        u = cls(name, 1)
        board.place(u, (board.width - 1 - (i // 2), i))


def run_one(team0_classes, team1_classes, board_size, max_turns, verbose=False):
    Unit.remove_all()
    board = Board(*board_size)
    place_teams(board, team0_classes, team1_classes)
    hb = HexBattle(board)
    hb.start()

    turns = 0
    while not hb.is_over() and turns < max_turns:
        # Team-turn loop: keep picking the next awaiting unit until awaiting
        # empties (auto-end may drop the current unit and flip teams inside
        # perform_ability). Snapshot the team before each pick because
        # auto-end can flip it mid-action.
        team_at_turn_start = hb.current_team
        while (hb.current_team == team_at_turn_start
               and hb.awaiting[hb.current_team]):
            u = hb.awaiting[hb.current_team][0]
            if not u.alive:
                # Drop this dead unit and try the next awaiting one.
                hb.awaiting[hb.current_team].pop(0)
                continue
            hb.begin_unit_turn(u)
            dest, ability, target = choose_turn(u, board)
            if dest is not None:
                hb.perform_move(dest)
            if ability is not None and target is not None:
                hb.perform_ability(ability, target)
            # Force the unit out of awaiting if it didn't auto-end (e.g. it
            # opted to only move or only cast) — sim doesn't want to loop
            # forever on a unit that keeps re-picking itself.
            if hb.current_unit is u:
                hb.end_unit_turn()
            if hb.is_over():
                break
        turns += 1

    alive0 = sum(1 for u in Unit.get_units("alive", 0))
    alive1 = sum(1 for u in Unit.get_units("alive", 1))
    if alive0 > 0 and alive1 == 0:
        winner = 0
    elif alive1 > 0 and alive0 == 0:
        winner = 1
    else:
        winner = None  # timeout / draw
    Unit.remove_all()
    return winner, turns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("team0", help="comma-separated class keys, e.g. K,P,K")
    ap.add_argument("team1", help="comma-separated class keys, e.g. T,T,T")
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--board", nargs=2, type=int, default=[10, 6],
                    metavar=("W", "H"))
    ap.add_argument("--max-turns", type=int, default=60)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    team0 = parse_team(args.team0)
    team1 = parse_team(args.team1)

    # Silence FRAY's inline pacing sleeps and (optionally) prints so batch
    # runs are fast and quiet.
    import time as _time
    _orig_print = builtins.print
    _orig_sleep = _time.sleep
    _time.sleep = lambda *a, **k: None
    if not args.verbose:
        builtins.print = lambda *a, **k: None

    t0 = time.time()
    results = {0: 0, 1: 0, None: 0}
    turns_total = 0
    crashes = 0
    for i in range(args.runs):
        try:
            w, turns = run_one(team0, team1, tuple(args.board), args.max_turns)
            results[w] += 1
            turns_total += turns
        except Exception as e:
            crashes += 1
            if args.verbose:
                _orig_print(f"crash on run {i}: {e!r}")
    elapsed = time.time() - t0

    builtins.print = _orig_print
    _time.sleep = _orig_sleep
    print(f"runs: {args.runs} | team0 win: {results[0]} ({100*results[0]/args.runs:.1f}%) "
          f"| team1 win: {results[1]} ({100*results[1]/args.runs:.1f}%) "
          f"| draws: {results[None]} | crashes: {crashes}")
    if args.runs:
        print(f"avg turns/battle: {turns_total/args.runs:.1f} | total elapsed: {elapsed:.2f}s")


if __name__ == "__main__":
    main()
