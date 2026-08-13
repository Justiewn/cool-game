# Hex Mechanics Reference

Everything unique to the spatial layer. FRAY's own mechanics
(`Prototypes/mechanics_readme.md`) still apply — this doc covers what the
hex prototype adds on top.

## Turn model

Team-turn model, same shape as FRAY: PHASE-0 ticks fire once per team at
team-turn start (batched), PHASE-1 ticks fire per-unit at ability-end.
Downed/dead handling, ghost casters, ALLY_DEATH passives — all delegated to
FRAY's `Battle`.

**Per-unit action budget** — each unit gets ONE Move + ONE Ability per team
turn. Tracked on `HexBattle` as two sets keyed by unit reference:

- `self._moved_units` — units that have spent their move this team turn.
- `self._acted_units` — units that have cast this team turn.

Both cleared in `_reset_awaiting` at team-turn start. Switching the current
unit mid-turn doesn't reset either — you can pick freely between awaiting
units without losing anyone's remaining budget.

**Auto-end** — after `perform_move` or `perform_ability`, `_auto_end_if_done`
checks whether the unit is now in both sets. If so, it's removed from
awaiting and `current_unit` clears. When awaiting empties, `_end_team_turn`
cascades. **No End-Unit-Turn button** — that's automatic. The `End Team Turn`
button in the GUI ends the whole team's remainder (skip everyone).

**Trap immobilisation** — units flagged with `_trap_immobilised = True` (set
by `move_unit` when they trigger a hostile trap) get added to `_moved_units`
at the start of their next team turn, then the flag clears. They keep their
action but lose their move for one round.

## Ability spatial config

`HEX_CONFIG` in `ability_hex.py` — every ability the hex layer knows about
has three fields:

- **RANGE** — max hex distance from caster to primary target.
- **AOE_SHAPE** — one of the values below.
- **AOE_RADIUS** — radius parameter for shape (0 = single tile).

### Shape catalogue

| Shape | Auto-fires? | Targets | Affected units |
|---|---|---|---|
| `self` | yes (self-cast) | caster's own tile | `[caster]` |
| `single` | no | one in-range enemy/ally unit | unit on target tile |
| `team` | yes | caster's own tile | every alive ally (or enemy if TARGET_ENEMY) |
| `self_burst` | yes | caster's own tile | every unit of target team within RADIUS of caster |
| `blast` | no | in-range tile | every unit in `hexes_within(target, RADIUS)` |
| `line` | no | in-range tile | every unit in `H.line(caster, target)` |
| `cleave_arc` | no | adjacent tile (any of 6 neighbours) | target + the two neighbours-of-both-caster-and-target |
| `lay_trap` | no | in-range empty tile | none (places trap) |

**Auto-fire** = no target picker; the ability fires immediately when clicked,
aimed at the caster's own hex. `self`, `team`, and `self_burst` all auto-fire.

### Range gate

`cast_ability` refuses when `H.distance(caster, target) > range` (except for
`self`-shape abilities which ignore the check). Also refuses when
`aoe_affected_units` returns empty — so a Cleave-arc into three empty tiles
doesn't burn the action.

### Target-tile computation

`get_valid_target_tiles(caster, ability, board)`:

- `MOVE` — BFS reachable tiles up to `caster.MOVE`, excluding occupied ones.
- `cleave_arc` — the 6 caster-adjacent tiles (any of them, empty or not).
- `lay_trap` — every in-range empty tile with no existing trap.
- Everything else — hexes of valid target units filtered by TARGET_TYPE + TARGET_ENEMY + RANGE.

## Kit-specific mechanics

### Tackle — charge

At range 2, the caster closes to the **gap tile** between them and the target
before hitting. Gap = `H.line(caster, target)[1]`. If the gap is off-board or
occupied, Tackle isn't offered / refuses. Range 1 Tackle stays put. Helper:
`_tackle_landing_hex`.

The charge animates in the GUI via `HexBattle.last_charge_path` — set inside
`perform_ability`, read by `_do_cast` to spin up the movement tween and defer
the hit SFX until the charge visually lands.

### Cleave — 3-hex arc

Not the FRAY hit-all-adjacent behaviour. Cleave targets an adjacent tile
(any of 6, including empty ones so you can sweep between two enemies) and
hits: **target + the two hexes that are neighbours of both caster and
target**. See `cleave_arc_hexes` in `ability_hex.py`.

### Lay Trap

Hex-only ability. FRAY-side is a bare TARGET_TYPE=0 stub that only deducts
MP and logs. `cast_ability` intercepts by name, calls `board.place_trap(tile,
caster.team, damage)`. Trap lives on `board.traps` (dict of hex → {owner_team,
damage, ability}).

**Trigger** — in `move_unit`, walk the A* path hex-by-hex. On any hostile
trap along the way, apply damage via `Ability.damage_target`, consume the
trap, halt movement on that tile, and set `unit._trap_immobilised = True` so
next turn's move budget is pre-spent.

### Focus — guaranteed crit

Self-effect with `EFFECT_STATUS: "FOCUS"`, `EFFECT_VALUES: {CRIT: +100}`,
`TICKS: 1`, `EFFECT_TICKS_ON: 4` (attacking-only) so it decrements on the
next outgoing attack.

