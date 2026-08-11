# GUI Handoff

State of `GUI.py`. Everything runs through the `GameGUI` class — a monolith,
but organised.

## Screens (`self.state`)

- **`'team_select'`** — team composition + scenarios + START button + Enemy AI toggle.
- **`'battle'`** — the actual game.

`draw_selection_screen` and `draw_battle_screen` are the two top-level draw
methods, called from `run()`.

## Battle-screen layout

Vertical **team columns**, not horizontal rows.

Constants (top of `GUI.py`):
```python
BATTLE_COLUMN_W = 280           # card width
BATTLE_COLUMN_PAD = 30          # side padding
ACTION_BTN_W = 210              # ability button width (rect size, not column width)
ACTION_BTN_GAP = 10              # only used now by playfield_w calc for the scenario preview
PLAYER_CARD_X = BATTLE_COLUMN_PAD
ENEMY_CARD_X  = WIDTH - BATTLE_COLUMN_PAD - BATTLE_COLUMN_W
LOG_BOX_W = 620
LOG_BOX_H = 400                 # doubled mid-session
LOG_BOX_MARGIN_BOTTOM = 80      # log sits well clear of the screen edge
LOG_UNHOVERED_ALPHA = 55        # log fades when mouse isn't over it
# Ability button fan (replaces the old vertical stack)
ABILITY_FAN_RADIUS = 200        # distance from card anchor to the middle button
ABILITY_FAN_STEP_DEG = 18       # fixed angular gap between neighbouring fan buttons
ABILITY_FAN_IN_DURATION = 0.25  # fan-out + fade-in from card anchor
ABILITY_FAN_STATE_FADE = 0.2    # alpha lerp when selection state changes
ABILITY_ALPHA_TARGETING = 100   # non-selected buttons dim to this while picking a target
ABILITY_ALPHA_CASTING = 0       # non-selected buttons fully hide once target is committed
# New-message animation:
LOG_SLIDE_DURATION = 0.25       # slide up from below into the bottom row
LOG_FULL_OPACITY_DURATION = 1.0 # hold at 255 alpha this long after arrival
LOG_FADE_DURATION = 0.4         # then lerp from 255 down to panel_alpha
```

Layout:
- **Player team**: left column, stacked top → bottom, cards centred vertically in the playable band above the log via `_column_top_y`.
- **Enemy team**: right column, same rules.
- **Action buttons**: **fan formation** anchored to the near edge midpoint of the acting unit's card (right edge for player, left for enemy). Each button's centre lies on an arc at `ABILITY_FAN_RADIUS` from the anchor at angle `−SPREAD/2 + i·step`; the middle button pokes out furthest, top/bottom tuck back. Built by `build_action_buttons`. See **Ability button fan animation** below for the fan-out + alpha state machine.
- **Battle log**: 620 × 400 box centred toward the bottom (`LOG_BOX_MARGIN_BOTTOM` above the screen edge). Title bar sits at the **bottom** of the panel with the scroll indicator on its right; messages are bottom-anchored above it so short logs leave the *top* of the panel empty and new arrivals appear at the last row directly above the title. Base panel (bg + border + title + scroll indicator) fades to `LOG_UNHOVERED_ALPHA` (55/255 ≈ 22%) when the mouse isn't over it; full opacity when hovered. Message text renders separately with per-entry alpha (see the **Battle log** section below).
- **Background image**: scenario preview shrunk to fit between the two columns.
- **⚙ Settings button**: top-right corner via `_setup_settings_ui`.

`_get_slot_layout(team_size)` computes `(v_spacing, card_w, card_h)` — cards
shrink to fit up to 5 units per column.

## Turn/pick state

- `self.state` — `'team_select'` or `'battle'`.
- `self.current_team` — 0 (player) / 1 (enemy).
- `self.units_awaiting_turn = {0: [...], 1: [...]}` — units yet to act.
- `self.picking_unit` — True while waiting for click / hotkey.
- `self.current_unit` — set on `_begin_unit_turn`.
- `self.selected_ability` — `Ability` instance once player picks an ability.
- `self.available_targets` — populated when the selected ability needs a target picker.

**Switch caster**: while `picking_unit=True` OR while `selected_ability is None` and not action-locked, clicking another awaiting card **or** pressing that card's `1`–`5` hotkey calls `_begin_unit_turn(that_unit)`. This works because PHASE=0 ticks fire at team-turn-start (see mechanics handoff), not on unit pick — switching is free of side effects. Green digit badges stay lit on the **other** awaiting units in this "abilities showing, nothing committed" state so the hotkeys remain discoverable; the currently-selected unit is skipped inside the badge-draw loop (not filtered from the source list) so digit indices stay in lockstep with the KEYDOWN handler's `awaiting[i]` mapping.

