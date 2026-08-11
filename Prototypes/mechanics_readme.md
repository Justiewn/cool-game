# Battle Mechanics

State of the combat + effect systems. Companion to `abilities_readme.txt`
(field-level reference) — this doc explains the runtime model.

## Files
- **`battle.py`** — `Battle` class: `active_effects` list + resolve/trigger methods.
- **`Abilities.py`** — `Ability` class: per-cast object, JSON-driven attrs, per-ability "special" methods for custom mechanics.
- **`Units.py`** — `Unit` base + `Unit_Knight/Priest/Thief/Berserker/Assassin/Thug` subclasses. Class-level team rosters (`team_zero_list`, `team_one_list`, etc.). `Unit.remove_all()` clears between battles.
- **`abilities.json`** — declarative ability data. See `abilities_readme.txt` for field docs.

## Turn model (team-turn, reworked mid-session)

**Old model**: strict sequential turn order — unit 0 team 0 → unit 1 team 0 → ... → unit 0 team 1 → ... with per-unit PHASE=0 ticks.

**New model** (what's in the code now): a team turn during which the human/AI picks the next unit to act from an "awaiting" list, in any order.

State (owned by `GameGUI`):
- `self.units_awaiting_turn = {0: [...], 1: [...]}`
- `self.picking_unit` — True while waiting for a human to click / hotkey a unit
- `self.current_team`, `self.current_unit`

Flow:
1. `start_battle` populates team 0's awaiting (excluding stunned units) and fires `_fire_team_turn_start_ticks(0)`.
2. `next_turn` filters awaiting (drops dead / newly-stunned units), then:
   - **Empty**: batch-ticks stunned units on this team (all four resolve phases), fires ghost-caster ticks for downed units, switches teams, refills awaiting, fires `_fire_team_turn_start_ticks(new_team)`, recurses.
   - **Human team**: sets `picking_unit=True`, clears action buttons, waits for click/hotkey.
   - **AI team**: `ai.choose_next_unit` picks, calls `_begin_unit_turn`.
3. `_begin_unit_turn(unit)`: **no longer fires** `resolve_turn_start`/`resolve_before_action` — those are team-turn-start now. Just handles the incap-skip edge case, builds action buttons, kicks off `execute_enemy_ai` for AI units.
4. `cast_selected_ability` fires PHASE=1 ticks (`resolve_after_action`, `resolve_turn_end`) after the actual cast, same as before.
5. `_complete_current_unit_turn` removes the acted unit from awaiting; `NEXT_TURN_EVENT` calls it then `next_turn`.

Player can switch to another awaiting unit before committing to an ability (click another awaiting card) — PHASE=0 ticks already fired at team-turn-start so switching has no side effects.

## Effect system

Every `IS_EFFECT` ability that lands registers an `Ability` instance in
`battle.active_effects`. Multi-target effects create one instance per target
via the "per-target clones" branch in `initial_cast`.

Each effect instance:
- `caster`, `target_list`, `turns_left`, `sp_val` (dict of applied stat deltas), `_stats_reversed` (guard)
- The **same class** as the ability — same `AttrValDict`, same special methods.

### TICK phases

`EFFECT_TICK_OWNER` + `EFFECT_TICK_PHASE` select which of four resolve methods a per-turn tick fires on:

| OWNER | PHASE | Method | When |
|---|---|---|---|
| 0 | 0 | `resolve_turn_start(target)` | Target's team turn starts |
| 1 | 0 | `resolve_before_action(caster)` | Caster's team turn starts |
| 1 | 1 | `resolve_after_action(caster)` | Caster's action ends |
| 0 | 1 | `resolve_turn_end(target)` | Target's action ends (same-unit only) |

Under the team-turn model, PHASE=0 ticks fire in a **batch at team-turn-start** for the whole team, once per unit. PHASE=1 still fires per-unit at cast time.

### EFFECT_TICKS_ON — fixed mid-session

Filter sets defined at the top of `battle.py`:

```python
_TICKS_ON_TURN_TICK  = (0, 1, 2, 3)   # per-turn ticks
_TICKS_ON_ATTACKED   = (2, 3, 5, 6)   # resolve_on_attacked
_TICKS_ON_ATTACKING  = (1, 3, 4, 6)   # resolve_on_attacking
```

Semantics per value:
- **0** — per turn only
- **1** — per turn OR attacking
- **2** — per turn OR attacked
- **3** — per turn OR attacked OR attacking
- **4** — attacking only
- **5** — attacked only
- **6** — attacked OR attacking (no per-turn)

**Historical note**: previous code hard-coded `(0,1,2)` / `(2,4,5)` / `(1,3,5)`, which broke values 3–6. Fixing this **shifted Sharpen sword** (was TICKS_ON=3, "attacking only" → now decays much faster) and **enabled Sneak** (TICKS_ON=4, was excluded from every resolver → now fires on outgoing attacks). Sharpen sword tuning may need `TICKS_ON=4` to match its "expires on next attack" fantasy.

### Effect application via `initial_cast`

Skeleton (pseudocode):
1. Store `target_list`, `caster`, `self.battle = battle` (last one lets special methods trigger sub-effects like Tackle's Stun).
2. Print `"{caster} used {ability}!"`.
3. For each target: `enforce_stack_limit`, `cast_on_target`, capture `sp_val`, add stack via `target.modify_effect_stack_dict("add", EFFECT_STATUS)`.
4. If `DMG_TYPE in {NORMAL, MAGIC}`: fire `resolve_on_attacking(caster, hit_any)` and `resolve_on_attacked(target, was_hit)` for each target.
5. Deduct MP if `success`.
6. **If `EFFECT_STACK_RENEWS`**: refresh `turns_left` of all existing stacks of this status on each target.
7. Register: multi-target IS_EFFECT → per-target clones (each independent); else register `self`.

### `EFFECT_STACK_RENEWS` (added this session)

Optional bool, default `false`. When `true`, applying a new stack of a
stackable effect resets `turns_left` on **all existing instances** of the same
`EFFECT_STATUS` targeting the current cast's target(s). Bundles the stacks into
one shared expiry instead of staggered ticks.

Currently enabled on **Riot** only. Poison / Uproar-passive still stagger.

### Stack limits (`enforce_stack_limit`)

If `current_stacks >= EFFECT_STACKS`, finds the first matching effect on the
target, force-expires it (`turns_left = 0`, `cast_on_target` to run the
special's remove branch, `remove_effect`). Behaves as "refresh oldest stack"
because `active_effects` is append-ordered.

### `remove_effect` (rebuilt mid-session)

Handles both natural expiry and early termination:
1. Remove from `active_effects` and each target's `target_Ability_queue`.
2. If `EFFECT_VALUES` exists AND `sp_val` is a dict AND `_stats_reversed` is falsy → call `effect.effect_stat_modifier("remove", target)` to reverse stat mods (protects against buffs lingering when caster is downed mid-effect).
3. Call `target.modify_effect_stack_dict("remove", EFFECT_STATUS)` to drop the pill count.

`effect_stat_modifier` sets `_stats_reversed` to True on "remove" and False on
"add", so the guard doesn't double-reverse when natural expiry already did it.

### Downed vs Dead

- `unit.alive == False, unit.dead == False` → **downed** (revivable, 0 HP).
- `unit.alive == False, unit.dead == True` → **permanently dead**.
- Only `Unit.permanently_kill()` sets dead=True. Nothing in-game currently triggers it, so downed = effectively dead for gameplay.

`Battle.handle_unit_downed`:
1. For each effect with the unit as **target**: honour `EFFECT_TARGET_DEATH` (0=remove immediately, 1=persist until permadeath).
2. `remove_caster_effects` — honours `EFFECT_CASTER_DEATH` (0=remove, 1=ghost-tick, 2=immortal).
3. **Fire ALLY_DEATH passives** via `_fire_ally_death_passives`.

### Ghost caster ticks

`resolve_ghost_caster_turns(caster)` — fires `EFFECT_CASTER_DEATH=1` effects for a downed caster once per team round (called from `next_turn` at team-turn-end).

Only fires for TICK_OWNER=1 effects (caster-owned ticks).

### Passives (TRIGGER_ON)

`Unit.passives = []` class attribute. Overridden per class (e.g. `Unit_Thug.passives = ["Uproar"]`).

`Battle._fire_ally_death_passives(fallen_unit)`:
- For each surviving teammate, for each passive name in `.passives`:
  - Look up ability. If `TRIGGER_ON == "ALLY_DEATH"`, cast on that teammate.
  - Push a `{"kind": "cast_sound", "ability": passive_name}` combat event so the GUI plays `CAST_SOUND` (Battle stays pygame-free).

`Uproar` is currently the only ALLY_DEATH passive.

## Special ability methods

Abilities with `IS_SPECIAL: true` invoke a Python method on the `Ability` class named after the ability (title-cased, no spaces, `/` → nothing). E.g. `Stab/Backstab` → `StabBackstab`. Method signature: `(self, target, caster=None)`.

Common pattern for effect-applying specials:
```python
def SomeEffect(self, target, caster=None):
    if self.turns_left == self.AttrValDict["TICKS"]:
        self.effect_stat_modifier("add", target)   # first cast
    elif self.turns_left == 0:
        self.effect_stat_modifier("remove", target) # natural expiry
```

Special methods that also apply sub-effects (e.g. Tackle's stun roll) do it
manually:
```python
stun = Ability("Stun", Ability.ability_ID_counter)
stun.caster = caster; stun.target_list = [target]; stun.turns_left = stun.AttrValDict["TICKS"]
battle.enforce_stack_limit(stun, target)
target.modify_effect_stack_dict("add", "STUN")
battle.register_effect(stun)
```

## Damage flow

`cast_on_target(target, caster)`:
1. Check `ability_dodged` (uses target.DODGE if `CAN_DODGE`).
2. If `IS_SPECIAL`: call special method → sets `success`.
3. If `success is None` AND `DMG_TYPE in {NORMAL, MAGIC}` (generic damage path): compute damage, apply crit (`random() < caster.CRIT/100`, `math.ceil(dmg * 1.5)`), `damage_target(...)`.
4. If `IS_HEAL`: `heal_target(...)`.

Damage-dealing specials (Tackle, StabBackstab) must **`return True`** so the
generic damage block is skipped — otherwise damage lands twice.

### Combat events queue

`Ability._combat_events` — class-level list drained + cleared each frame by the
GUI. Non-HP events pushed by:
- `damage_target` on 0-damage hits (`kind: "blocked"`)
- `ability_dodged` on successful dodge (`kind: "dodged"`)
- Poison ticks (`kind: "poison_tick"`, carries amount for dark-green splash)
- `Battle._fire_ally_death_passives` (`kind: "cast_sound"`, carries ability name)

Battle module has no pygame imports; the GUI drains the queue and renders/plays audio.

## Stun / PREVENTS_ACTION

Effects with `PREVENTS_ACTION: true` (currently just Stun) skip the target's
action. Under the team-turn model:
- Stunned units are **excluded from `units_awaiting_turn`** at team-turn-start
  and filtered on every `next_turn` call (catches mid-round stuns from Tackle).
- Their **full four-phase tick cycle** fires in a **batch at team-turn-end**,
  so the Stun `turns_left` decrements normally without them being pickable.
- If every unit on a team is stunned, awaiting is empty → team-turn-end batch
  fires → switch teams.

## Effects on save / reset

`GameGUI.setup_game`:
- `Unit.remove_all()` (clears the four class-level team lists).
- New `Battle()` instance.
- `Ability._combat_events.clear()`.

`Unit.__init__` re-populates team rosters. Ability class-level state
(`AbilitiesDict`, `ability_ID_counter`) persists — that's fine.

## Known quirks / gotchas

- `Ability.ability_ID_counter` is incremented on every instantiation, including
  the throwaway ones AI uses to look up target lists. Never read anywhere.
- Frenzy has `TARGET_ENEMY: true` even though `TARGET_TYPE: 0` (self). GUI's
  buff/debuff pill classifier explicitly overrides for `TARGET_TYPE=0`.
- `remove_effect` reverses stats twice if you forget the `_stats_reversed`
  guard — don't skip that check when adding new termination paths.
- `enforce_stack_limit` only removes ONE stack per call (breaks on first
  match). If stacks exceed cap by more than 1, only one gets pruned per cast.