Belt-and-braces: `_prime_focus_crit(caster)` in `cast_ability` also bumps
`caster._prd_counters["CRIT"]` to 10 000 whenever FOCUS is present, so the
very first crit roll trips even before the +100 bonus takes effect.

### Arrow — distance damage bonus

+5% base damage per hex of distance past adjacent, capped at +20%. Adjacent
(dist 1) gets **no bonus** — Arrow is punished for being in melee range.

Formula: `bonus = max(0, min(0.2, (dist - 1) * 0.05))`.

Implemented by temporarily bumping `caster._ATK` inside `cast_ability` and
restoring via `try/finally`. Distance is fetched from `H.distance(caster.hex,
target_tile)`.

### Arcane Shield — MP absorption

While `ARCSHLD` is active on the target, `Ability.damage_target` diverts
incoming damage:

1. `reduced = max(1, final_damage // 2)` — 50% reduction.
2. Deduct up to `target.mp` from MP (`absorbed`). Push `{"kind":
   "mp_absorbed", "target": target, "amount": absorbed}` combat event.
3. Any leftover after MP is depleted (`overflow`) falls through to HP.

A hit fully absorbed by MP does **not** fire the BLOCKED event (guarded by
`shield_absorbed_any`) — that would misrepresent an absorbed hit as a
defence-blocked one.

**Duration** — TICKS=2, PHASE=0 (caster team-turn start), OWNER=1. Placed
during the caster's turn; ticks down at the START of their next two team
turns; expires at the start of the third. Covers 2 enemy attack rounds.

### Arcane Strike — hybrid damage

Special method `ArcaneStrike`. Damage = `(ATK - target.DEF) + (MAGIC -
target.MAGIC_DEF) + roll`, each half clamped at 0, then crit-multiplied.
Displayed as MAGIC damage so magic hit tiers fire.

### Mana Sap

Special method `ManaSap`. Drains `4 + randint(0, DMG_ROLL)` MP from the
target, caster gains half. No HP damage. Returns True so the generic damage
path is skipped.

## PRD (pseudo-random distribution)

`prd.py` at the FRAY level. Ramps per-attempt success chance linearly since
last success (`p_n = min(1, n * C)`) so long-run rate matches target but
streaks are compressed. Applies to:

- **CRIT** — every crit roll goes through `prd.roll(caster, "CRIT", ...)`.
- **DODGE** — same for dodges (`target.DODGE`).
- **STUN_TACKLE** — Tackle's 20% stun chance.

Counters live on `unit._prd_counters` (initialised in `Unit.__init__`). Focus
manipulates the CRIT counter directly for its guaranteed-crit contract.

## GUI-side effects that mirror model state

- **Movement animation** — path-based tween through the A* result at 130 ms
  per hex. Board state moves synchronously; only rendering is delayed.
- **Cast nudge** — brief lunge toward target for damage abilities (skipped
  for self-casts and Tackle, which has its own charge).
- **Flinch** — target recoils away from caster on damaging hits.
- **Splashes** — floating numbers above damaged/healed units. Colour by kind:
  red for damage, green for heal, purple `-N MP` for shield absorption, white
  `DODGED` / `BLOCKED` for full misses.
- **Effect pills** — status stacks shown above the portrait, coloured blue
  (buff) or red (debuff) based on the ability's `TARGET_TYPE`/`TARGET_ENEMY`.
- **Reachable region** — blue perimeter outline (not full-fill) so units on
  the tiles remain visible.
- **Breathing outline** — units still in `awaiting` pulse in team colour so
  the player can see who still has actions.

## AI overview

`ai_hex.choose_turn(caster, board)` does a bounded 1-ply search over every
(reachable destination × affordable ability × valid target). See
`_hunter_positional_bonus` and `_positional_bonus` for the class-specific
tuning.

Per-class positional bias:

- **Priestess** — back-rank; +ally-proximity, penalises being <3 from enemies.
- **Hunter** — melee-avoidance penalty (−80 at dist 1, −40 at dist 2 for
  Tackle range, −10 at dist 3) + Arrow-range sweet-spot bonus peaked at
  `HEX_CONFIG['Arrow'][0]`.
- **Everyone else** — small unbounded "close in" gradient (`-nearest * 2`).

Target selection is FRAY-derived (`_threat_score`, killshot detection). Hunter
adds a "prefer the weakest enemy on the entire board" bonus so kills get
finished instead of spread thin.

## Known quirks

- **Sim runtime** was 4 s/battle before the `blast → team` refactor for Riot;
  team-shape abilities used to make `bfs_reachable` walk huge tile sets
  during AI evaluation. Now ~10 ms/battle.
- **Portraits for Hunter and Spellblade** are placeholders (Thief and
  Priestess PNGs). Add `hunter.png` / `spellblade.png` to
  `Prototypes/images/portraits/` and update the mapping in
  `gui_hex.py:_load_portraits` when real art lands.
- **Hex distance and pathing don't know about traps** — a unit's A* path may
  route directly through a known enemy trap because BFS/A* only sees
  occupied tiles as blocked. This is a feature more than a bug (traps should
  be hard to see-and-avoid) but if you want AI to avoid known traps, add
  their tiles to `blocked_for(unit)` for path scoring only.
- **Immobilised units** can still cast — only movement is spent. If you want
  them to be fully skipped, add them to `_acted_units` too in the trap trigger.
