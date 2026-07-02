# AI (`ai.py`)

Strategy layer for enemy units when their AI toggle is on. Lives in a separate
module so `Units.py` stays a pure data model and `GUI.py` stays presentation.
No pygame imports — the module can be driven from a script for testing / tuning.

## Entry point

```python
from ai import choose_action
move_name, targets = choose_action(battle, unit)
```

Returns `(ability_name: str, targets: list[Unit])` ready to feed into
`cast_selected_ability`. Always returns a legal move — falls through to
`"Rest"` on `[caster]` if nothing else is affordable.

`GUI.execute_enemy_ai` is a thin dispatcher that calls this and hands the
result off to the existing cast pipeline.

## Architecture

- **Per-class strategies** in the `_STRATEGIES` dict. Each is a small function
  that inspects the unit and returns the first move whose priority condition
  fires, or `(None, None)` to defer.
- **Shared helpers** (`_can_afford`, `_has_effect`, `_valid_targets`,
  `_enemies`, `_allies`) hide the tedious plumbing.
- **Target scorers** (`_lowest_hp`, `_highest_threat`, `_damage_target`)
  centralise the "who do I hit" logic so class strategies don't reimplement it.
- **`_fallback`** — random legal move; used when a class has no strategy or
  every priority is unaffordable.

## Current strategies

Priorities are checked top-down; the first that fires wins.

| Class     | 1                              | 2                                       | 3                             | 4                                    | 5                    |
|-----------|--------------------------------|-----------------------------------------|-------------------------------|--------------------------------------|----------------------|
| Priest    | Heal wounded (<40% HP)         | Rejuvenation if team avg < 70%          | Bless if no ally has it       | Smite the highest-threat / kill-shot | —                    |
| Knight    | Sword slash for a guaranteed KO | If HP<10, only Sword slash             | Sharpen sword if not SHRPN    | Raise shield if lowest-HP ally & HP<40 | Default Sword slash  |
| Berserker | If HP<10, only Cleave          | Frenzy if not FRENZY                    | Taunt biggest untaunted threat | Cleave (always, if any enemy)        | —                    |
| Assassin  | Shroud if HP<40% or MP<40% and unshrouded | Focus <=50% HP target (prefer MARKED; else squishiest) — Mark then Stab | Setup cycle on healthy targets in squishiness order: Mark → Poison→cap, then move to next | Shroud to stall once all set up | Stab softest (Marked preferred) |
| Thief     | Sneak if not SNEAK             | Distract the tankiest enemy             | Shiv a distracted / kill-shot | —                                    | —                    |
| Thug      | If HP<10, only Punch (no recoil) | Riot until team at RIOT cap           | Rest if HP<40%                | Tackle (primary attack, has recoil)  | Punch fallback       |

## Target scoring

`_damage_target(caster, ability, enemies)` returns:
1. an enemy the ability's **maximum roll** can outright kill, lowest HP first
   (guarantees the kill is at least possible on a lucky roll);
2. otherwise the enemy with the highest `_threat_score` = `2·ATK + 2·MAGIC + CRIT`.

Buff/debuff strategies pick their own targets directly (biggest threat for
debuffs, self for self-buffs, whole team for team buffs).

## What's intentionally not here

- **No lookahead / simulation.** Each unit picks locally best; no "if I do X,
  the priest will heal, then I can Y."
- **No teamwork coordination.** Two Priests may both cast Heal on the same
  wounded ally in sequence. In practice this over-heals rather than misses.
- **No positioning / range** — the game is targeting-only, so nothing to model.
- **Hand-tuned thresholds.** `<40% HP`, `<55%`, `<70%` are all baked into the
  strategy functions rather than a config dict.
- **No difficulty tiers.** All enemies play at "smart" level.

## Next steps

Ordered by effort / return.

1. **Difficulty knob.** Add an `AI_DIFFICULTY` enum passed into `choose_action`.
   `EASY` returns `_fallback` (current dumb AI). `HARD` does what the strategies
   do now. `NORMAL` is somewhere between — e.g. correct target pick 70% of the
   time, else random legal.
2. **Pull thresholds into a config.** Move the `< 0.4`, `< 0.55`, `< 0.7`
   numbers into a per-class dict at the top of the file so tuning doesn't
   require reading each strategy body.
3. **Team-aware Priest.** Track which allies are already scheduled to receive
   a heal this turn (add a per-turn scratch dict) so multiple healers don't
   pile on the same target. Applies more once there's more than one Priest.
4. **Effect-source awareness.** Prefer the strongest available caster for
   team buffs — e.g. if two Thugs can cast Riot this round, only the one
   with the highest ATK should, so stacks don't cap prematurely.
5. **Threat model beyond ATK+MAGIC+CRIT.** Add "expected damage per turn
   against my team" using actual `calculate_dmg` / `calculate_def` values,
   so a high-ATK unit with no matching damage type isn't over-prioritised.
6. **1-ply search.** For each legal (ability, target) pair, simulate the cast
   on a deep-copied `Battle`+`Unit` state, score the resulting state (allies'
   remaining HP × threat − enemies' remaining HP × threat), pick the best.
   Requires `copy.deepcopy` on Battle+Units and a way to disable
   `builtins.print` reroute during simulation. Replaces the strategy functions
   with a generic scorer.
7. **Headless eval harness.** A `python -m ai_bench` script that runs N random
   scenarios with `AI vs AI`, tallies wins per class matchup, and prints a
   table. Makes it possible to tune numbers without eyeballing battles.
8. **Learned weights.** Once (5) and (7) exist, replace the hand-tuned threat
   coefficients with weights fit against the bench (grid search or coordinate
   descent — the state space is small enough).

Steps 1–4 are cheap wins that keep the current architecture. Step 5 onwards
gradually converts the AI to a scorer + search shape, at which point per-class
strategies collapse into "which subset of moves is this class allowed to
score."

## Testing

Manual: turn `Enemy AI: ON` in team select, watch the log. Blocked / dodged
splashes, target picks, and buff-first-then-hit ordering are the most visible
signals that the strategies are firing.

Headless (once a bench exists): construct a `Battle`, spawn units on both
teams, loop `choose_action` + `Ability.initial_cast` until `battle.is_battle_over()`.

## When to extend

If a strategy misfires on an obvious case (e.g. Priest smites while an ally
is at 5 HP), add a priority *above* the offending one rather than adjusting
the affected step — priorities read as a decision tree, not a mesh.

If you're tempted to duplicate the same scoring code across two class
strategies, promote it to a `_scoring.py` helper first.