**Inter-team pause**: when a team's awaiting list empties, `next_turn()` runs the wrap-up ticks (stun/sleep for incapacitated units, ghost-caster turns, `Unit.process_downed`) inline so their log messages appear immediately, then schedules `TEAM_SWITCH_EVENT = USEREVENT + 6` for 1000 ms and returns. `_start_next_team_turn()` fires on that event, does the actual `current_team` flip, populates the new team's awaiting list, fires `_fire_team_turn_start_ticks`, and calls back into `next_turn`. The handler re-schedules itself in 200 ms increments while `self.paused`, matching the existing `NEXT_TURN_EVENT` pattern. Non-blocking — the log's slide-in and fade animations keep running during the 1 s wait.

## Hotkeys

- `Q W E R T Y` → abilities 1-6 in `self.hotkey_abilities` (order depends on movesList; Rest is at the top by convention when present).
- `1 2 3 4 5` → target selection during target picking, unit picking while `picking_unit`, OR swap caster while the ability list is up (contextual, in that priority: available_targets → picking_unit → current_unit set with no selected_ability). When swapping caster, pressing the current unit's own digit is a no-op — the ability list is left untouched rather than re-initialised.
- `ESC` → close settings → cancel target selection → open pause (in that priority order).

Gate: `is_human_team_turn` = current team is 0 OR AI toggle is off. Enemy team is fully hotkey-controllable when AI toggle is off.

## Animations (per-frame updates in `_update_hp_animations`)

Tracked state:
- `unit_last_hp` — id(unit) → HP at last frame; diff drives splashes/shakes.
- `unit_display_hp`, `unit_display_mp` — lerped animated bar values.
- `hp_splashes` — list of floating damage/heal numbers with spawn time.
- `shake_state` — id(unit) → {spawn_t, duration}; triggered by negative HP delta.
- `nudge_state` — one-shot cast lunge toward centre.
- `awaiting_nudge_pos` — persistent inward offset (eases in when unit is pickable, out when acted).
- `pill_states` — animated pill fade-in/out entries per unit.

Constants:
- `AWAITING_NUDGE_PX = 10`, `AWAITING_NUDGE_RATE = 60.0` px/sec.
- `PILL_FADE_DUR = 0.25` s.

Draw order (bottom to top):
1. Background image
2. Blue "can still move" glow around each awaiting card (`draw_unit_card` prologue, pulses at 1.5 Hz).
3. Unit card fill + border (border colours: BLUE for current unit, GOLD for hover-targets, GREEN for awaiting-when-picking, RED for AI-marked targets).
4. Portrait, HP/MP bars (using display values), effect pills.
5. Under each pill: pulsing "ticks remaining" orbs, one per `max(turns_left)` across active stacks.
6. HP splashes (rising numbers).
7. Target hotkey badges (pulsing gold when picking targets, green when picking a unit — either during `picking_unit`, or while the ability list is up and no ability is committed, so the caster can still be swapped).

## Effect pills

- Rendered via `pill_states` (id(unit) → list of {status, stacks, phase, start_t}).
- **Buff pills = blue** `(60, 110, 180)`, **debuff pills = red** `(170, 60, 60)`, **Downed pill = darker red** `(160, 40, 40)`.
- Classification lookup `self._effect_pill_bg` built once at init from each ability's `TARGET_TYPE` + `TARGET_ENEMY`. Rule: `TARGET_TYPE=0` always classifies as buff (Frenzy has a JSON quirk with `TARGET_ENEMY=true`).
- Under each pill: 3 px inner orb + 4 px outer ring, one per turn remaining, pulsing at ~1.5 Hz.

## Ability button fan animation

`build_action_buttons` stamps each `Button` with two independent animation tracks:

