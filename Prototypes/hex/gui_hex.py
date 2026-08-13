"""Minimum-viable pygame front end for the hex prototype.

Scope: playable end-to-end loop — team-turn, click-to-move, click-to-cast,
AI opponent, battle log, win detection. Reuses FRAY's damage/effects
untouched.

Deferred vs the FRAY GUI (intentionally, to keep this bounded):
    - team-select screen (starter roster hard-coded below)
    - effect pills / stack orbs (hover tooltip shows HP/MP only)
    - HP splash animations, card shake, ability fan-out
    - BGM music (SFX is wired up)
    - settings modal

Run:  python gui_hex.py
"""

import _bootstrap  # noqa: F401

import os
import sys
import pygame

from Units import Unit
from Abilities import Ability
from board import Board
from hex_unit import HEX_CLASS_MAP
from battle_hex import HexBattle
from ability_hex import (
    get_valid_target_tiles, aoe_affected_units, get_config, MOVE,
    cleave_arc_hexes,
)
from ai_hex import choose_turn
import hex as H


# ─────────────────────────────── config ───────────────────────────────────
# Detect the primary display size on import so the window opens near-fullscreen.
# We leave a small margin so the OS title bar / taskbar remains visible; if
# pygame can't query yet (very rare), fall back to a large fixed size.
def _default_window_size():
    try:
        pygame.display.init()
        info = pygame.display.Info()
        w = max(1280, info.current_w - 80)
        h = max(720,  info.current_h - 120)
        return w, h
    except Exception:
        return 1600, 900


WIDTH, HEIGHT = _default_window_size()
FPS = 60
HEX_SIZE = 56                 # centre-to-corner in pixels
BOARD_ORIGIN = (240, 140)
BOARD_W, BOARD_H = 10, 7

# Movement animation.
MOVE_STEP_MS = 130   # per-hex travel time; total = MOVE_STEP_MS * (len(path)-1)
# Cast-nudge animation — brief lunge toward target when firing an ability.
NUDGE_DUR_MS = 260
NUDGE_MAX_PX = 12
# Flinch animation — target's recoil away from the caster on a damaging hit.
FLINCH_DUR_MS = 300
FLINCH_MAX_PX = 14
# Damage splash — floating "-N" number above a damaged unit, rises and fades.
SPLASH_DUR_MS = 900
SPLASH_RISE_PX = 40
# Effect pill colours (matches FRAY's classification).
PILL_BUFF   = (60, 110, 180)
PILL_DEBUFF = (170, 60, 60)

# Hit-sound damage tiers (same thresholds as FRAY).
HIT_DMG_LIGHT  = 14
HIT_DMG_MEDIUM = 26

# AI pacing (ms) — enforces breathing room between phases so a full unit
# turn doesn't blur into one frame.
AI_DELAY_START     = 250   # after picking a unit, before it moves
AI_DELAY_POST_MOVE = 450   # after a move completes, before the cast
AI_DELAY_POST_CAST = 750   # after a cast lands, before end-turn
AI_DELAY_END       = 250   # after end-turn, before the next unit begins

BG           = (18, 22, 30)
TILE_FILL    = (46, 54, 68)
TILE_BORDER  = (28, 32, 44)
TILE_REACH   = (60, 140, 220)
TILE_AOE     = (220, 90, 90)
TILE_TARGET  = (240, 200, 80)
TEAM0_COL    = (90, 160, 240)
TEAM1_COL    = (220, 120, 120)
CURRENT_COL  = (255, 220, 80)
TEXT         = (230, 232, 240)
DIM_TEXT     = (150, 155, 170)
PANEL        = (32, 36, 48)
PANEL_BORDER = (60, 66, 82)
BTN_FILL       = (72, 82, 100)
BTN_HOVER      = (100, 112, 130)
BTN_DISABLED   = (50, 54, 66)
# Ability button states.
ABIL_READY_FILL  = (75, 130, 200)     # light blue — usable this turn
ABIL_READY_HOVER = (105, 165, 235)
ABIL_SELECTED    = (200, 165, 70)     # gold — currently picked, awaiting target
# End Turn goes orange once both Move and Action are spent.
END_TURN_READY_FILL  = (215, 130, 50)
END_TURN_READY_HOVER = (240, 155, 75)
LOG_BG       = (24, 28, 38)


# ────────────────────────────── scenario ──────────────────────────────────
# Starter roster — override by editing.
TEAM0 = ["K", "P", "TH"]
TEAM1 = ["T", "B", "T"]


