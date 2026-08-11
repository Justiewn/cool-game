# AI (`ai.py`)

Strategy layer for enemy units when their AI toggle is on. Lives in a separate
module so `Units.py` stays a pure data model and `GUI.py` stays presentation.
No pygame imports — the module can be driven from a script for testing / tuning.

## Files

- **`ai.py`** — the strategy layer. Two public entry points:
  - `choose_action(battle, unit) -> (ability_name, targets_list)` — picks the move for a unit.
  - `choose_next_unit(units, battle) -> Unit` — picks which unit acts next on an AI-controlled team turn.
- **`sim.py`** — headless simulator. See [Simulator](#simulator-simpy).

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
- **Shared helpers** hide the tedious plumbing:
  - `_hp_ratio(u)`, `_has_effect(u, status)`, `_stacks(u, status)`, `_can_afford`, `_has_move`, `_valid_targets`
  - `_min_turns_left(u, status)` — reads `unit.target_Ability_queue` for the min `turns_left` across live effects of a given status. Enables expiry-aware buff refresh instead of "recast whenever the status is present".
  - `_enemies(caster)`, `_allies(caster)`
- **Target scorers**:
  - `_threat_score(u) = 2·ATK + 2·MAGIC + CRIT`
  - `_lowest_hp`, `_highest_threat`, `_priests`, `_priority_target`
  - `_damage_target(caster, name, enemies)` — kill-shot check first (max roll can outright kill, lowest-HP first), else `_priority_target` (lowest-HP alive Priest if any, else highest threat).
- **`_fallback`** — random legal move; used when a class has no strategy or every priority is unaffordable.

## Target scoring

`_damage_target(caster, name, enemies)` returns:
1. an enemy the ability's **maximum roll** can outright kill, lowest HP first
   (guarantees the kill is at least possible on a lucky roll);
2. otherwise `_priority_target(enemies)` — the lowest-HP alive Priest (heal-blocker
   priority), else the highest-`_threat_score` unit.

Buff/debuff strategies pick their own targets directly (biggest threat for
debuffs, self for self-buffs, whole team for team buffs). Berserker's Taunt
selection and Assassin's DEF-sorted targeting also use Priest-first tie-breaking.

## Current strategies

Priorities are checked top-down; the first that fires wins.

| Class     | 1                              | 2                                       | 3                             | 4                                    | 5                    |
|-----------|--------------------------------|-----------------------------------------|-------------------------------|--------------------------------------|----------------------|
| Priest    | Heal wounded (<40% HP)         | Rejuvenation if team avg < 70%          | Bless if no ally has it       | Smite the highest-threat / kill-shot | —                    |
| Knight    | Sword slash for a guaranteed KO | If HP<10, only Sword slash             | Sharpen sword if not SHRPN    | Raise shield if lowest-HP ally & HP<40 | Default Sword slash  |
| Berserker | If HP<10, only Cleave          | Frenzy if not FRENZY                    | Taunt biggest untaunted threat | Cleave (always, if any enemy)        | —                    |
| Assassin  | Guaranteed Stab kill (crit + MARKED backstab bonus) | Shroud if (HP<30 or MP<40%) AND `mp < max_mp` | Priest priority: Mark then Stab, focus one at a time | Setup cycle: Mark → Poison→cap, squishiness order | Shroud stall (gated on `mp < max_mp`), then fallback Stab |
| Thief     | Sneak if not SNEAK             | Distract the tankiest enemy             | Shiv a distracted / kill-shot | —                                    | —                    |
| Thug      | If HP<10, only Punch (no recoil) | Riot until team at cap, then refresh only when `turns_left <= 1` | Rest if HP<40% | Min-Punch KO → Punch, else Tackle (avoid stunned targets unless KO) | Punch fallback |

### Per-class detail

**Assassin** — the most-iterated class:
1. **Guaranteed kill**: any enemy `_stab_max(e) >= e.hp` gets Stabbed. Uses caster ATK + Stab DMG_BASE+ROLL, applies 1.5× crit multiplier as upper bound, adds the MARKED backstab bonus (`floor((max_hp - hp) * 0.2)`) for marked targets. Prefer Priest, then lowest HP.
2. **Shroud** — only if `caster.hp < 30` or `mp < 40% max`, AND `caster.mp < caster.max_mp` (never Shroud at full MP — regen benefit is wasted and it stalls the kill loop).
3. **Priest priority**: if any priest is MARKED, Stab that priest; else Mark the lowest-HP unmarked priest. Never mark a second priest while one is marked.
4. **Setup cycle**: for non-Priest enemies in `sorted(key=e.DEF)` (squishiest first), skip if `hp_ratio <= 0.5` (finisher handles), Mark if unmarked, else Poison to `EFFECT_STACKS` cap. Bails to fallback if it can't afford the current step (doesn't jump ahead).
5. **Shroud stall** (also gated on `mp < max_mp`), then **fallback Stab** (Marked preferred, Priest first on ties by DEF). At full MP the stall is skipped so the AI falls straight to Stab.

