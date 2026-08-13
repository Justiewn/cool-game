# FRAY — Hex Prototype

A tactical spatial layer on top of FRAY's combat model: units occupy hexes,
abilities have range and area-of-effect, movement is its own action, and the
AI plans over (destination × ability × target). Reuses FRAY's `Ability`,
`Battle`, `Unit`, and threat-scoring subsystems unchanged.

## Run

```bash
python Prototypes/hex/gui_hex.py
```

Opens on a team-selection screen. Pick classes for both teams, START. The
selection screen recognises class keys `K P TH B A T H SB` (see `hex_unit.py`).

**Selection screen:**
- Left-click a slot: cycle class forward.
- Right-click a slot: cycle class backward.
- `+` adds a slot (up to 5), `×` removes.
- **Enemy AI: ON/OFF** — when OFF the human plays both teams (useful for
  testing).

**Battle screen:**
- Click a highlighted (breathing outline) unit to begin its turn.
- Blue perimeter = movement range. Click a tile inside to move.
- Ability panel on the right — click to arm (gold), click a valid target tile
  (gold) to cast. Right-click / ESC / Cancel button aborts targeting.
- Units auto-end when they've spent both **Move** and **Action**. `End Team
  Turn` (orange when everyone's touched) skips the whole team's remainder.
- ESC in battle opens **Resume / Restart Battle / End Battle / Quit**.

## Directory map

Everything hex-specific lives in `Prototypes/hex/`. FRAY files it reaches into
are noted where they appear.

| File | Role |
|---|---|
| `hex.py` | Axial coord math — neighbours, distance, ring, line, hexes_within, pixel↔axial, BFS reachable, A*. Pure Python, no pygame. |
| `board.py` | `Board(width, height)` — valid tiles, unit placement, blocked-for-unit set, traps dict. |
| `_bootstrap.py` | Puts `Prototypes/` on `sys.path` so hex modules can import FRAY as a library. |
| `hex_unit.py` | Position-aware `Unit` subclasses: `HexKnight`, `HexPriestess`, `HexThief`, `HexBerserker`, `HexAssassin`, `HexThug`, `HexHunter`, `HexSpellblade`. Mixes `hex` position + `MOVE` stat onto each FRAY class. |
| `ability_hex.py` | Spatial targeting: `HEX_CONFIG` per-ability (RANGE + AOE_SHAPE + AOE_RADIUS), valid-target-tile computation, AoE expansion, defensive range gate, Tackle-charge landing, Lay-Trap interception, Focus PRD boost, Arrow distance scaling. |
| `battle_hex.py` | `HexBattle` — team-turn orchestrator, per-unit budgets (`_moved_units` / `_acted_units`), auto-end when both actions spent, PHASE=0 team-turn-start batch ticks, trap-immobilise consumption. |
| `ai_hex.py` | 1-ply search over (dest × ability × target). Reuses FRAY's `ai._threat_score`. Class-specific positional bonuses (Priestess back-rank, Hunter safe-range). |
| `sim_hex.py` | Headless AI-vs-AI runner. `python sim_hex.py K,P,K T,B,T --runs 100`. |
| `gui_hex.py` | Pygame front end. Selection screen, battle board, animations, sound, pause menu. |
| `mechanics_readme.md` | Deeper reference for the spatial mechanics — shape catalogue, trap system, per-unit budgets, Focus, Arcane Shield, Arrow distance scaling. |

## What's reused from FRAY (no changes needed)

- **`Prototypes/battle.py`** — `Battle` class, effect ticks, `remove_effect`, `enforce_stack_limit`, downed/dead handling, ghost-caster ticks, ALLY_DEATH passives.
- **`Prototypes/Abilities.py`** — `calculate_dmg`, `calculate_def`, `ability_dodged`, crit roll (through `prd.roll`), `heal_target`, per-ability special methods, `AbilitiesDict` JSON loader.
- **`Prototypes/Units.py`** — `Unit` base class + per-class kits. Hex adds two new classes here: `Unit_Hunter`, `Unit_Spellblade`.
- **`Prototypes/ai.py`** — `_threat_score`, `_priority_target`, `_lowest_hp`, killshot helpers. Hex's AI wraps these with a positional layer.
- **`Prototypes/prd.py`** — Pseudo-random distribution for CRIT / DODGE / Tackle-stun.

## Shared files hex modifies

| File | Change | Why |
|---|---|---|
| `Prototypes/Abilities.py` | Added `damage_target` shield-absorb branch + `mp_absorbed` combat event. | Arcane Shield needed a hook in the damage path. |
| `Prototypes/Abilities.py` | Added special methods: `ArcaneStrike`, `ManaSap`, `ArcaneShield`. | Spellblade kit. |
| `Prototypes/Units.py` | Added `Unit_Hunter`, `Unit_Spellblade`. | New classes. |
| `Prototypes/abilities.json` | Added `Arrow`, `Lay Trap`, `Focus`, `Arcane Strike`, `Mana Sap`, `Arcane Shield`. | Hunter + Spellblade kits. |

FRAY's own selection/battle screens (`Prototypes/GUI.py`) don't know about
these additions — they'd need `_class_map` entries to be playable in FRAY's
UI, but the hex prototype uses its own selection UI.

## Headless bench

Class keys: `K P TH B A T H SB` — comma-separated per team.

```bash
python Prototypes/hex/sim_hex.py K,P,K T,B,T --runs 100
python Prototypes/hex/sim_hex.py H,H SB,SB --runs 50 --board 10 6
```

Silences `builtins.print` + `time.sleep` for speed (~10 ms/battle). Reports
win rates and average turn count. Add `--verbose` to see the combat log.

## Verification

Every module has a self-check `if __name__ == "__main__":` block. Run in order:

```bash
python Prototypes/hex/hex.py           # coord math
python Prototypes/hex/board.py         # board state
python Prototypes/hex/hex_unit.py      # class mixin
python Prototypes/hex/ability_hex.py   # targeting + AoE + Tackle landing
python Prototypes/hex/battle_hex.py    # turn model
python Prototypes/hex/ai_hex.py        # positional AI
python Prototypes/hex/sim_hex.py K,P,K T,B,T --runs 20   # full-system smoke
python Prototypes/hex/gui_hex.py       # manual playtest
```

If any of these fails, the layer above almost certainly will too — start
debugging at the lowest failing one.
