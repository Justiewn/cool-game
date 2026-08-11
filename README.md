# FRAY

A turn-based tactical combat prototype in Python + pygame. Two teams of
class-based units trade abilities with status effects, stacks, and
per-turn ticks. Single-machine hotseat or vs a per-class scripted AI.

Prototype lives under `Prototypes/`.

## Run

```bash
python Prototypes/GUI.py
```

Requires Python 3.12+ and `pygame`. A PyInstaller spec (`Prototypes/FRAY.spec`)
is included for producing a standalone build.

## How it plays

1. **Team select screen** — pick a scenario, compose two teams from six classes
   (Knight, Priest, Thief, Berserker, Assassin, Thug), toggle Enemy AI on/off,
   START.
2. **Battle screen** — team-turn model: on your team's turn, freely pick which
   awaiting unit acts next (click a card or press its digit hotkey), choose an
   ability from the fan of buttons, pick a target if needed. When the whole team
   has acted, the other team goes.
3. Battle ends when one team has no units left standing (downed units can be
   revived; permadeath isn't currently triggered by any ability).

**Hotkeys** — `Q W E R T Y` = abilities, `1–5` = unit / target pick,
`ESC` = cancel / pause, `⚙` (top-right) opens settings (fullscreen, FPS,
music/SFX volumes).

## Codebase map

Everything of interest lives in `Prototypes/`. The module split is deliberate:
`battle.py` and `Units.py` stay pygame-free so the AI and headless simulator
can drive them.

| File | Role |
|---|---|
| `GUI.py` | pygame front-end — `GameGUI` class, screens, animations, input, sound. Monolithic but organised. |
| `battle.py` | `Battle` — active-effects list, tick resolvers, downed/dead handling, combat-events queue. |
| `Abilities.py` | `Ability` class — JSON-driven attrs, damage/heal path, per-ability "special" methods. |
| `Units.py` | `Unit` base + per-class subclasses. Class-level team rosters. No pygame. |
| `ai.py` | Per-class scripted strategies. Public entry points: `choose_action`, `choose_next_unit`. |
| `sim.py` | Headless AI-vs-AI batch simulator for balance tuning. |
| `abilities.json` | Declarative ability data. Field-level reference in `abilities_readme.txt`. |
| `images/`, `sounds/` | Assets — portraits, scenario backdrops, cast/hit SFX, BGM. |

## Documentation

Deeper handoff docs for each subsystem live alongside the code:

- **[gui_readme.md](Prototypes/gui_readme.md)** — screens, battle-screen layout, turn/pick state, hotkey routing, animations (fan-out ability buttons, HP splashes, effect pills), settings modal, sound, quirks.
- **[mechanics_readme.md](Prototypes/mechanics_readme.md)** — turn model, effect system (`TICK_OWNER` × `TICK_PHASE`, `EFFECT_TICKS_ON` filter values, `EFFECT_STACK_RENEWS`), stack limits, `remove_effect`, downed vs dead, ghost-caster ticks, ALLY_DEATH passives, special-method conventions.
- **[ai_readme.md](Prototypes/ai_readme.md)** — per-class strategy tables, target scorers, `sim.py` usage, tuning results, deliberate omissions, planned next steps.
- **[abilities_readme.txt](Prototypes/abilities_readme.txt)** — field-by-field reference for `abilities.json`.

## Headless simulator

For AI tuning without the GUI:

```bash
python Prototypes/sim.py K,P,K A,A,A --runs 500
python Prototypes/sim.py K,K,K T,T,T,T,T --runs 500 --top-abilities 15
```

Class keys: `K` Knight, `P` Priest, `TH` Thief, `B` Berserker, `A` Assassin, `T` Thug.
Reports win rate, average turns/rounds, and most-used abilities. ~2 ms/battle.
