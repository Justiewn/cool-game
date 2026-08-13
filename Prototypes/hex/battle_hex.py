"""Turn orchestrator for the hex prototype.

Team-turn model, same shape as FRAY's GameGUI runtime — but each unit's
turn has two optional actions: Move and Ability. Both can be skipped.

Effect ticks reuse FRAY's Battle: PHASE=0 fires once per team at team-turn
start (batched), PHASE=1 fires per-unit at ability-end. Downed handling,
ghost casters, ALLY_DEATH passives — all delegated.
"""

import _bootstrap  # noqa: F401

from Units import Unit
from battle import Battle
from Abilities import Ability

from ability_hex import cast_ability, move_unit, MOVE, _tackle_landing_hex
import hex as H


class HexBattle:
    """Owns the FRAY Battle + team turn state + per-unit action budget."""

    def __init__(self, board):
        self.board = board
        self.battle = Battle()
        self.current_team = 0
        self.awaiting = {0: [], 1: []}   # units yet to act this team turn
        self.current_unit = None
        # Per-unit action budget for the current TEAM turn. Sets of unit refs
        # that have already spent that action this team turn. Reset only when
        # the team turn ends — so switching context between units mid-turn no
        # longer clobbers who has moved / acted.
        self._moved_units = set()
        self._acted_units = set()
        # After each perform_ability call, holds the caster's involuntary
        # displacement path (currently used by Tackle to close range 2 -> 1).
        # None if no charge happened. GUI reads this to animate the charge.
        self.last_charge_path = None
        self.log = []

    # ─────────────────────── setup ──────────────────────────────────────
    def start(self):
        self._reset_awaiting(0)
        self._fire_team_turn_start_ticks(0)

    def _reset_awaiting(self, team):
        self.awaiting[team] = [u for u in Unit.get_units("alive", team)
                               if "STUN" not in u.effect_stacks_dict]
        # New team turn — clear the per-unit budget so units get fresh
        # move+action allowances.
        self._moved_units.clear()
        self._acted_units.clear()
        # Any unit flagged as trap-immobilised has their move already spent
        # for this turn. Consume the flag so it only affects one turn.
        for u in self.awaiting[team]:
            if getattr(u, "_trap_immobilised", False):
                self._moved_units.add(u)
                u._trap_immobilised = False

    # ─────────────────────── budget queries ──────────────────────────
    @property
    def moved_this_turn(self):
        """True iff the current unit has already spent its move this team turn."""
        return self.current_unit is not None and self.current_unit in self._moved_units

    @property
    def acted_this_turn(self):
        """True iff the current unit has already cast this team turn."""
        return self.current_unit is not None and self.current_unit in self._acted_units

    def has_moved(self, unit):
        return unit in self._moved_units

    def has_acted(self, unit):
        return unit in self._acted_units

    def unit_turn_done(self, unit):
        """A unit is done when it's spent BOTH move and action, or it's no
        longer in awaiting (already removed)."""
        return unit not in self.awaiting.get(self.current_team, []) or (
            unit in self._moved_units and unit in self._acted_units)

    def _fire_team_turn_start_ticks(self, team):
        for u in list(Unit.get_units("alive", team)):
            self.battle.resolve_turn_start(u)
            self.battle.resolve_before_action(u)

    # ─────────────────────── unit turn ─────────────────────────────────
    def begin_unit_turn(self, unit):
        """Set `unit` as the currently-selected unit. Does NOT reset its
        budget — that's per-team-turn now, so switching between awaiting
        units freely doesn't refresh anyone's move/action allowance."""
        self.current_unit = unit

    def perform_move(self, dest):
        """Path the current unit to `dest`. Returns the path or None."""
        if self.current_unit is None or self.current_unit in self._moved_units:
            return None
        path = move_unit(self.current_unit, dest, self.board)
        if path is not None:
            self._moved_units.add(self.current_unit)
            self.log.append(f"{self.current_unit} moves to {dest}.")
            self._auto_end_if_done(self.current_unit)
        return path

    def perform_ability(self, ability_name, target_tile):
        """Cast; runs FRAY's PHASE=1 ticks after. Returns cast success."""
        self.last_charge_path = None
        if self.current_unit is None or self.current_unit in self._acted_units:
            return False
        if ability_name == MOVE:
            return False
        # MP check
        mp = Ability.get_attr(ability_name, "MP_COST") or 0
        if mp > self.current_unit.mp:
            self.log.append(f"{self.current_unit}: not enough MP for {ability_name}.")
            return False
        # Tackle "charge": at range 2, caster closes to the gap tile before
        # hitting. If no legal landing hex exists (gap off-board or blocked)
        # the cast isn't allowed at all — refuse without consuming the action.
        if ability_name == "Tackle" \
                and self.current_unit.hex is not None \
                and target_tile is not None:
            landing = _tackle_landing_hex(self.current_unit.hex, target_tile, self.board)
            if landing is None:
                self.log.append(
                    f"{self.current_unit}: no clear path to Tackle {target_tile}.")
                return False
            if landing != self.current_unit.hex:
                caster_hex = self.current_unit.hex
                self.board.move(self.current_unit, landing)
                self.last_charge_path = [caster_hex, landing]
        result = cast_ability(self.current_unit, ability_name, target_tile,
                              self.board, self.battle)
        if result is None:
            # Out of range / no valid AoE targets — don't burn the action.
            return False
        self.battle.resolve_after_action(self.current_unit)
        self.battle.resolve_turn_end(self.current_unit)
        Unit.process_downed(self.battle)
        # Remove downed units from board
        for u in list(self.board.occupied()):
            unit = self.board.unit_at(u)
            if unit is not None and not unit.alive:
                self.board.remove(unit)
        self._acted_units.add(self.current_unit)
        self._auto_end_if_done(self.current_unit)
        return True

    def _auto_end_if_done(self, unit):
        """If `unit` has spent both actions, remove it from awaiting so it
        stops showing as a pickable candidate. Callers no longer need to
        press an End Turn button per-unit."""
        if unit in self._moved_units and unit in self._acted_units:
            if unit in self.awaiting[self.current_team]:
                self.awaiting[self.current_team].remove(unit)
            if self.current_unit is unit:
                self.current_unit = None
            self._filter_awaiting()
            if not self.awaiting[self.current_team]:
                self._end_team_turn()

    def _filter_awaiting(self):
        self.awaiting[self.current_team] = [
            u for u in self.awaiting[self.current_team]
            if u.alive and "STUN" not in u.effect_stacks_dict
        ]

    def end_unit_turn(self):
        """Manually remove the current unit from awaiting (used by the AI to
        cycle through its units). For humans, units auto-end via
        `_auto_end_if_done`, and the UI's End-Turn button ends the whole
        team turn via `end_team_turn`."""
        if self.current_unit in self.awaiting[self.current_team]:
            self.awaiting[self.current_team].remove(self.current_unit)
        self.current_unit = None
        self._filter_awaiting()
        if not self.awaiting[self.current_team]:
            self._end_team_turn()

    def end_team_turn(self):
        """Skip the whole team's remaining units and hand off to the other
        team. Also runs the team-end tick batch that _end_team_turn does."""
        self.awaiting[self.current_team] = []
        self.current_unit = None
        self._end_team_turn()

    def _end_team_turn(self):
        # Batch-tick stunned units on this team.
        for u in Unit.get_units("alive", self.current_team):
            if "STUN" in u.effect_stacks_dict:
                self.battle.resolve_turn_start(u)
                self.battle.resolve_before_action(u)
                self.battle.resolve_after_action(u)
                self.battle.resolve_turn_end(u)
        # Ghost-caster ticks for downed
        for team in (0, 1):
            for u in Unit.get_units("all", team):
                if u.downed:
                    self.battle.resolve_ghost_caster_turns(u)
        # Switch teams
        self.current_team = 1 - self.current_team
        self._reset_awaiting(self.current_team)
        self._fire_team_turn_start_ticks(self.current_team)

    def is_over(self):
        return self.battle.is_battle_over()


if __name__ == "__main__":
    from Units import Unit
    from board import Board
    from hex_unit import HexKnight, HexThug

    Unit.remove_all()
    b = Board(6, 6)
    hb = HexBattle(b)
    k = HexKnight("Aldric", 0)
    t = HexThug("Brutus", 1)
    b.place(k, (0, 0))
    b.place(t, (5, 0))
    hb.start()
    assert hb.current_team == 0
    assert k in hb.awaiting[0] and t not in hb.awaiting[0]
    hb.begin_unit_turn(k)
    assert hb.perform_move((2, 0)) is not None
    assert k.hex == (2, 0)
    # Ability out of range no-ops (defensive range check inside cast_ability)
    ok = hb.perform_ability("Sword slash", (5, 0))
    assert not ok  # target out of range
    hb.end_unit_turn()
    assert hb.current_team == 1  # switched — was only unit
    Unit.remove_all()
    print("battle_hex.py self-check OK")