**Position** — `.fan_spawn_t`, `.fan_origin_topleft` (all buttons collapsed at the card's near-edge midpoint), `.fan_target_topleft` (final position on the arc). Every `draw_buttons` frame interpolates `.rect.topleft` from origin → target over `ABILITY_FAN_IN_DURATION` using ease-out cubic, so buttons literally fan outward from the card. Hover and click hit-testing follow the moving rect — clicks made mid-fan land correctly.

**Alpha** — `.state_alpha_start_val`, `.state_alpha_start_t`, `.state_alpha_target`. `_compute_ability_button_alpha` picks the current target each frame:
- Selected button (`button.text == self.selected_ability.ABILITY_NAME`) → **255**.
- Any other button, with `selected_ability` set AND any targeting signal present (`available_targets` for the player, `ai_pending_targets` / `ai_targeted_units` for AI) → **`ABILITY_ALPHA_TARGETING`** (100, dim).
- Any other button, with `selected_ability` set AND no targeting signal (cast has committed — `cast_selected_ability` clears `available_targets`; `AI_CAST_EVENT` clears the AI signals before calling it) → **`ABILITY_ALPHA_CASTING`** (0, hidden).
- No `selected_ability` → **255**.

When the target changes, the helper snapshots the current interpolated alpha as the new tween's start value, so cascading state changes (e.g. targeting → casting before the first tween finished) glide through without snapping.

**Spawn state** — `state_alpha_start_val = 0`, `state_alpha_target = 255`, `state_alpha_start_t = spawn_t`. The initial 0 → 255 tween IS the fade-in. On AI turns, `execute_enemy_ai` fires inside `_begin_unit_turn` before the first draw, so the non-selected buttons never reach 255 — their tween redirects immediately to 100 and they fade in dimmed.

**Blit path** — full-opacity buttons draw directly to `self.screen` via `Button.draw`. Partially transparent buttons render onto a temp `SRCALPHA` surface (with `.rect` temporarily zeroed so the button paints at (0, 0)), then `set_alpha` + blit at the real rect origin. Alpha 0 skips the draw entirely.

## Battle log

`self.message_log` is a list of `(text, arrival_time)` tuples — every read site unpacks. `log(msg)` appends `(msg, time.time())`, trims to the last 50 entries, and advances `log_scroll` toward the bottom. Anything reading the log content directly must destructure the tuple.

Colour segments per line via `_color_log_segments(line, unit_names)`. Regex list `_LOG_PATTERNS` compiled at init:

| Match | Colour | Priority |
|---|---|---|
| Unit names (from live `unit.name` + `Class \| Name`) | Gold | 3 (highest) |
| Ability names (from `Ability.AbilitiesDict.keys()`, longest-first) | Violet | 2 |
| Damage phrases, "is down", "Critical hit", poison lines | Red | 1 |
| Heal phrases | Green | 1 |
| `X (has )?increased` / `+N ATK` | Blue | 1 |
| `X (has )?decreased` / `-N ATK`, "is stunned" | Orange | 1 |

Every char gets a colour + priority; higher priority overrides on overlap. Consecutive same-colour chars get grouped into single `SMALL_FONT.render` blits.

**Two-layer draw** (replaces the old single-surface flatten):

1. **Base panel** — bg + border + title + scroll indicator composed on one SRCALPHA surface, then `set_alpha(255 if hovered else LOG_UNHOVERED_ALPHA)` and blitted. Title sits inside a `title_bar_h = TITLE_FONT.get_linesize() + 8` strip at the *bottom* of the panel (`LOG_BOX_H - title_bar_h`, centred horizontally); scroll indicator is right-aligned inside the same strip.
2. **Messages** — each visible line is rendered to its own SRCALPHA row surface (`row_width × line_height`), gets its own `set_alpha`, and is blitted directly to the screen under a clip rect covering `[log_y + pad, log_y + pad + visible_height]` so the top-most sliding row can't spill over the bottom title bar.

**Bottom-anchor + slide-in.** Content top = `log_y + pad` (10 px). The rank of an entry within `rendered` is `offset_i + (max_lines - len(rendered))`, so the last entry always sits on the bottom row (row `max_lines - 1`) directly above the title bar. Short logs leave empty rows at the *top* of the panel. When the log fills up, top- and bottom-anchor coincide.

When the newest entry's `arrival_time` is less than `LOG_SLIDE_DURATION` old and the last row is visible in the current scroll window, every row shifts down by `(1 - progress) * line_height`; if a message exists just before `start_index`, it's rendered too (at row -1, sliding off the top). Clipping keeps that pre-window row invisible above the content, and the incoming row emerges from behind the title bar.

**Per-message alpha:**
- `age < LOG_FULL_OPACITY_DURATION` → 255
- `age < LOG_FULL_OPACITY_DURATION + LOG_FADE_DURATION` → lerp from 255 to `panel_alpha`
- else → `panel_alpha`

So a fresh entry pops at 255 regardless of hover state, holds for 1 s, then fades over 0.4 s to whatever the panel is currently at (55 unhovered, 255 hovered). The bg/border/title track the panel alpha uniformly via the single `set_alpha` on the base surface.

`MOUSEWHEEL` scrolls the log (`log_scroll`), only when `state == 'battle'`.

## Settings modal

Triggered by ⚙ button (`_setup_settings_ui`). Three tabs:
- **Visual** — Fullscreen toggle, FPS cap toggle (30/60).
- **Audio** — Music/SFX volume sliders (click-drag; volume applied live to `pygame.mixer.music.set_volume` and each loaded `Sound.set_volume`).
- **Quit** — "Quit to Selection" (greyed out on selection screen), "Quit Game".

State: `settings_open`, `settings_tab`, `bgm_volume`, `sfx_volume`, `fps`, `fullscreen`, `_dragging_slider`.

When `settings_open`, mouse clicks are intercepted by the modal (blocks all
game clicks until it's closed).

## Sound

`load_sounds()`:
- Walks `Ability.AbilitiesDict` for `CAST_SOUND`. Each ability's cast sound is loaded to `self.sounds[ability_name]`.
- Loads hit sounds by damage tier + hit type: `hit_sharp_light`, `hit_blunt_heavy`, `hit_magic_no_dmg` etc.
- Special sounds: `miss`, `poison_tick`, `menu_click`.

Volume set on every sound via `SFX slider`. Music volume via `pygame.mixer.music`.

BGM: `play_bgm(folder)` — reads `sounds/bgm/<folder>/`, picks a random track, loops via `MUSIC_END_EVENT`. Uses `self.bgm_volume` (survives across BGM changes — earlier bug where it hard-coded 0.5 is fixed).

## Portraits

`load_unit_portraits()` builds two dicts:
- `self.unit_portraits[className]` — 44 × 44 (battle card avatars).
- `self.unit_portraits_hires[className]` — 256 × 256 (selection-screen icons).

`draw_class_icon` downscales from hi-res for crisp selection UI.

## Buttons

`Button` class (`__init__` params): `rect, text, action, color, hover_color, tooltip, right_text, icon, left_text, image_stacked, icon_left, label_font`.

Render modes:
- **Text-only** — default.
- **Icon-only** — pass `icon` (e.g. ⚙ settings button, ✕ close).
- **`image_stacked=True`** — icon on top, text label beneath (START button).
- **`icon_left=True`** — icon on left, text centred in remaining space (Enemy AI toggle).
- **`left_text` badge** — small dark pill on the left (hotkey `Q`/`W`/etc. indicator on ability buttons).
- **`right_text`** — small text on the right (MP cost on ability buttons).

## Splashes

`hp_splashes`: `{unit, text, color, spawn_t, small=?}`. Lifetime 1 s. Rise 55 px.

Colours: RED for damage, GREEN for heal, `(210, 210, 235)` for "Blocked",
WHITE for "Dodged", `DARK_GREEN = (40, 130, 50)` for Poison ticks.

Small font is used for `Blocked` / `Dodged` (short readable words); regular
`TITLE_FONT` for numeric splashes.

The attribution system: when a poison tick fires, `Ability._combat_events` gets
a `{"kind": "poison_tick", "amount": N}` entry. GUI drains it in
`_update_hp_animations`, spawns a dark-green splash with `-N`, and adds the
amount to an `attributed` dict so the generic HP-delta detector doesn't spawn
a duplicate red splash for the same HP loss.

## Known quirks / gotchas

- `builtins.print` is monkey-patched in `__init__` to also append to
  `self.message_log`. `cleanup()` restores the original before shutdown.
- `time.sleep(0.4)` calls scattered in `Unit.process_downed` and stun-handling
  cause pacing pauses. The sim monkey-patches them out for speed.
- `_column_top_y` uses `LOG_BOX_H` in its available-height math; changing log
  height rebalances how much space the team columns get.
- Card position depends on shake + nudge + awaiting-nudge offsets summed.
  The ability-button fan is anchored to the acting unit's **base** card
  position (before shake/nudge), so a nudged-current unit's buttons stay
  put while the card slides toward centre.
- Effect pill hover (for tooltips) uses `unit_effect_rects` keyed by
  `(unit, display_status)`. If pill positions change, hover tooltips silently
  miss until the next frame rebuild.