**Knight**:
1. Sword slash for a guaranteed KO (max roll can kill).
2. If `caster.hp < 10`, only Sword slash (desperate).
3. Sharpen sword if `SHRPN` not active.
4. Raise shield if `SHLD` not active AND `caster.hp < 40` AND caster is the lowest-HP ally.
5. Default Sword slash via `_damage_target`.

**Berserker**:
1. Desperate at HP<10 → only Cleave.
2. Taunt (team-wide, `_valid_targets`) if not every enemy already has `TAUNT`.
3. Frenzy if not active (fires AFTER Taunt so enemies are already DEF-debuffed).
4. Cleave (team-wide damage).
5. Cleave fallback.

**Thief**: Sneak → Distract (once per target, doesn't stack) → Shiv the focus target. Focus target = squishiest (lowest DEF), Priest first on ties.

**Thug** — desperate HP<10 → only Punch (no recoil). Otherwise:
1. **Riot maintenance**: cast until every ally hits `EFFECT_STACKS` cap, then refresh only when `_min_turns_left(ally, "RIOT") <= 1` (i.e. would expire on the next caster turn after `resolve_before_action` decrements). Without this the AI Riot-spammed every turn instead of attacking; without a cap check, letting the buff lapse dropped every stack on every ally simultaneously (they share `turns_left` via `EFFECT_STACK_RENEWS`).
2. **Rest** if HP<40% (Tackle costs recoil, recover first).
3. **Punch instead of Tackle** if a *min-roll* Punch is a guaranteed KO: `caster.ATK + Punch.DMG_BASE - Punch.DMG_ROLL - target.DEF >= target.hp`. Punch has no recoil, so save the HP cost when the finish is already free.
4. **Tackle** via `_damage_target`, but if the picked target is `STUN`'d and it's *not* a killshot (`caster.ATK + Tackle.DMG_BASE + Tackle.DMG_ROLL - target.DEF >= target.hp` computed inline), re-pick from the non-stunned pool — spreading a new stun is worth more than doubling up.
5. **Punch fallback**.

**Priest**: emergency Heal (single wounded ally <40%) → Rejuvenation (team-wide when avg HP <70%) → Bless upkeep → Smite via `_damage_target` (which prefers enemy Priest).

## Simulator (`sim.py`)

Headless. Reuses `Battle`, `Unit`, `ai.choose_action`, `ai.choose_next_unit`.
Silences `builtins.print` and `time.sleep` for speed (~2 ms/battle).

```bash
py -3.12 sim.py K,P,K A,A,A --runs 500
py -3.12 sim.py K,K,K T,T,T,T,T --runs 500 --top-abilities 15
```

Class keys: `T K P TH B A`. Outputs win rates, avg turns, avg rounds, and the
top-N most-used abilities by frequency.

## Tuning results

| Matchup | Original AI | After tuning |
|---|---|---|
| K,P,K vs A,A,A | 4.6% Assassin win | **43-45% Assassin win** |
| A,A,A vs K,K,K | 20.8% Assassin win | **~68% Assassin win** |
| K,P,K vs B,B,B | 0.4% Berserker win | **~49% Berserker win** (after Frenzy stat retune) |
| K,K,K vs T×5 | 47.4% Thug win | 47-48% Thug win (unchanged, was already balanced) |
| TH,TH,TH vs K,K,K | 6.8% Thief win | ~47% Thief win (mostly from Sneak/Sharpen sword fixes) |

The `EFFECT_TICKS_ON` fix (see mechanics handoff) was the single biggest lever
after AI tuning — it changed Sharpen sword and Sneak behavior significantly.

**Note:** subsequent Thug/Assassin/Tackle-recoil changes (see "Recent changes"
below) layered on top of these results; the table has **not** been re-run since.
Worth doing next `sim.py` exercise.

## Recent changes

- **`_min_turns_left` helper** — reads `unit.target_Ability_queue` for the min `turns_left` across live effects. Enables expiry-aware buff refresh instead of "recast whenever the status is present" (which produced the Thug Riot-spam bug).
- **Thug Riot** now maintains at cap by refreshing only when `turns_left <= 1` — earlier "recast while status active" flavour Riot-spammed forever and never attacked. Verified headlessly: builds to 5 stacks, then alternates Tackle / Riot cleanly.
- **Thug Tackle** avoids stunned targets unless the hit KOs them. Killshot check is computed inline (max-roll `caster.ATK + DMG_BASE + DMG_ROLL - target.DEF >= target.hp`); when the original pick is a stunned non-killshot and any non-stunned enemy exists, re-picks with `_damage_target` restricted to that pool.
- **Thug Punch-over-Tackle**: inserted before the Tackle branch — if min-roll Punch is guaranteed to KO the lowest-HP enemy (`ATK + Punch.DMG_BASE - Punch.DMG_ROLL - e.DEF >= e.hp`), Punch them instead. Saves the Tackle recoil when a free finish exists.
- **Assassin Shroud** — both branches (survival/regen and stall) now require `caster.mp < caster.max_mp`. Full-MP Shrouds no longer stall the setup/finish cycle.

### Mechanics change touching AI expectations

- **Tackle recoil** was rewritten to `floor(raw_damage / 2)` (raw = `caster.ATK + roll`, pre-DEF, pre-crit) instead of `max(3, floor(caster.max_hp * 0.12))`. Recoil now scales with the tackle's own damage roll, not caster max HP or target armour. The `HP<40% → Rest` rule still fits — recoil is variable but roughly the same magnitude for a baseline Thug.

## What's intentionally not here

- **No lookahead / simulation.** Each unit picks locally best; no "if I do X, the priest will heal, then I can Y."
- **No teamwork coordination.** Two Priests may both cast Heal on the same wounded ally in sequence. In practice this over-heals rather than misses.
- **No positioning / range** — the game is targeting-only, so nothing to model.
- **Hand-tuned thresholds.** `<40% HP`, `<55%`, `<70%` are all baked into the strategy functions rather than a config dict.
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

Headless: `sim.py` (see above) — or roll your own by constructing a `Battle`,
spawning units on both teams, looping `choose_action` + `Ability.initial_cast`
until `battle.is_battle_over()`.

## Debugging tips

- Add `if move_name: print(f"{caster.name} -> {move_name}")` at the top of
  `choose_action` for a per-turn action log when running via the GUI.
- The sim silences prints. To debug via sim, temporarily comment out the
  `builtins.print = lambda ...` line in `run_batch`.
- Ability names must exactly match `AbilitiesDict` keys — including spaces
  (`"Sharpen sword"`) and slashes (`"Stab/Backstab"`).

## When to extend

If a strategy misfires on an obvious case (e.g. Priest smites while an ally
is at 5 HP), add a priority *above* the offending one rather than adjusting
the affected step — priorities read as a decision tree, not a mesh.

If you're tempted to duplicate the same scoring code across two class
strategies, promote it to a `_scoring.py` helper first.