def _resource_path(relative):
    """Same helper FRAY uses for PyInstaller-safe asset paths."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", relative)


class HexGUI:
    def __init__(self):
        pygame.init()
        pygame.mixer.init()
        pygame.display.set_caption("FRAY — Hex Prototype")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("segoe ui", 16)
        self.small = pygame.font.SysFont("segoe ui", 12)
        self.title_font = pygame.font.SysFont("segoe ui", 22, bold=True)
        self.portraits = self._load_portraits()
        self.team_icon = self._load_team_icon()
        self._diagram_cache = {}
        self.sounds = {}
        self._load_sounds()
        # status -> pill background colour (buff blue / debuff red).
        # status -> effect tooltip string. Both derived once at init.
        self._effect_pill_bg, self._effect_tooltip_map = self._build_effect_tables()

        # Top-level state: "select" (team selection screen) or "battle".
        self.state = "select"
        # Pause menu overlay during battle. When True, board input + AI pump
        # freeze and only the pause-menu buttons respond.
        self._paused = False
        self._pause_buttons = []      # populated by _draw_pause_menu
        self._quit_requested = False  # set by pause-menu Quit; run() honours it
        self.player_team = list(TEAM0)   # mutable copies driven by selection UI
        self.enemy_team = list(TEAM1)
        self.enemy_ai_enabled = True
        # Selection screen also uses action_buttons for hit-testing (same
        # (rect, kind, payload) tuple format as battle mode).
        self.action_buttons = []

        # Interaction state (battle mode).
        self.board = None
        self.hb = None
        self.mode = "pick_unit"    # "pick_unit" | "act" | "target" | "ai" | "over"
        self.selected_ability = None
        self.reachable = set()     # tiles shown in blue during Move highlight
        self.valid_targets = set() # tiles shown in gold during Target picking
        self.hover_hex = None
        self.message_log = []
        # Snapshots for hit-sound detection: id(unit) -> last-seen hp.
        self._last_hp = {}
        # AI action queue: list of (fire_at_ms, callable). Each callback runs
        # once, may enqueue follow-ups. Empty during human turns.
        self._ai_queue = []
        # Movement animation state: {unit, path: [hex,...], start_ms, total_ms}
        # or None. Board state moves synchronously; this only tweens rendering.
        # AI pump blocks and human input is refused while it's non-None.
        self._active_anim = None
        # Optional callback fired once when the current animation completes.
        # Used to defer hit SFX until a Tackle charge visually connects.
        self._after_anim_cb = None
        # Per-unit cast nudges: id(unit) -> {start_ms, dx, dy}. Non-blocking —
        # doesn't gate AI/input, purely a lunge visual on top of position.
        self._nudges = {}
        # Per-unit flinches (target recoil on hit): id(unit) -> {start_ms, dx, dy}.
        self._flinches = {}
        # Floating damage-splash numbers: list of {unit, amount, start_ms}.
        self._splashes = []
        # Ability button currently under the mouse — used by _draw_board to
        # preview team-shape AoE without needing a target-select mode.
        self._hover_ability_name = None
        # Selection screen doesn't need battle state — that's set up when the
        # user clicks START via _start_battle().

    # ─────────────────────── setup ─────────────────────────────────────
    def _start_battle(self):
        """Called from the selection screen — spins up board + battle state
        using the currently selected teams and flips into 'battle' mode."""
        self.board = Board(BOARD_W, BOARD_H)
        self.hb = HexBattle(self.board)
        self._setup_scenario()
        self.hb.start()
        self.mode = "pick_unit"
        self.selected_ability = None
        self.reachable = set()
        self.valid_targets = set()
        self.message_log = []
        self._last_hp = {id(u): u.hp
                         for u in Unit.get_units("alive", 0) + Unit.get_units("alive", 1)}
        self._ai_queue = []
        self._active_anim = None
        self._after_anim_cb = None
        self._nudges = {}
        self._flinches = {}
        self._splashes = []
        self._log("Battle begin — team 0's turn.")
        self.state = "battle"
        self._begin_turn_flow()

    def _setup_scenario(self):
        Unit.remove_all()
        for i, key in enumerate(self.player_team):
            cls = HEX_CLASS_MAP[key]
            name = cls.name_pool[i % len(cls.name_pool)]
            u = cls(name, 0)
            self.board.place(u, (0, i + 1))
        for i, key in enumerate(self.enemy_team):
            cls = HEX_CLASS_MAP[key]
            name = cls.name_pool[i % len(cls.name_pool)]
            u = cls(name, 1)
            self.board.place(u, (BOARD_W - 2 - (i // 2), i + 1))

    def _load_sounds(self):
        """Cast sounds per ability + hit tiers + miss + poison_tick. Same
        naming convention as FRAY so we share the sounds/effects/ folder."""
        sounds_dir = _resource_path(os.path.join("sounds", "effects"))
        for name, attrs in Ability.AbilitiesDict.items():
            cs = attrs.get("CAST_SOUND") if isinstance(attrs, dict) else None
            if not cs:
                continue
            try:
                self.sounds[name] = pygame.mixer.Sound(os.path.join(sounds_dir, cs))
            except Exception:
                pass
        tiered = [
            ("hit_sharp_no_dmg", "hit_sharp_no_dmg.mp3"),
            ("hit_sharp_light", "hit_sharp_light.mp3"),
            ("hit_sharp_medium", "hit_sharp_medium.mp3"),
            ("hit_sharp_heavy", "hit_sharp_heavy.mp3"),
            ("hit_blunt_no_dmg", "hit_blunt_no_dmg.mp3"),
            ("hit_blunt_light", "hit_blunt_light.mp3"),
            ("hit_blunt_medium", "hit_blunt_medium.mp3"),
            ("hit_blunt_heavy", "hit_blunt_heavy.mp3"),
            ("hit_magic_no_dmg", "hit_magic_no_dmg.mp3"),
            ("hit_magic_light", "hit_magic_light.mp3"),
            ("hit_magic_medium", "hit_magic_medium.mp3"),
            ("hit_magic_heavy", "hit_magic_heavy.mp3"),
            ("miss", "miss.wav"),
            ("poison_tick", "poison_tick.mp3"),
        ]
        for key, fn in tiered:
            try:
                self.sounds[key] = pygame.mixer.Sound(os.path.join(sounds_dir, fn))
            except Exception:
                pass
        # menu_click lives one directory up in FRAY's layout.
        try:
            self.sounds["menu_click"] = pygame.mixer.Sound(
                _resource_path(os.path.join("sounds", "menu_click.mp3")))
        except Exception:
            pass

    def _play(self, key):
        s = self.sounds.get(key)
        if s is not None:
            try:
                s.play()
            except Exception:
                pass

    def _hp_snapshot(self):
        return {id(u): u.hp for u in Unit.get_units("alive", 0) + Unit.get_units("alive", 1)}

    def _play_hit_sounds_for_delta(self, before, after, ability_name):
        """Compare HP before/after a cast and play the appropriate hit tier
        for the biggest damaged unit. Poison ticks come through the combat
        events queue instead (see _drain_combat_events)."""
        attrs = Ability.AbilitiesDict.get(ability_name, {})
        dmg_type = attrs.get("DMG_TYPE")
        hit_type = (attrs.get("HIT_TYPE") or "blunt").lower()
        if not dmg_type:
            return
        max_dmg = 0
        for uid, hp_before in before.items():
            hp_after = after.get(uid, hp_before)
            dmg = hp_before - hp_after
            if dmg > max_dmg:
                max_dmg = dmg
        if max_dmg <= 0:
            tier = "no_dmg"
        elif max_dmg <= HIT_DMG_LIGHT:
            tier = "light"
        elif max_dmg <= HIT_DMG_MEDIUM:
            tier = "medium"
        else:
            tier = "heavy"
        key = f"hit_magic_{tier}" if dmg_type == "MAGIC" else f"hit_{hit_type}_{tier}"
        self._play(key)

    def _drain_combat_events(self):
        """Pull non-HP events pushed by battle/Abilities — poison ticks, misses,
        passive cast sounds, blocks — and play/animate the matching SFX. Same
        drain contract FRAY uses (Ability._combat_events is a class-level queue)."""
        now = pygame.time.get_ticks()
        for evt in Ability._combat_events:
            kind = evt.get("kind")
            if kind == "cast_sound":
                self._play(evt.get("ability"))
            elif kind == "poison_tick":
                self._play("poison_tick")
            elif kind == "dodged":
                self._play("miss")
                tgt = evt.get("target")
                if tgt is not None and getattr(tgt, "hex", None) is not None:
                    self._splashes.append({"unit": tgt, "text": "DODGED",
                                           "kind": "miss", "start_ms": now})
            elif kind == "blocked":
                tgt = evt.get("target")
                if tgt is not None and getattr(tgt, "hex", None) is not None:
                    self._splashes.append({"unit": tgt, "text": "BLOCKED",
                                           "kind": "miss", "start_ms": now})
            elif kind == "mp_absorbed":
                tgt = evt.get("target")
                amt = evt.get("amount", 0)
                if tgt is not None and getattr(tgt, "hex", None) is not None and amt > 0:
                    self._splashes.append({"unit": tgt, "amount": amt,
                                           "kind": "mp_loss", "start_ms": now})
        Ability._combat_events.clear()

    def _do_move(self, dest):
        """Wraps HexBattle.perform_move with a visual tween. Board state
        updates immediately (path resolves synchronously); the animation is
        purely visual and blocks subsequent input/AI steps until it ends.
        Returns the path used, or None if the move was rejected."""
        unit = self.hb.current_unit
        if unit is None:
            return None
        src = unit.hex
        path = self.hb.perform_move(dest)  # may return None if rejected
        if path is None or len(path) < 2:
            return path
        # perform_move already applied board.move — path[0] is `src`.
        self._active_anim = {
            "unit": unit,
            "path": list(path),
            "start_ms": pygame.time.get_ticks(),
            "total_ms": MOVE_STEP_MS * (len(path) - 1),
        }
        return path

    def _anim_pixel_for(self, unit):
        """If `unit` is currently being animated, return its interpolated
        pixel position; else None (caller should use board-hex pixel)."""
        anim = self._active_anim
        if anim is None or anim["unit"] is not unit:
            return None
        elapsed = pygame.time.get_ticks() - anim["start_ms"]
        total = max(1, anim["total_ms"])
        t = max(0.0, min(1.0, elapsed / total))
        path = anim["path"]
        # Segment index: 0..len(path)-2. Each segment covers 1/(n-1) of t.
        n_segs = len(path) - 1
        seg_span = 1.0 / n_segs
        seg_i = min(int(t / seg_span), n_segs - 1)
        seg_t = (t - seg_i * seg_span) / seg_span
        a = self._hex_center(path[seg_i])
        b = self._hex_center(path[seg_i + 1])
        return (a[0] + (b[0] - a[0]) * seg_t,
                a[1] + (b[1] - a[1]) * seg_t)

    def _update_animation(self):
        if self._active_anim is None:
            return
        elapsed = pygame.time.get_ticks() - self._active_anim["start_ms"]
        if elapsed >= self._active_anim["total_ms"]:
            self._active_anim = None
            cb = self._after_anim_cb
            self._after_anim_cb = None
            if cb is not None:
                cb()

    def _trigger_cast_nudge(self, caster, target_tile, ability_name):
        """Kick off a brief lunge toward `target_tile`. Skips self-casts and
        Tackle (which has its own charge animation)."""
        if caster is None or caster.hex is None or target_tile is None:
            return
        if ability_name == "Tackle":
            return
        _, shape, _ = get_config(ability_name)
        if shape == "self" or target_tile == caster.hex:
            return
        src = self._hex_center(caster.hex)
        dst = self._hex_center(target_tile)
        vx, vy = dst[0] - src[0], dst[1] - src[1]
        mag = (vx * vx + vy * vy) ** 0.5
        if mag <= 0:
            return
        vx, vy = vx / mag, vy / mag
        self._nudges[id(caster)] = {
            "start_ms": pygame.time.get_ticks(),
            "dx": vx * NUDGE_MAX_PX,
            "dy": vy * NUDGE_MAX_PX,
        }

    def _trigger_flinch_and_splash(self, caster, before, after):
        """For each unit whose HP changed: spawn a floating number (red for
        damage taken, green for heal received) and — only for damage —
        kick a brief flinch away from the caster."""
        c_pixel = self._hex_center(caster.hex) if caster and caster.hex else None
        for uid, hp_before in before.items():
            hp_after = after.get(uid, hp_before)
            delta = hp_after - hp_before   # positive = heal, negative = damage
            if delta == 0:
                continue
            # Look up the unit by id — walk both team lists.
            hit_unit = None
            for team in (0, 1):
                for u in Unit.get_units("all", team):
                    if id(u) == uid:
                        hit_unit = u
                        break
                if hit_unit is not None:
                    break
            if hit_unit is None or hit_unit.hex is None:
                continue
            if delta < 0:
                # Damage — flinch away from caster (if we know their position).
                if c_pixel is not None:
                    u_pixel = self._hex_center(hit_unit.hex)
                    vx, vy = u_pixel[0] - c_pixel[0], u_pixel[1] - c_pixel[1]
                    mag = (vx * vx + vy * vy) ** 0.5
                    if mag > 0:
                        vx, vy = vx / mag, vy / mag
                        self._flinches[id(hit_unit)] = {
                            "start_ms": pygame.time.get_ticks(),
                            "dx": vx * FLINCH_MAX_PX,
                            "dy": vy * FLINCH_MAX_PX,
                        }
                self._splashes.append({
                    "unit": hit_unit,
                    "amount": -delta,
                    "kind": "damage",
                    "start_ms": pygame.time.get_ticks(),
                })
            else:
                self._splashes.append({
                    "unit": hit_unit,
                    "amount": delta,
                    "kind": "heal",
                    "start_ms": pygame.time.get_ticks(),
                })

    def _flinch_offset_for(self, unit):
        """Current recoil offset for `unit`, or (0, 0). Sinusoidal push-out
        followed by ease-back, matching the shape of the caster nudge."""
        f = self._flinches.get(id(unit))
        if f is None:
            return (0, 0)
        elapsed = pygame.time.get_ticks() - f["start_ms"]
        if elapsed >= FLINCH_DUR_MS:
            del self._flinches[id(unit)]
            return (0, 0)
        import math
        t = elapsed / FLINCH_DUR_MS
        k = math.sin(math.pi * t)
        return (f["dx"] * k, f["dy"] * k)

    def _draw_splashes(self):
        """Render floating damage numbers on top of everything else. Splashes
        rise `SPLASH_RISE_PX` and fade linearly over `SPLASH_DUR_MS`."""
        now = pygame.time.get_ticks()
        alive = []
        for s in self._splashes:
            elapsed = now - s["start_ms"]
            if elapsed >= SPLASH_DUR_MS:
                continue
            alive.append(s)
            unit = s["unit"]
            if unit.hex is None:
                continue
            cx, cy = self._hex_center(unit.hex)
            t = elapsed / SPLASH_DUR_MS
            y = cy - HEX_SIZE + 8 - t * SPLASH_RISE_PX
            alpha = int(255 * (1 - t))
            kind = s.get("kind")
            if kind == "miss":
                # "DODGED" / "BLOCKED" — plain white label, use the small font
                # so long words don't overrun the tile.
                colour = (245, 245, 245)
                txt = self.font.render(s.get("text", ""), True, colour)
            elif kind == "mp_loss":
                # Purple splash for MP absorbed by Arcane Shield.
                colour = (180, 100, 220)
                txt = self.title_font.render(f"-{s['amount']} MP", True, colour)
            else:
                if kind == "heal":
                    colour, sign = (90, 220, 100), "+"
                else:
                    colour, sign = (240, 90, 90), "-"
                txt = self.title_font.render(f"{sign}{s['amount']}", True, colour)
            txt.set_alpha(alpha)
            self.screen.blit(txt, txt.get_rect(center=(int(cx), int(y))))
        self._splashes = alive

    def _nudge_offset_for(self, unit):
        """Current (dx, dy) offset for `unit`'s cast lunge, or (0, 0)."""
        n = self._nudges.get(id(unit))
        if n is None:
            return (0, 0)
        elapsed = pygame.time.get_ticks() - n["start_ms"]
        if elapsed >= NUDGE_DUR_MS:
            del self._nudges[id(unit)]
            return (0, 0)
        # Sinusoidal: peaks at t=0.5, back to 0 at t=1. Fast lunge + return.
        import math
        t = elapsed / NUDGE_DUR_MS
        k = math.sin(math.pi * t)
        return (n["dx"] * k, n["dy"] * k)

    def _do_cast(self, ability_name, target_tile):
        """Wraps HexBattle.perform_ability with cast SFX + hit SFX. Returns
        the ok flag from perform_ability."""
        before = self._hp_snapshot()
        self._play(ability_name)  # cast sound (may be missing for some abilities)
        caster_before = self.hb.current_unit
        self._trigger_cast_nudge(caster_before, target_tile, ability_name)
        ok = self.hb.perform_ability(ability_name, target_tile)
        if not ok:
            return ok
        # Tackle (or any future ability) may have moved the caster to close
        # range. If so, run the charge animation and defer the hit SFX +
        # combat-event drain until the visual charge lands.
        charge_path = self.hb.last_charge_path
        after = self._hp_snapshot()
        if charge_path and len(charge_path) >= 2:
            caster = self.hb.current_unit
            if caster is not None:
                self._active_anim = {
                    "unit": caster,
                    "path": list(charge_path),
                    "start_ms": pygame.time.get_ticks(),
                    "total_ms": MOVE_STEP_MS * (len(charge_path) - 1),
                }
                self._after_anim_cb = lambda b=before, a=after, n=ability_name, c=caster: (
                    self._play_hit_sounds_for_delta(b, a, n),
                    self._trigger_flinch_and_splash(c, b, a),
                    self._drain_combat_events(),
                )
                return ok
        self._play_hit_sounds_for_delta(before, after, ability_name)
        self._trigger_flinch_and_splash(self.hb.current_unit, before, after)
        self._drain_combat_events()
        return ok

    def _build_effect_tables(self):
        """Classify each EFFECT_STATUS as buff/debuff and remember its tooltip.
        Rule (same as FRAY): TARGET_TYPE 0 (self) is a buff; otherwise the
        pill colour follows TARGET_ENEMY (True = debuff, False = buff)."""
        pill_bg = {}
        tips = {}
        for name, attrs in Ability.AbilitiesDict.items():
            if not isinstance(attrs, dict):
                continue
            status = attrs.get("EFFECT_STATUS")
            if not status:
                continue
            if attrs.get("TARGET_TYPE") == 0:
                pill_bg[status] = PILL_BUFF
            elif attrs.get("TARGET_ENEMY"):
                pill_bg[status] = PILL_DEBUFF
            else:
                pill_bg[status] = PILL_BUFF
            tip = attrs.get("EFFECT_TOOLTIP")
            if tip and status not in tips:
                tips[status] = tip
        return pill_bg, tips

    def _load_team_icon(self):
        p = _resource_path(os.path.join("images", "icons", "team.png"))
        try:
            return pygame.image.load(p).convert_alpha()
        except Exception:
            return None

    # ─────────────────────── ability diagrams ─────────────────────────
    DIAG_W, DIAG_H = 120, 40   # per-button diagram surface size
    DIAG_HEX = 8               # mini-hex centre-to-corner in px
    DIAG_SELF = (75, 130, 200)   # blue — caster
    DIAG_GRAY = (110, 118, 130)  # traversal
    DIAG_RED  = (220, 90, 90)    # affected target
    DIAG_BG   = (35, 42, 56)     # panel-ish backdrop for team icon

    def _mini_hex(self, surf, axial_qr, colour, origin):
        cx, cy = H.axial_to_pixel(axial_qr, self.DIAG_HEX, origin)
        pts = H.corners((cx, cy), self.DIAG_HEX - 1)
        pygame.draw.polygon(surf, colour, pts)
        pygame.draw.polygon(surf, (12, 14, 20), pts, 1)

    def _make_ability_diagram(self, ability_name):
        """Small hex diagram summarising the ability's shape.
           - self:           one blue hex.
           - team:           blue background + team.png.
           - cleave_arc:     one blue hex + three red (arc).
           - range N single/line/blast: blue + (N-1) gray + 1 red extending east.
        Returns a Surface of size DIAG_W × DIAG_H."""
        if ability_name in self._diagram_cache:
            return self._diagram_cache[ability_name]
        rng, shape, _radius = get_config(ability_name)
        surf = pygame.Surface((self.DIAG_W, self.DIAG_H), pygame.SRCALPHA)
        if shape == "team":
            # Blue caster in the middle + three green hexes at distance 2 in
            # every-other direction — none of the greens touch each other AND
            # none touch the blue centre. Uses a smaller mini-hex than the
            # default so the distance-2 layout fits in the diagram surface.
            SMALL_HEX = 5
            origin = (self.DIAG_W // 2, self.DIAG_H // 2)
            GREEN = (90, 200, 110)
            def small(qr, colour):
                cx, cy = H.axial_to_pixel(qr, SMALL_HEX, origin)
                pts = H.corners((cx, cy), SMALL_HEX - 1)
                pygame.draw.polygon(surf, colour, pts)
                pygame.draw.polygon(surf, (12, 14, 20), pts, 1)
            small((0, 0), self.DIAG_SELF)
            for q, r in ((2, 0), (0, -2), (-2, 2)):
                small((q, r), GREEN)
        elif shape == "self":
            origin = (self.DIAG_W // 2, self.DIAG_H // 2)
            self._mini_hex(surf, (0, 0), self.DIAG_SELF, origin)
        elif shape == "self_burst":
            # Caster centre + every hex within `radius`. Ring tiles coloured
            # yellow to match the in-battle team-hover preview colour.
            origin = (self.DIAG_W // 2, self.DIAG_H // 2)
            RING = (240, 200, 80)   # matches TILE_TARGET yellow
            for h in H.hexes_within((0, 0), max(1, _radius)):
                if h == (0, 0):
                    continue
                self._mini_hex(surf, h, RING, origin)
            self._mini_hex(surf, (0, 0), self.DIAG_SELF, origin)
        elif shape == "cleave_arc":
            # Caster at (0,0), target east at (1,0), flanks at (1,-1) & (0,1).
            origin = (self.DIAG_W // 2 - 14, self.DIAG_H // 2)
            self._mini_hex(surf, (0, 0),   self.DIAG_SELF, origin)
            self._mini_hex(surf, (1, 0),   self.DIAG_RED,  origin)
            self._mini_hex(surf, (1, -1),  self.DIAG_RED,  origin)
            self._mini_hex(surf, (0, 1),   self.DIAG_RED,  origin)
        elif shape == "lay_trap":
            # Caster + a red hex a couple of tiles away (the placed trap).
            n = max(1, rng)
            total_w = (n + 1) * (self.DIAG_HEX * 1.732)
            origin = (int((self.DIAG_W - total_w) // 2 + self.DIAG_HEX),
                      self.DIAG_H // 2)
            self._mini_hex(surf, (0, 0), self.DIAG_SELF, origin)
            for i in range(1, n):
                self._mini_hex(surf, (i, 0), self.DIAG_GRAY, origin)
            # The trap tile — drawn as a small diamond marker inside the hex.
            cx, cy = H.axial_to_pixel((n, 0), self.DIAG_HEX, origin)
            pts = H.corners((cx, cy), self.DIAG_HEX - 1)
            pygame.draw.polygon(surf, self.DIAG_GRAY, pts)
            pygame.draw.polygon(surf, (12, 14, 20), pts, 1)
            s = 4
            diamond = [(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)]
            pygame.draw.polygon(surf, self.DIAG_RED, diamond)
        else:
            # single / line / blast: blue self + (rng-1) gray + 1 red extending east.
            n = max(1, rng)
            total_w = (n + 1) * (self.DIAG_HEX * 1.732)   # sqrt(3) column pitch
            origin = (int((self.DIAG_W - total_w) // 2 + self.DIAG_HEX),
                      self.DIAG_H // 2)
            self._mini_hex(surf, (0, 0), self.DIAG_SELF, origin)
            for i in range(1, n + 1):
                colour = self.DIAG_RED if i == n else self.DIAG_GRAY
                self._mini_hex(surf, (i, 0), colour, origin)
        self._diagram_cache[ability_name] = surf
        return surf

    def _load_portraits(self):
        path = _resource_path(os.path.join("images", "portraits"))
        mapping = {
            "Thug": "thug.png", "Knight": "knight.png", "Thief": "thief.png",
            "Priestess": "priestess.png", "Berserker": "berserker.png",
            "Assassin": "assassin.png",
            "Hunter": "hunter.png",
            "Spellblade": "spellblade.jpg",  # placeholder — reuse Priestess avatar
        }
        out = {}
        for k, fn in mapping.items():
            fp = os.path.join(path, fn)
            try:
                img = pygame.image.load(fp).convert_alpha()
                out[k] = pygame.transform.smoothscale(img, (48, 48))
            except Exception:
                out[k] = None
        return out

    # ─────────────────────── log ───────────────────────────────────────
    def _log(self, msg):
        self.message_log.append(str(msg))
        self.message_log = self.message_log[-40:]

    def _drain_battle_log(self):
        # Battle module prints via builtins.print; we didn't reroute it here
        # (FRAY did that in its GUI). For v1 keep it simple: we mirror major
        # events into self.message_log at cast time in perform_ability wrapper.
        pass

    # ─────────────────────── turn flow ─────────────────────────────────
    def _begin_turn_flow(self):
        if self.hb.is_over():
            self.mode = "over"
            self._log("Battle over.")
            return
        team = self.hb.current_team
        if not self.hb.awaiting[team]:
            # Team turn just ended — the model handles this only when we
            # end_unit_turn. Force a nudge here defensively.
            self.hb.end_unit_turn()
            self._begin_turn_flow()
            return
        if team == 1 and self.enemy_ai_enabled:
            self.mode = "ai"
        else:
            self.mode = "pick_unit"

    def _begin_unit(self, unit):
        self.hb.begin_unit_turn(unit)
        self.selected_ability = None
        self.valid_targets = set()
        self.reachable = self._compute_reachable(unit)
        self.mode = "act"

    def _compute_reachable(self, unit):
        if self.hb.moved_this_turn or unit is None or unit.hex is None:
            return set()
        blocked = self.board.blocked_for(unit)
        reach = H.bfs_reachable(unit.hex, unit.MOVE, blocked=blocked,
                                in_bounds=self.board.in_bounds)
        return {t for t in reach.keys() if t != unit.hex}

    def _end_team_turn(self):
        """Force-end the whole team turn — button used to end per-unit turn."""
        self.hb.end_team_turn()
        self.selected_ability = None
        self.valid_targets = set()
        self.reachable = set()
        self._begin_turn_flow()

    def _after_player_action(self):
        """Called after a human perform_move/perform_ability lands.
        If HexBattle auto-ended the unit (both actions spent), rebuild UI
        state for picking another awaiting unit or transitioning."""
        self.selected_ability = None
        self.valid_targets = set()
        if self.hb.current_unit is None:
            # Unit auto-ended. Team may also have flipped inside the model.
            self.reachable = set()
            self._begin_turn_flow()
        else:
            self.reachable = self._compute_reachable(self.hb.current_unit)

    def _ai_enqueue(self, delay_ms, fn):
        """Schedule `fn` to fire in `delay_ms` from now."""
        self._ai_queue.append((pygame.time.get_ticks() + delay_ms, fn))

    def _ai_pump(self):
        """Fires any queued AI callbacks whose fire-time has arrived. If the
        queue empties and it's still an AI turn, schedule the next unit."""
        # Hold off while a move is animating — cast/end shouldn't overlap it.
        if self._active_anim is not None:
            return
        now = pygame.time.get_ticks()
        # Fire at most one queued step per frame — keeps pacing visible even
        # if two callbacks were scheduled at the same tick.
        for i, (fire_at, fn) in enumerate(self._ai_queue):
            if fire_at <= now:
                self._ai_queue.pop(i)
                fn()
                return
        if not self._ai_queue and self.mode == "ai":
            self._ai_schedule_next_unit()

    def _ai_schedule_next_unit(self):
        team = self.hb.current_team
        if not self.hb.awaiting[team]:
            # Team turn ended by process — force a nudge so the model flips.
            self.hb.end_unit_turn()
            self._begin_turn_flow()
            return
        u = self.hb.awaiting[team][0]
        self._ai_enqueue(AI_DELAY_START, lambda unit=u: self._ai_begin(unit))

    def _ai_begin(self, unit):
        self.hb.begin_unit_turn(unit)
        dest, ability, target = choose_turn(unit, self.board)
        # Phase 1: move (if any). Delay the cast at least long enough for the
        # movement animation to finish.
        if dest is not None:
            path = self._do_move(dest)
            self._log(f"{unit} moves to {dest}.")
            anim_ms = MOVE_STEP_MS * (max(1, len(path or []) - 1))
            phase2_delay = max(AI_DELAY_POST_MOVE, anim_ms + 120)
        else:
            phase2_delay = 0
        # Phase 2: cast (if any).
        if ability is not None and target is not None:
            self._ai_enqueue(phase2_delay,
                             lambda a=ability, t=target, u=unit: self._ai_cast(u, a, t))
        else:
            self._ai_enqueue(phase2_delay, self._ai_end_unit)

    def _ai_cast(self, unit, ability, target):
        ok = self._do_cast(ability, target)
        if ok:
            self._log(f"{unit} used {ability}.")
        self._ai_enqueue(AI_DELAY_POST_CAST, self._ai_end_unit)

    def _ai_end_unit(self):
        self.hb.end_unit_turn()
        self._ai_enqueue(AI_DELAY_END, self._ai_after_end)

    def _ai_after_end(self):
        # Team may have flipped — check what we're in now.
        if self.hb.is_over():
            self.mode = "over"
            return
        if self.hb.current_team == 1 and self.enemy_ai_enabled:
            self._ai_schedule_next_unit()
        else:
            self.mode = "pick_unit"

    # ─────────────────────── input ────────────────────────────────────
    def handle_click(self, mouse_pos):
        # While a unit is animating a move, refuse clicks so the player
        # can't queue up an action mid-tween.
        if self._active_anim is not None:
            return
        # Buttons first.
        for rect, kind, payload in self.action_buttons:
            if rect.collidepoint(mouse_pos):
                self._handle_button(kind, payload)
                return
        # Board interaction (only during player's turn).
        if self.mode == "ai" or self.mode == "over":
            return
        clicked_hex = H.pixel_to_axial(mouse_pos, HEX_SIZE, BOARD_ORIGIN)
        if not self.board.in_bounds(clicked_hex):
            return
        if self.mode == "pick_unit":
            unit = self.board.unit_at(clicked_hex)
            if unit is not None and unit in self.hb.awaiting[self.hb.current_team]:
                self._begin_unit(unit)
        elif self.mode == "act":
            # Clicking a reachable tile = Move. Clicking another awaiting
            # unit = swap caster (unrestricted — budgets are per-unit now,
            # switching mid-turn no longer clobbers state).
            if clicked_hex in self.reachable:
                caster = self.hb.current_unit
                self._do_move(clicked_hex)
                self._log(f"{caster} moves to {clicked_hex}.")
                self._after_player_action()
                return
            unit = self.board.unit_at(clicked_hex)
            if unit is not None and unit in self.hb.awaiting[self.hb.current_team] \
                    and unit is not self.hb.current_unit:
                self._begin_unit(unit)
        elif self.mode == "target":
            if clicked_hex in self.valid_targets:
                caster = self.hb.current_unit
                ok = self._do_cast(self.selected_ability, clicked_hex)
                if ok:
                    self._log(f"{caster} cast {self.selected_ability}.")
                    self._after_player_action()
                    if self.hb.current_unit is not None:
                        self.mode = "act"

    def _handle_button(self, kind, payload):
        if kind == "ability":
            if self.mode not in ("act", "target"):
                return
            if self.hb.acted_this_turn:
                return
            name = payload
            self.selected_ability = name
            tiles = get_valid_target_tiles(self.hb.current_unit, name, self.board)
            self.valid_targets = set(tiles)
            _, shape, _ = get_config(name)
            if shape in ("self", "team", "self_burst") and self.hb.current_unit.hex is not None:
                # No positional target — auto-fire at the caster's own tile.
                caster = self.hb.current_unit
                ok = self._do_cast(name, caster.hex)
                if ok:
                    self._log(f"{caster} cast {name}.")
                self._after_player_action()
                if self.hb.current_unit is not None:
                    self.mode = "act"
            else:
                self.mode = "target"
        elif kind == "end_turn":
            self._end_team_turn()
        elif kind == "cancel_ability":
            self.selected_ability = None
            self.valid_targets = set()
            self.mode = "act"

    # ─────────────────────── draw ─────────────────────────────────────
    def _hex_center(self, h):
        return H.axial_to_pixel(h, HEX_SIZE, BOARD_ORIGIN)

    def _draw_board(self):
        for h in self.board.tiles:
            cx, cy = self._hex_center(h)
            pts = H.corners((cx, cy), HEX_SIZE - 1)
            fill = TILE_FILL
            # Target-select tiles still fill (they're gold, sparse, and need to
            # read as clickable). Reach tiles are outlined at the perimeter
            # instead — see the loop below.
            if h in self.valid_targets:
                fill = TILE_TARGET
            pygame.draw.polygon(self.screen, fill, pts)
            pygame.draw.polygon(self.screen, TILE_BORDER, pts, 2)

        # Perimeter outline of the reachable region: for each reachable tile,
        # draw the shared edges with any *non*-reachable neighbour. Produces a
        # single continuous fence around the whole area rather than filling
        # each tile — reads as "the area you could move to" without hiding
        # what's already on those tiles.
        if self.reachable:
            for tile in self.reachable:
                tc = self._hex_center(tile)
                t_corners = H.corners(tc, HEX_SIZE - 1)
                for n in H.neighbors(tile):
                    if n in self.reachable:
                        continue
                    nc = self._hex_center(n)
                    # Pick the edge whose midpoint is closest to n's centre —
                    # that's the shared edge between `tile` and `n`.
                    best_i, best_d = 0, float("inf")
                    for i in range(6):
                        a, b = t_corners[i], t_corners[(i + 1) % 6]
                        mx = (a[0] + b[0]) * 0.5
                        my = (a[1] + b[1]) * 0.5
                        d = (mx - nc[0]) ** 2 + (my - nc[1]) ** 2
                        if d < best_d:
                            best_d, best_i = d, i
                    a = t_corners[best_i]
                    b = t_corners[(best_i + 1) % 6]
                    pygame.draw.line(self.screen, TILE_REACH, a, b, 4)

        # Traps — small red diamond centred on tile so both players see them.
        for h, trap in self.board.traps.items():
            cx, cy = self._hex_center(h)
            s = 10
            diamond = [(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)]
            trap_col = (220, 90, 90) if trap["owner_team"] == 0 else (220, 140, 90)
            pygame.draw.polygon(self.screen, trap_col, diamond)
            pygame.draw.polygon(self.screen, (10, 10, 12), diamond, 2)

        # AoE preview under hover.
        if self.mode == "target" and self.hover_hex in self.valid_targets \
                and self.selected_ability is not None:
            _, shape, radius = get_config(self.selected_ability)
            preview = set()
            if shape == "blast":
                preview = set(H.hexes_within(self.hover_hex, radius))
            elif shape == "line" and self.hb.current_unit is not None:
                preview = set(H.line(self.hb.current_unit.hex, self.hover_hex))
            elif shape == "cleave_arc" and self.hb.current_unit is not None:
                preview = set(cleave_arc_hexes(self.hb.current_unit.hex, self.hover_hex))
            elif shape == "single":
                preview = {self.hover_hex}
            for h in preview:
                if not self.board.in_bounds(h):
                    continue
                cx, cy = self._hex_center(h)
                pts = H.corners((cx, cy), HEX_SIZE - 3)
                pygame.draw.polygon(self.screen, TILE_AOE, pts, 3)

        # Team-shape hover preview: fill every affected tile yellow when the
        # mouse is over a team-scope ability button. Team abilities auto-fire
        # (no target picker), so this is the only way to show who they'll hit.
        # Filled here (after tile draws, before unit draws) so the yellow sits
        # behind the portrait rather than obscuring it.
        if self._hover_ability_name is not None and self.hb.current_unit is not None:
            _, hover_shape, _ = get_config(self._hover_ability_name)
            if hover_shape in ("team", "self_burst"):
                affected = aoe_affected_units(
                    self.hb.current_unit.hex, self._hover_ability_name,
                    self.hb.current_unit, self.board)
                for u in affected:
                    if u is None or u.hex is None:
                        continue
                    cx, cy = self._hex_center(u.hex)
                    pts = H.corners((cx, cy), HEX_SIZE - 1)
                    pygame.draw.polygon(self.screen, TILE_TARGET, pts)
                    pygame.draw.polygon(self.screen, TILE_BORDER, pts, 2)

    def _draw_units(self):
        for h in list(self.board.occupied()):
            u = self.board.unit_at(h)
            if u is None or not u.alive:
                continue
            # Use tween pixel while animating, else board hex centre.
            anim_pos = self._anim_pixel_for(u)
            cx, cy = anim_pos if anim_pos is not None else self._hex_center(h)
            # Cast-nudge (caster lunging toward target) and flinch (target
            # recoiling away from caster) both stack on top of position.
            ox, oy = self._nudge_offset_for(u)
            fx, fy = self._flinch_offset_for(u)
            cx += ox + fx
            cy += oy + fy
            border_col = TEAM0_COL if u.team == 0 else TEAM1_COL
            if u is self.hb.current_unit:
                border_col = CURRENT_COL
            # Breathing outer glow on units that still have their turn
            # to spend — only on the current team, and only if they're not
            # the currently-selected unit (that one already gets CURRENT_COL).
            awaiting = self.hb.awaiting.get(self.hb.current_team, [])
            is_awaiting = (u in awaiting and u is not self.hb.current_unit)
            if is_awaiting:
                import math
                # sin-based breath: period ~1.4 s, alpha 60→180, radius pad 2→9.
                t = pygame.time.get_ticks() / 1000.0
                k = 0.5 + 0.5 * math.sin(t * (2 * math.pi / 1.4))
                pad = int(2 + k * 7)
                alpha = int(60 + k * 120)
                glow_pts = H.corners((cx, cy), HEX_SIZE + pad)
                # Render outline to an alpha surface so we can fade it.
                surf_size = int((HEX_SIZE + pad + 4) * 2)
                glow_surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
                local_pts = [(p[0] - cx + surf_size // 2,
                              p[1] - cy + surf_size // 2) for p in glow_pts]
                pygame.draw.polygon(
                    glow_surf,
                    (border_col[0], border_col[1], border_col[2], alpha),
                    local_pts, 3)
                self.screen.blit(glow_surf, (cx - surf_size // 2, cy - surf_size // 2))
            # Hex outline hugging the tile — same 6 corners the tile is drawn
            # with, just inset a touch so it reads as a highlight rim rather
            # than overwriting the tile's own border.
            outline_pts = H.corners((cx, cy), HEX_SIZE - 4)
            pygame.draw.polygon(self.screen, border_col, outline_pts, 3)
            portrait = self.portraits.get(type(u).__bases__[0].className)
            if portrait is not None:
                r = portrait.get_rect(center=(int(cx), int(cy) - 4))
                self.screen.blit(portrait, r)
            # HP + MP bars stacked beneath the portrait.
            bar_w = HEX_SIZE
            bar_h = 6
            bar_gap = 2
            hp_ratio = u.hp / u.max_hp if u.max_hp else 0
            mp_ratio = u.mp / u.max_mp if u.max_mp else 0
            # Sit the HP bar just under the portrait (portrait bottom ≈ cy+20
            # with the current 48px scale + -4 centre offset).
            hp_y = int(cy) + 22
            mp_y = hp_y + bar_h + bar_gap
            hp_bar = pygame.Rect(int(cx) - bar_w // 2, hp_y, bar_w, bar_h)
            mp_bar = pygame.Rect(int(cx) - bar_w // 2, mp_y, bar_w, bar_h)
            pygame.draw.rect(self.screen, (60, 30, 30), hp_bar)
            pygame.draw.rect(self.screen, (200, 80, 80),
                             pygame.Rect(hp_bar.x, hp_bar.y, int(hp_bar.w * hp_ratio), hp_bar.h))
            pygame.draw.rect(self.screen, (10, 10, 12), hp_bar, 1)
            pygame.draw.rect(self.screen, (25, 40, 70), mp_bar)
            pygame.draw.rect(self.screen, (80, 140, 220),
                             pygame.Rect(mp_bar.x, mp_bar.y, int(mp_bar.w * mp_ratio), mp_bar.h))
            pygame.draw.rect(self.screen, (10, 10, 12), mp_bar, 1)
            # Effect pills sit above the portrait — small rounded rects
            # coloured by buff/debuff, showing status + stack count.
            self._draw_effect_pills(u, cx, cy)

    def _draw_effect_pills(self, unit, cx, cy):
        """Row of coloured status pills above the portrait."""
        if not unit.effect_stacks_dict:
            return
        pill_h = 14
        pad_x = 6
        gap = 4
        y = int(cy) - HEX_SIZE + 6   # top of tile, small inset
        # Pre-render each pill to measure widths, then centre-align the row.
        entries = []
        for status, stacks in unit.effect_stacks_dict.items():
            label = status if stacks <= 1 else f"{status} x{stacks}"
            surf = self.small.render(label, True, TEXT)
            entries.append((status, surf))
        total_w = sum(e[1].get_width() + pad_x * 2 for e in entries) + gap * max(0, len(entries) - 1)
        x = int(cx) - total_w // 2
        for status, surf in entries:
            w = surf.get_width() + pad_x * 2
            rect = pygame.Rect(x, y, w, pill_h)
            colour = self._effect_pill_bg.get(status, PILL_BUFF)
            pygame.draw.rect(self.screen, colour, rect, border_radius=6)
            pygame.draw.rect(self.screen, (10, 10, 12), rect, 1, border_radius=6)
            self.screen.blit(surf, surf.get_rect(center=rect.center))
            x += w + gap

    def _draw_unit_tooltip(self):
        """When the mouse hovers a board hex holding a unit, show a tooltip
        with stats + effects. Tooltip anchor is offset from the unit centre
        in the direction of the cursor, with distance proportional to how
        far the cursor is from the tile centre (edge = far, centre = near)."""
        if self.state != "battle" or self.mode == "ai":
            return
        mp = pygame.mouse.get_pos()
        # Only proceed if the pointer is actually over a valid hex/unit.
        if not self.board:
            return
        h = H.pixel_to_axial(mp, HEX_SIZE, BOARD_ORIGIN)
        if not self.board.in_bounds(h):
            return
        u = self.board.unit_at(h)
        if u is None:
            return
        # Build tooltip lines.
        cls_name = getattr(type(u).__bases__[0], "className", "Unit")
        lines = [
            f"{cls_name} | {u.name}   (team {u.team})",
            f"HP {u.hp}/{u.max_hp}   MP {u.mp}/{u.max_mp}",
            f"ATK {u.ATK}   DEF {u.DEF}   MAGIC {u.MAGIC}",
            f"CRIT {u.CRIT}%   DODGE {u.DODGE}%   MOVE {u.MOVE}",
        ]
        if u.effect_stacks_dict:
            lines.append("")
            lines.append("Effects:")
            for status, stacks in u.effect_stacks_dict.items():
                tip = self._effect_tooltip_map.get(status, "")
                stack_str = f" x{stacks}" if stacks > 1 else ""
                lines.append(f"  {status}{stack_str}" + (f" — {tip}" if tip else ""))
        # Measure.
        pad = 8
        line_h = self.small.get_linesize()
        w = max(self.small.size(ln)[0] for ln in lines) + pad * 2
        box_h = line_h * len(lines) + pad * 2
        # Direction from tile centre to cursor; anchor tooltip on that side.
        cx, cy = self._hex_center(h)
        dx = mp[0] - cx
        dy = mp[1] - cy
        r = (dx * dx + dy * dy) ** 0.5
        if r < 1:
            r = 1
        dirx, diry = dx / r, dy / r
        # Distance from tile centre to tooltip centre — closer to tile edge
        # (large r) → tooltip is pushed further out.
        edge_frac = min(1.0, r / HEX_SIZE)             # 0 at centre, 1 at edge
        push = HEX_SIZE + 24 + edge_frac * 50         # 80 (centre) → 220 (edge)
        anchor_x = cx + dirx * push
        anchor_y = cy + diry * push
        box = pygame.Rect(0, 0, w, box_h)
        box.center = (int(anchor_x), int(anchor_y))
        # Clamp to screen.
        if box.left < 8:
            box.left = 8
        if box.right > WIDTH - 8:
            box.right = WIDTH - 8
        if box.top < 8:
            box.top = 8
        if box.bottom > HEIGHT - 8:
            box.bottom = HEIGHT - 8
        pygame.draw.rect(self.screen, (28, 32, 44), box, border_radius=6)
        pygame.draw.rect(self.screen, PANEL_BORDER, box, 2, border_radius=6)
        for i, ln in enumerate(lines):
            surf = self.small.render(ln, True, TEXT)
            self.screen.blit(surf, (box.x + pad, box.y + pad + i * line_h))

    def _draw_top_bar(self):
        team = self.hb.current_team
        team_txt = f"Team {team}'s turn"
        surf = self.title_font.render(team_txt, True, TEAM0_COL if team == 0 else TEAM1_COL)
        self.screen.blit(surf, (30, 20))
        if self.hb.current_unit is not None:
            u = self.hb.current_unit
            info = f"{u}  HP {u.hp}/{u.max_hp}  MP {u.mp}/{u.max_mp}  MOVE {u.MOVE}"
            s = self.font.render(info, True, TEXT)
            self.screen.blit(s, (30, 58))
            budget = []
            budget.append("Move: " + ("used" if self.hb.moved_this_turn else "available"))
            budget.append("Action: " + ("used" if self.hb.acted_this_turn else "available"))
            s2 = self.small.render(" | ".join(budget), True, DIM_TEXT)
            self.screen.blit(s2, (30, 80))

    def _action_panel_rect(self):
        """Shared geometry so the End Team Turn button can sit directly under
        the action panel without duplicating the layout constants."""
        panel_w = 300
        panel_top = 100
        panel_bottom = HEIGHT - 240   # leave room for the log
        return pygame.Rect(WIDTH - panel_w - 20, panel_top,
                           panel_w, panel_bottom - panel_top)

    def _draw_action_panel(self):
        self.action_buttons.clear()
        ABILITY_H = 72          # taller boxes for easier reading + wider diagram row
        ABILITY_GAP = 10
        panel = self._action_panel_rect()
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=8)
        pygame.draw.rect(self.screen, PANEL_BORDER, panel, 2, border_radius=8)
        title = self.title_font.render("Actions", True, TEXT)
        self.screen.blit(title, (panel.x + 12, panel.y + 8))
        if self.hb.current_unit is None or self.mode == "ai":
            hint = self.small.render(
                "AI turn." if self.mode == "ai" else "Click a highlighted unit.",
                True, DIM_TEXT)
            self.screen.blit(hint, (panel.x + 12, panel.y + 44))
            return
        u = self.hb.current_unit
        y = panel.y + 48
        moves = list(u.movesList)
        for m in moves:
            mp = Ability.get_attr(m, "MP_COST") or 0
            can_afford = u.mp >= mp
            already_acted = self.hb.acted_this_turn
            enabled = can_afford and not already_acted
            rect = pygame.Rect(panel.x + 12, y, panel.w - 24, ABILITY_H)
            hover = rect.collidepoint(pygame.mouse.get_pos())
            if not enabled:
                fill = BTN_DISABLED
            elif self.selected_ability == m:
                fill = ABIL_SELECTED     # gold while targeting
            else:
                fill = ABIL_READY_HOVER if hover else ABIL_READY_FILL
            pygame.draw.rect(self.screen, fill, rect, border_radius=6)
            pygame.draw.rect(self.screen, PANEL_BORDER, rect, 1, border_radius=6)
            label = f"{m}"
            info = Ability.get_attr(m, "TOOLTIP_INFO") or ""
            # Label: top, larger. TOOLTIP_INFO: bottom, small.
            self.screen.blit(self.title_font.render(label, True, TEXT),
                             (rect.x + 12, rect.y + 6))
            self.screen.blit(self.small.render(info, True, TEXT),
                             (rect.x + 12, rect.bottom - 20))
            # Shape diagram on the right — pre-rendered per ability.
            diagram = self._make_ability_diagram(m)
            self.screen.blit(diagram,
                             diagram.get_rect(midright=(rect.right - 10,
                                                        rect.centery)))
            if enabled:
                self.action_buttons.append((rect, "ability", m))
            y += ABILITY_H + ABILITY_GAP
        # Cancel target
        if self.mode == "target":
            ct_rect = pygame.Rect(panel.x + 12, panel.bottom - 46, panel.w - 24, 30)
            hover = ct_rect.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(self.screen, BTN_HOVER if hover else BTN_FILL, ct_rect, border_radius=6)
            pygame.draw.rect(self.screen, PANEL_BORDER, ct_rect, 1, border_radius=6)
            s = self.small.render("Cancel target", True, TEXT)
            self.screen.blit(s, s.get_rect(center=ct_rect.center))
            self.action_buttons.append((ct_rect, "cancel_ability", None))

    # ─────────────────────── pause menu ───────────────────────────────
    def _toggle_pause(self):
        if not self._paused:
            self._paused = True
        else:
            self._paused = False

    def _restart_battle(self):
        """Rebuild the fight with the same teams."""
        self._paused = False
        self._start_battle()

    def _end_battle_to_selection(self):
        """Drop back to the team-selection screen."""
        self._paused = False
        self.state = "select"
        self.mode = "pick_unit"
        self.selected_ability = None
        self.reachable = set()
        self.valid_targets = set()
        self._ai_queue = []
        self._active_anim = None
        self._after_anim_cb = None

    def _draw_pause_menu(self):
        """Modal overlay covering the whole screen — options for the paused
        battle. Populated buttons live in `_pause_buttons` for click routing."""
        self._pause_buttons = []
        # Dim everything behind the menu.
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 150))
        self.screen.blit(veil, (0, 0))
        box_w, box_h = 360, 320
        box = pygame.Rect((WIDTH - box_w) // 2, (HEIGHT - box_h) // 2, box_w, box_h)
        pygame.draw.rect(self.screen, PANEL, box, border_radius=10)
        pygame.draw.rect(self.screen, PANEL_BORDER, box, 3, border_radius=10)
        title = self.title_font.render("Paused", True, TEXT)
        self.screen.blit(title, title.get_rect(midtop=(box.centerx, box.y + 18)))
        # Four vertical options.
        options = [
            ("Resume",         "resume"),
            ("Restart Battle", "restart"),
            ("End Battle",     "end"),
            ("Quit Game",      "quit"),
        ]
        btn_h = 48
        btn_gap = 12
        y = box.y + 72
        for label, kind in options:
            rect = pygame.Rect(box.x + 24, y, box.w - 48, btn_h)
            hover = rect.collidepoint(pygame.mouse.get_pos())
            fill = BTN_HOVER if hover else BTN_FILL
            if kind == "quit":
                fill = END_TURN_READY_HOVER if hover else END_TURN_READY_FILL
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, PANEL_BORDER, rect, 2, border_radius=8)
            s = self.title_font.render(label, True, TEXT)
            self.screen.blit(s, s.get_rect(center=rect.center))
            self._pause_buttons.append((rect, kind))
            y += btn_h + btn_gap

    def _handle_pause_click(self, mouse_pos):
        for rect, kind in self._pause_buttons:
            if rect.collidepoint(mouse_pos):
                if kind == "resume":
                    self._paused = False
                elif kind == "restart":
                    self._restart_battle()
                elif kind == "end":
                    self._end_battle_to_selection()
                elif kind == "quit":
                    self._quit_requested = True
                return

    def _draw_end_team_turn_button(self):
        """Standalone button sitting just below the action panel. Orange only
        when every remaining awaiting unit has already spent at least one of
        their move/action — otherwise stays neutral so it doesn't shout for
        attention while fresh units still have things to do."""
        if self.state != "battle" or self.mode == "ai":
            return
        panel = self._action_panel_rect()
        rect = pygame.Rect(panel.x, panel.bottom + 12, panel.w, 40)
        hover = rect.collidepoint(pygame.mouse.get_pos())
        awaiting = self.hb.awaiting.get(self.hb.current_team, [])
        team_done = bool(awaiting) and all(
            self.hb.has_moved(u) or self.hb.has_acted(u) for u in awaiting)
        if team_done or not awaiting:
            fill = END_TURN_READY_HOVER if hover else END_TURN_READY_FILL
        else:
            fill = BTN_HOVER if hover else BTN_FILL
        pygame.draw.rect(self.screen, fill, rect, border_radius=8)
        pygame.draw.rect(self.screen, PANEL_BORDER, rect, 2, border_radius=8)
        label = self.title_font.render("End Team Turn", True, TEXT)
        self.screen.blit(label, label.get_rect(center=rect.center))
        self.action_buttons.append((rect, "end_turn", None))

    def _draw_log(self):
        panel = pygame.Rect(30, HEIGHT - 200, 800, 170)
        pygame.draw.rect(self.screen, LOG_BG, panel, border_radius=6)
        pygame.draw.rect(self.screen, PANEL_BORDER, panel, 2, border_radius=6)
        title = self.small.render("LOG", True, DIM_TEXT)
        self.screen.blit(title, (panel.x + 8, panel.y + 6))
        y = panel.y + 24
        line_h = 16
        visible = 9
        for line in self.message_log[-visible:]:
            s = self.small.render(line, True, TEXT)
            self.screen.blit(s, (panel.x + 12, y))
            y += line_h

    def _draw_overlay(self):
        if self.mode == "over":
            alive0 = sum(1 for u in Unit.get_units("alive", 0))
            alive1 = sum(1 for u in Unit.get_units("alive", 1))
            if alive0 > alive1:
                text, col = "Team 0 wins", TEAM0_COL
            elif alive1 > alive0:
                text, col = "Team 1 wins", TEAM1_COL
            else:
                text, col = "Draw", TEXT
            s = self.title_font.render(text, True, col)
            r = s.get_rect(center=(WIDTH // 2, 40))
            self.screen.blit(s, r)

    # ─────────────────────── selection screen ─────────────────────────
    CLASS_CYCLE = ["K", "P", "TH", "B", "A", "T", "H", "SB"]
    CLASS_LABELS = {"K": "Knight", "P": "Priestess", "TH": "Thief",
                    "B": "Berserker", "A": "Assassin", "T": "Thug",
                    "H": "Hunter", "SB": "Spellblade"}
    MAX_TEAM = 5

    def _selection_layout(self):
        """Fixed geometry for the selection screen. Kept as a helper so
        draw + click share the exact same rects."""
        col_w = 340
        slot_h = 88
        slot_gap = 12
        top_y = 160
        left_x = 140
        right_x = WIDTH - 140 - col_w
        return {
            "col_w": col_w, "slot_h": slot_h, "slot_gap": slot_gap,
            "top_y": top_y, "left_x": left_x, "right_x": right_x,
        }

    def _draw_selection_screen(self):
        self.action_buttons.clear()
        L = self._selection_layout()

        title = self.title_font.render("FRAY — Hex Team Selection", True, TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 60)))
        hint = self.small.render(
            "Click a slot to cycle class. + adds a slot, × removes. Up to 5 per team.",
            True, DIM_TEXT)
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 100)))

        for team_i, (label, team, col_x) in enumerate((
                ("Player Team", self.player_team, L["left_x"]),
                ("Enemy Team",  self.enemy_team,  L["right_x"]))):
            th = self.title_font.render(label, True, TEAM0_COL if team_i == 0 else TEAM1_COL)
            self.screen.blit(th, (col_x, L["top_y"] - 40))
            for i, key in enumerate(team):
                y = L["top_y"] + i * (L["slot_h"] + L["slot_gap"])
                self._draw_selection_slot(col_x, y, L["col_w"], L["slot_h"], key,
                                          team_i, i)
            # Add-slot button below last slot (or at top if empty).
            if len(team) < self.MAX_TEAM:
                y = L["top_y"] + len(team) * (L["slot_h"] + L["slot_gap"])
                add_rect = pygame.Rect(col_x, y, L["col_w"], 36)
                hover = add_rect.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(self.screen, BTN_HOVER if hover else BTN_FILL,
                                 add_rect, border_radius=6)
                pygame.draw.rect(self.screen, PANEL_BORDER, add_rect, 1, border_radius=6)
                s = self.font.render("+ Add slot", True, TEXT)
                self.screen.blit(s, s.get_rect(center=add_rect.center))
                self.action_buttons.append((add_rect, "sel_add", team_i))

        # Enemy AI toggle.
        ai_rect = pygame.Rect(WIDTH // 2 - 130, HEIGHT - 200, 260, 36)
        hover = ai_rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(self.screen, BTN_HOVER if hover else BTN_FILL,
                         ai_rect, border_radius=6)
        pygame.draw.rect(self.screen, PANEL_BORDER, ai_rect, 1, border_radius=6)
        ai_label = f"Enemy AI: {'ON' if self.enemy_ai_enabled else 'OFF'}"
        s = self.font.render(ai_label, True, TEXT)
        self.screen.blit(s, s.get_rect(center=ai_rect.center))
        self.action_buttons.append((ai_rect, "sel_toggle_ai", None))

        # START button.
        can_start = 1 <= len(self.player_team) <= self.MAX_TEAM \
                    and 1 <= len(self.enemy_team) <= self.MAX_TEAM
        start_rect = pygame.Rect(WIDTH // 2 - 120, HEIGHT - 140, 240, 60)
        hover = start_rect.collidepoint(pygame.mouse.get_pos())
        if can_start:
            fill = (80, 180, 100) if not hover else (110, 210, 130)
        else:
            fill = BTN_DISABLED
        pygame.draw.rect(self.screen, fill, start_rect, border_radius=8)
        pygame.draw.rect(self.screen, PANEL_BORDER, start_rect, 2, border_radius=8)
        s = self.title_font.render("START BATTLE", True, TEXT)
        self.screen.blit(s, s.get_rect(center=start_rect.center))
        if can_start:
            self.action_buttons.append((start_rect, "sel_start", None))

    def _draw_selection_slot(self, x, y, w, h, class_key, team_i, slot_i):
        rect = pygame.Rect(x, y, w, h)
        hover = rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(self.screen, PANEL_BORDER if hover else PANEL,
                         rect, border_radius=8)
        pygame.draw.rect(self.screen, PANEL_BORDER, rect, 2, border_radius=8)
        # Portrait.
        cls_name = self.CLASS_LABELS.get(class_key, "?")
        portrait = self.portraits.get(cls_name)
        if portrait is not None:
            p = pygame.transform.smoothscale(portrait, (h - 16, h - 16))
            self.screen.blit(p, p.get_rect(midleft=(x + 12, y + h // 2)))
        # Label.
        name = self.title_font.render(cls_name, True, TEXT)
        self.screen.blit(name, (x + h + 12, y + 18))
        hint = self.small.render("click to cycle class", True, DIM_TEXT)
        self.screen.blit(hint, (x + h + 12, y + h - 24))
        # Remove ×.
        x_rect = pygame.Rect(x + w - 32, y + 8, 24, 24)
        x_hover = x_rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(self.screen, (170, 60, 60) if x_hover else (110, 40, 40),
                         x_rect, border_radius=4)
        xs = self.font.render("×", True, TEXT)
        self.screen.blit(xs, xs.get_rect(center=x_rect.center))
        self.action_buttons.append((x_rect, "sel_remove", (team_i, slot_i)))
        # Slot body itself (below the × so click precedence works).
        self.action_buttons.append((rect, "sel_cycle", (team_i, slot_i)))

    def _handle_selection_button(self, kind, payload):
        if kind == "sel_add":
            team_i = payload
            team = self.player_team if team_i == 0 else self.enemy_team
            if len(team) < self.MAX_TEAM:
                team.append(self.CLASS_CYCLE[0])
        elif kind == "sel_remove":
            team_i, slot_i = payload
            team = self.player_team if team_i == 0 else self.enemy_team
            if 0 <= slot_i < len(team) and len(team) > 1:
                team.pop(slot_i)
        elif kind == "sel_cycle" or kind == "sel_cycle_back":
            team_i, slot_i = payload
            team = self.player_team if team_i == 0 else self.enemy_team
            if 0 <= slot_i < len(team):
                cur = team[slot_i]
                step = -1 if kind == "sel_cycle_back" else 1
                base = self.CLASS_CYCLE.index(cur) if cur in self.CLASS_CYCLE else 0
                idx = (base + step) % len(self.CLASS_CYCLE)
                team[slot_i] = self.CLASS_CYCLE[idx]
        elif kind == "sel_toggle_ai":
            self.enemy_ai_enabled = not self.enemy_ai_enabled
        elif kind == "sel_start":
            self._start_battle()

    def _handle_selection_click(self, mouse_pos, right=False):
        # The × button rect gets added BEFORE the slot body rect, so it
        # wins the precedence check. Right-click on a slot cycles backward
        # through classes; on other buttons right-click is ignored.
        for rect, kind, payload in self.action_buttons:
            if rect.collidepoint(mouse_pos) and kind.startswith("sel_"):
                if right:
                    if kind == "sel_cycle":
                        self._handle_selection_button("sel_cycle_back", payload)
                    return
                self._handle_selection_button(kind, payload)
                return

    # ─────────────────────── draw / run ────────────────────────────────
    def _refresh_hover_ability(self):
        """Scan the last frame's action_buttons for a hovered ability slot.
        One-frame stale is fine — buttons only move when the current unit
        changes, and the mouse can't cross a slot faster than one frame."""
        self._hover_ability_name = None
        mp = pygame.mouse.get_pos()
        for rect, kind, payload in self.action_buttons:
            if kind == "ability" and rect.collidepoint(mp):
                self._hover_ability_name = payload
                return

    def draw(self):
        self.screen.fill(BG)
        if self.state == "select":
            self._draw_selection_screen()
        else:
            self._refresh_hover_ability()
            self._draw_board()
            self._draw_units()
            self._draw_splashes()   # floating damage numbers over everything
            self._draw_top_bar()
            self._draw_action_panel()
            self._draw_end_team_turn_button()
            self._draw_log()
            self._draw_unit_tooltip()
            self._draw_overlay()
            if self._paused:
                self._draw_pause_menu()
        pygame.display.flip()

    def run(self):
        running = True
        while running:
            self.clock.tick(FPS)
            if self.state == "battle":
                self.hover_hex = H.pixel_to_axial(pygame.mouse.get_pos(),
                                                  HEX_SIZE, BOARD_ORIGIN)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                    if self.state == "battle" and self.mode == "target" and not self._paused:
                        self._handle_button("cancel_ability", None)
                    elif self.state == "battle":
                        # In battle: ESC toggles the pause menu.
                        self._toggle_pause()
                    else:
                        running = False
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    if self.state == "battle" and self._paused:
                        self._handle_pause_click(e.pos)
                    elif self.state == "select":
                        self._handle_selection_click(e.pos)
                    else:
                        self.handle_click(e.pos)
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 3:
                    # Right-click: in battle, cancels target selection (parity
                    # with ESC). On the selection screen, cycles the clicked
                    # class slot backward through the class list.
                    if self.state == "select":
                        self._handle_selection_click(e.pos, right=True)
                    elif self.state == "battle" and self.mode == "target":
                        self._handle_button("cancel_ability", None)
            if self.state == "battle" and not self._paused:
                self._update_animation()
                if self.mode == "ai":
                    self._ai_pump()
            if self._quit_requested:
                running = False
            self.draw()
        pygame.quit()


if __name__ == "__main__":
    HexGUI().run()
