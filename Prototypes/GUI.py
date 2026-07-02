import builtins
import math
import os
import pygame
import random
import re
import sys
import time


def _resource_path(relative):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)
from battle import Battle
from Units import Unit, Unit_Knight, Unit_Thief, Unit_Priest, Unit_Berserker, Unit_Assassin, Unit_Thug
from Abilities import Ability

# Pygame GUI for the turn-based battle prototype

pygame.init()
pygame.font.init()
pygame.mixer.init()

_display_info = pygame.display.Info()
WIDTH = _display_info.current_w
HEIGHT = _display_info.current_h
FPS = 30

WHITE = (245, 245, 245)
BLACK = (20, 20, 20)
TRUE_BLACK = (0, 0, 0)
DARK_GRAY = (45, 45, 45)
LIGHT_GRAY = (200, 200, 200)
BLUE = (70, 130, 180)
GREEN = (80, 190, 120)
DARK_GREEN = (40, 130, 50)      # Poison damage splash colour
RED = (220, 80, 80)

BUTTON_COLOR = (70, 130, 180)
BUTTON_HOVER = (90, 160, 205)
BUTTON_TEXT = WHITE
LOG_BG = (35, 35, 35)
LOG_TEXT = (230, 230, 230)
# Battle-log semantic colours
LOG_NAME_COLOR    = (255, 215,   0)  # gold — unit names
LOG_ABILITY_COLOR = (200, 150, 240)  # violet — ability names
LOG_DMG_COLOR     = (230,  90,  90)  # red — damage taken
LOG_HEAL_COLOR    = (110, 220, 130)  # green — heals
LOG_BUFF_COLOR    = (110, 170, 240)  # blue — stat buffs
LOG_DEBUFF_COLOR  = (240, 160,  60)  # orange — stat debuffs / stuns
AI_CAST_EVENT = pygame.USEREVENT + 1
AI_SHOW_EVENT = pygame.USEREVENT + 2
NEXT_TURN_EVENT = pygame.USEREVENT + 3
HIT_SOUND_EVENT = pygame.USEREVENT + 4
MUSIC_END_EVENT = pygame.USEREVENT + 5
HIT_DMG_LIGHT = 14
HIT_DMG_MEDIUM = 26
FONT = pygame.font.SysFont("arial", 18)
TITLE_FONT = pygame.font.SysFont("arial", 24, bold=True)
SMALL_FONT = pygame.font.SysFont("arial", 14)

# Battle layout constants (relative to native WIDTH)
OUTER_PADDING = 30
LOG_PANEL_W = 300                  # kept for compatibility; not used by new layout
# Vertical-column battle layout
BATTLE_COLUMN_W = 280              # card width inside a team column
BATTLE_COLUMN_PAD = 30             # outer padding from screen edge
ACTION_BTN_W = 210                 # ability button width
ACTION_BTN_GAP = 10                # gap between card edge and action button column
PLAYER_CARD_X = BATTLE_COLUMN_PAD
CARD_W = BATTLE_COLUMN_W
ENEMY_CARD_X = WIDTH - BATTLE_COLUMN_PAD - BATTLE_COLUMN_W
# Battle log (small box at bottom centre)
LOG_BOX_W = 620
LOG_BOX_H = 200
LOG_BOX_MARGIN_BOTTOM = 18

# Hotkeys: first ability = Q, second = W, ...   first target = 1, second = 2, ...
ABILITY_HOTKEY_LABELS = ["Q", "W", "E", "R", "T", "Y"]
ABILITY_HOTKEY_KEYS = [pygame.K_q, pygame.K_w, pygame.K_e, pygame.K_r, pygame.K_t, pygame.K_y]
TARGET_HOTKEY_KEYS = [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5]
# Selection layout constants
SEL_SLOT_W = 320
SEL_SLOT_H = 100
SEL_SLOT_SPACING = 120
SEL_P_X = 180
SEL_E_X = WIDTH - 180 - SEL_SLOT_W
LOG_PANEL_H = 0  # unused, kept for compatibility


def draw_text(surface, text, rect, font, color=BLACK, align="topleft"):
    words = [word.split(' ') for word in text.splitlines()]
    space = font.size(' ')[0]
    x, y = rect.topleft
    max_width = rect.width
    for line in words:
        for word in line:
            word_surface = font.render(word, True, color)
            word_width, word_height = word_surface.get_size()
            if x + word_width >= rect.right:
                x = rect.left
                y += word_height
            surface.blit(word_surface, (x, y))
            x += word_width + space
        x = rect.left
        y += word_height


class Button:
    def __init__(self, rect, text, action=None, color=BUTTON_COLOR, hover_color=BUTTON_HOVER, tooltip="", right_text="", icon=None, left_text="", image_stacked=False, icon_left=False, label_font=None):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.action = action
        self.color = color
        self.hover_color = hover_color
        self.tooltip = tooltip
        self.right_text = right_text
        self.left_text = left_text
        self.icon = icon   # optional pygame.Surface drawn centred instead of text
        # When image_stacked is True the icon renders in the upper portion of
        # the button and the text renders beneath it (used by the START button).
        self.image_stacked = image_stacked
        # When icon_left is True the icon renders on the left side of the button
        # with the text to its right (used by the Enemy AI toggle).
        self.icon_left = icon_left
        self.label_font = label_font
        self.hover = False

    def draw(self, surface):
        fill = self.hover_color if self.hover else self.color
        pygame.draw.rect(surface, fill, self.rect, border_radius=6)
        pygame.draw.rect(surface, BLACK, self.rect, 2, border_radius=6)
        if self.icon and self.image_stacked:
            font = self.label_font or FONT
            label_h = font.get_linesize() if self.text else 0
            pad = 10
            icon_area_h = self.rect.height - label_h - pad * 2
            self.icon.get_rect(midtop=(self.rect.centerx, self.rect.y + pad))
            icon_rect = self.icon.get_rect(midtop=(self.rect.centerx, self.rect.y + pad))
            surface.blit(self.icon, icon_rect)
            if self.text:
                label_surf = font.render(self.text, True, WHITE)
                label_rect = label_surf.get_rect(midtop=(self.rect.centerx, self.rect.y + pad + icon_area_h))
                surface.blit(label_surf, label_rect)
        elif self.icon and self.icon_left and self.text:
            font = self.label_font or FONT
            pad = 10
            icon_rect = self.icon.get_rect(midleft=(self.rect.x + pad, self.rect.centery))
            surface.blit(self.icon, icon_rect)
            text_x = icon_rect.right + pad
            text_surface = font.render(self.text, True, WHITE)
            # Centre the label in the remaining horizontal space
            text_area_center_x = (text_x + self.rect.right - pad) // 2
            text_rect = text_surface.get_rect(center=(text_area_center_x, self.rect.centery))
            surface.blit(text_surface, text_rect)
        elif self.icon:
            icon_rect = self.icon.get_rect(center=self.rect.center)
            surface.blit(self.icon, icon_rect)
        elif self.text:
            text_surface = FONT.render(self.text, True, BUTTON_TEXT)
            text_rect = text_surface.get_rect(center=self.rect.center)
            surface.blit(text_surface, text_rect)
        if self.right_text:
            cost_surface = SMALL_FONT.render(self.right_text, True, BUTTON_TEXT)
            cost_rect = cost_surface.get_rect(midright=(self.rect.right - 10, self.rect.centery))
            surface.blit(cost_surface, cost_rect)
        if self.left_text:
            # Hotkey pill: small dark badge with the key letter
            pad = 8
            hk_surface = SMALL_FONT.render(self.left_text, True, WHITE)
            badge_w = hk_surface.get_width() + 10
            badge_h = hk_surface.get_height() + 4
            badge_rect = pygame.Rect(self.rect.x + pad, self.rect.centery - badge_h // 2, badge_w, badge_h)
            pygame.draw.rect(surface, (30, 30, 30), badge_rect, border_radius=4)
            pygame.draw.rect(surface, WHITE, badge_rect, 1, border_radius=4)
            surface.blit(hk_surface, hk_surface.get_rect(center=badge_rect.center))

    def update(self, mouse_pos):
        self.hover = self.rect.collidepoint(mouse_pos)

    def click(self):
        if self.action:
            self.action()


class GameGUI:
    CLASS_OPTIONS = ['T', 'P', 'K', 'TH', 'B', 'A']
    CLASS_NAMES = {'T': 'Thug', 'P': 'Priest', 'K': 'Knight', 'TH': 'Thief', 'B': 'Berserker', 'A': 'Assassin'}
    SCENARIOS = [
        {"name": "Midnight Assassination", "player": ['A', 'A', 'A'], "enemy": ['K', 'K', 'K']},
        {"name": "Holy Crusade",           "player": ['K', 'P', 'K'], "enemy": ['B', 'B', 'B']},
        {"name": "Riot in the Capitol",        "player": ['K', 'K', 'K'], "enemy": ['T', 'T', 'T', 'T', 'T']},
    ]

    def __init__(self):
        # Window/taskbar icon — must be set before set_mode on Windows for the
        # taskbar to pick it up. Falls through silently if the image is missing.
        try:
            _icon_raw = pygame.image.load(_resource_path(os.path.join("images", "game.png")))
            pygame.display.set_icon(pygame.transform.smoothscale(_icon_raw, (32, 32)))
        except Exception:
            pass
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("FRAY")
        self.clock = pygame.time.Clock()
        self.battle = Battle()
        self.message_log = []
        self.running = True
        self.game_over = False
        self.selected_ability = None
        self.target_buttons = []
        self.action_buttons = []
        self.selection_buttons = []
        self.start_button = None
        self.ai_toggle_button = None
        self.current_unit = None
        self.available_targets = None
        self.hotkey_abilities = []
        # Damage/heal splash + animated bar state
        self.unit_last_hp = {}     # id(unit) -> HP at last frame
        self.unit_display_hp = {}  # id(unit) -> current animated HP
        self.unit_display_mp = {}  # id(unit) -> current animated MP
        self.hp_splashes = []      # list of dicts: unit, amount, color, spawn_t, y_off
        self.shake_state = {}      # id(unit) -> {spawn_t, duration}
        self.nudge_state = {}      # id(unit) -> {spawn_t, duration}
        # Per-unit ordered list of pill anim entries: {"status", "stacks", "phase", "start_t"}.
        # phase in {"in", "steady", "out"}; "out" pills stay in the list until fade completes.
        self.pill_states = {}
        self._last_frame_t = time.time()
        self.card_rects = []
        self.hovered_ability_button = None
        self.hovered_ability_info = {}
        self.cancel_target_button = None
        self.active_scenario = None
        self.scenario_buttons = []
        self.remove_slot_buttons = []
        self.add_slot_buttons = {}
        self.ai_targeted_units = []
        self.ai_pending_targets = None
        self.action_locked = False
        self._pending_hit_sound = None
        self.current_team = 0
        self.current_index = 0
        self.info_text = "Select your team and enemy team to begin."
        self.state = 'team_select'
        self.player_team = ['K', 'P', 'TH']
        self.enemy_team = ['T', 'T', 'T']
        self.enemy_ai_enabled = True
        self.log_scroll = 0
        self.unit_portraits = self.load_unit_portraits()
        self.scenario_images = {}
        self.scenario_images_fullscreen = {}
        self.scenario_preview_image = None
        self.scenario_preview_image_fullscreen = None
        self.load_scenario_images()
        self.sounds = {}
        self.load_sounds()
        self.unit_effect_rects = {}  # (unit, status) -> pill Rect
        self.unit_effect_area_rects = {}  # unit -> bounding Rect of all pills
        self.unit_header_rects = {}  # unit -> bounding Rect of avatar + name
        self.effect_tooltip_map = {
            attrs.get("EFFECT_STATUS"): attrs.get("EFFECT_TOOLTIP")
            for attrs in Ability.AbilitiesDict.values()
            if attrs.get("EFFECT_STATUS") and attrs.get("EFFECT_TOOLTIP")
        }
        # Effect statuses that prevent a unit from acting (stun / sleep / etc.)
        self._incap_statuses = {
            attrs["EFFECT_STATUS"]
            for attrs in Ability.AbilitiesDict.values()
            if attrs.get("PREVENTS_ACTION") and attrs.get("EFFECT_STATUS")
        }
        # Ability names sorted longest-first so multi-word matches (e.g. "Sword slash")
        # win over partial single-word matches inside the same phrase.
        self._ability_name_patterns = [
            re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)")
            for name in sorted(Ability.AbilitiesDict.keys(), key=len, reverse=True)
        ]
        self._bgm_folder = None
        self.original_print = builtins.print
        builtins.print = self._print_and_log
        self.setup_team_selection()
        self.game_over_buttons = []
        self._setup_game_over_buttons()
        self.paused = False
        self.pause_buttons = []
        self._setup_pause_buttons()
        self.quit_confirm = False
        self.quit_buttons = []
        self._setup_quit_buttons()
        # Settings
        self.settings_open = False
        self.settings_tab = 'visual'   # 'visual' | 'audio'
        self.bgm_volume = 0.5
        self.sfx_volume = 1.0
        self.fps = 30
        self.fullscreen = False
        self._dragging_slider = None   # 'bgm' | 'sfx' | None
        self.settings_button = None
        self.settings_tab_buttons = []
        self._settings_close_btn = None
        self._settings_fullscreen_btn = None
        self._settings_fps_btn = None
        self._slider_rects = {}        # updated each frame by draw_settings_overlay
        self._setup_settings_ui()
        self.play_bgm('selection')

    def create_fallback_portrait(self):
        fallback = pygame.Surface((44, 44), pygame.SRCALPHA)
        fallback.fill((180, 180, 180, 255))
        pygame.draw.line(fallback, BLACK, (6, 6), (28, 28), 3)
        pygame.draw.line(fallback, BLACK, (28, 6), (6, 28), 3)
        return fallback

    def load_scenario_images(self):
        scenarios_dir = _resource_path(os.path.join("images", "scenarios"))
        # Per-scenario current image index (which variant to show).
        self.scenario_image_index = {s["name"]: 0 for s in self.SCENARIOS}
        # Precompute the shared "fullscreen" dimensions once.
        playfield_w = WIDTH - 2 * (BATTLE_COLUMN_PAD + BATTLE_COLUMN_W + ACTION_BTN_GAP + ACTION_BTN_W)
        playfield_w = max(playfield_w, 600)
        full_w = int(playfield_w * 0.95)
        full_h = int((HEIGHT - LOG_BOX_H - LOG_BOX_MARGIN_BOTTOM - 60) * 0.95)
        for scenario in self.SCENARIOS:
            base = scenario["name"].lower().replace(" ", "_")
            # Look for base.png, base2.png, base3.png, ... — stop at the first missing one.
            small_variants = []
            full_variants = []
            suffix_i = 0
            while True:
                filename = f"{base}.png" if suffix_i == 0 else f"{base}{suffix_i + 1}.png"
                path = os.path.join(scenarios_dir, filename)
                if not os.path.isfile(path):
                    break
                try:
                    img = pygame.image.load(path).convert_alpha()
                    small = pygame.transform.smoothscale(img, (1100, 800))
                    small = self._apply_fade_mask(small)
                    small_variants.append(small)
                    full = pygame.transform.smoothscale(img, (full_w, full_h))
                    full = self._apply_fade_mask(full, corner_radius=30, fade_width=50)
                    full_variants.append(full)
                except Exception:
                    break
                suffix_i += 1
            if small_variants:
                self.scenario_images[scenario["name"]] = small_variants
                self.scenario_images_fullscreen[scenario["name"]] = full_variants

    def _apply_fade_mask(self, img, corner_radius=120, fade_width=120):
        iw, ih = img.get_size()
        mask = pygame.Surface((iw, ih), pygame.SRCALPHA)
        mask.fill((0, 0, 0, 0))
        # Draw concentric rounded rects, largest first (low alpha) to smallest last (high alpha).
        # Each pixel ends up with the alpha of the last rect that covers it, which is the
        # rect whose inset matches that pixel's distance from the nearest edge.
        for inset in range(1, fade_width + 1):
            alpha = int(255 * inset / fade_width)
            rect = pygame.Rect(inset, inset, iw - inset * 2, ih - inset * 2)
            if rect.width > 0 and rect.height > 0:
                pygame.draw.rect(mask, (255, 255, 255, alpha), rect, border_radius=corner_radius)
        result = img.copy()
        result.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return result

    def load_unit_portraits(self):
        portraits_dir = _resource_path(os.path.join("images", "portraits"))
        mapping = {
            "Thug": "thug.png",
            "Knight": "knight.png",
            "Thief": "thief.png",
            "Priest": "priest.png",
            "Berserker": "berserker.png",
            "Assassin": "assassin.png",
        }
        portraits = {}
        fallback = self.create_fallback_portrait()
        for class_name, file_name in mapping.items():
            portrait_path = os.path.join(portraits_dir, file_name)
            try:
                image = pygame.image.load(portrait_path).convert_alpha()
                portraits[class_name] = pygame.transform.scale(image, (44, 44))
            except Exception:
                portraits[class_name] = fallback
        return portraits

    def play_bgm(self, folder):
        bgm_dir = _resource_path(os.path.join("sounds", "bgm", folder))
        if not os.path.isdir(bgm_dir):
            return
        tracks = [f for f in os.listdir(bgm_dir) if f.lower().endswith(('.mp3', '.ogg', '.wav'))]
        if not tracks:
            return
        self._bgm_folder = folder
        track = os.path.join(bgm_dir, random.choice(tracks))
        pygame.mixer.music.load(track)
        pygame.mixer.music.set_volume(self.bgm_volume)
        pygame.mixer.music.set_endevent(MUSIC_END_EVENT)
        pygame.mixer.music.play()

    def load_sounds(self):
        sounds_dir = _resource_path(os.path.join("sounds", "effects"))
        for ability_name, attrs in Ability.AbilitiesDict.items():
            cast_sound = attrs.get("CAST_SOUND") if isinstance(attrs, dict) else None
            if cast_sound:
                path = os.path.join(sounds_dir, cast_sound)
                try:
                    self.sounds[ability_name] = pygame.mixer.Sound(path)
                except Exception:
                    pass
        for name, filename in (("hit_sharp_no_dmg", "hit_sharp_no_dmg.mp3"), ("hit_sharp_light", "hit_sharp_light.mp3"), ("hit_sharp_medium", "hit_sharp_medium.mp3"), ("hit_sharp_heavy", "hit_sharp_heavy.mp3"),
                               ("hit_blunt_no_dmg", "hit_blunt_no_dmg.mp3"), ("hit_blunt_light", "hit_blunt_light.mp3"), ("hit_blunt_medium", "hit_blunt_medium.mp3"), ("hit_blunt_heavy", "hit_blunt_heavy.mp3"),
                               ("hit_magic_no_dmg", "hit_magic_no_dmg.mp3"), ("hit_magic_light", "hit_magic_light.mp3"), ("hit_magic_medium", "hit_magic_medium.mp3"), ("hit_magic_heavy", "hit_magic_heavy.mp3"),
                               ("miss", "miss.wav"),
                               ("poison_tick", "poison_tick.mp3")):
            path = os.path.join(sounds_dir, filename)
            try:
                self.sounds[name] = pygame.mixer.Sound(path)
            except Exception:
                pass
        menu_click_path = _resource_path(os.path.join("sounds", "menu_click.mp3"))
        try:
            self.sounds["menu_click"] = pygame.mixer.Sound(menu_click_path)
        except Exception:
            pass

    def get_portrait_for_unit(self, unit):
        class_name = getattr(type(unit), "className", "Thug")
        return self.unit_portraits.get(class_name, self.create_fallback_portrait())

    def setup_game(self):
        Unit.remove_all()
        self.battle = Battle()
        Unit.player_name = "Hero"
        _class_map = {'K': Unit_Knight, 'P': Unit_Priest, 'TH': Unit_Thief, 'B': Unit_Berserker, 'A': Unit_Assassin, 'T': Unit_Thug}
        _used_names = set()

        def pick_name(unit_cls):
            available = [n for n in unit_cls.name_pool if n not in _used_names]
            if not available:
                available = unit_cls.name_pool
            name = random.choice(available)
            _used_names.add(name)
            return name

        for class_key in self.player_team:
            unit_cls = _class_map.get(class_key, Unit)
            unit_cls(pick_name(unit_cls), 0)

        for class_key in self.enemy_team:
            unit_cls = _class_map.get(class_key, Unit)
            unit_cls(pick_name(unit_cls), 1)

        self.message_log.clear()
        self.log_scroll = 0
        # Reset splash + bar-animation state so trackers don't reference stale unit ids
        self.unit_last_hp.clear()
        self.unit_display_hp.clear()
        self.unit_display_mp.clear()
        self.hp_splashes.clear()
        self.shake_state.clear()
        self.nudge_state.clear()
        self.pill_states.clear()
        Ability._combat_events.clear()
        self._last_frame_t = time.time()
        self.log("Battle begins!")

    def setup_team_selection(self):
        MAX_TEAM = 5
        P_X, E_X = SEL_P_X, SEL_E_X
        SLOT_W, SLOT_H, SLOT_SPACING, SLOT_Y = SEL_SLOT_W, SEL_SLOT_H, SEL_SLOT_SPACING, 180

        self.selection_buttons.clear()
        self.remove_slot_buttons = []
        self.add_slot_buttons = {}

        # Squarish START button — battle.png at the top, "START" label beneath, gold fill.
        START_W, START_H = 160, 180
        start_rect = (WIDTH - START_W - 60, HEIGHT - START_H - 60, START_W, START_H)
        start_icon = None
        try:
            _raw = pygame.image.load(_resource_path(os.path.join("images", "battle.png"))).convert_alpha()
            icon_size = 110
            start_icon = pygame.transform.smoothscale(_raw, (icon_size, icon_size))
        except Exception:
            start_icon = None
        GOLD        = (218, 165,  32)
        GOLD_HOVER  = (240, 190,  55)
        self.start_button = Button(
            start_rect, "START", self.start_battle,
            color=GOLD, hover_color=GOLD_HOVER,
            icon=start_icon, image_stacked=True,
            label_font=TITLE_FONT,
        )
        # Rectangular Enemy AI toggle sitting above the START button, with the spartan icon on the left.
        # Colour indicates state: red when ON, grey when OFF.
        AI_W, AI_H = 240, 64
        start_x, start_y = start_rect[0], start_rect[1]
        ai_rect = (start_x + (START_W - AI_W) // 2, start_y - AI_H - 16, AI_W, AI_H)
        spartan_icon = None
        try:
            _raw_sp = pygame.image.load(_resource_path(os.path.join("images", "spartan.png"))).convert_alpha()
            _sp_size = 44
            spartan_icon = pygame.transform.smoothscale(_raw_sp, (_sp_size, _sp_size))
        except Exception:
            spartan_icon = None
        ai_color = self._ai_toggle_colors(self.enemy_ai_enabled)
        self.ai_toggle_button = Button(
            ai_rect,
            "Enemy AI",
            self.toggle_enemy_ai,
            color=ai_color[0], hover_color=ai_color[1],
            icon=spartan_icon, icon_left=True,
        )

        for i in range(len(self.player_team)):
            rect = (P_X, SLOT_Y + i * SLOT_SPACING, SLOT_W, SLOT_H)
            self.selection_buttons.append(Button(rect, "", self.make_class_cycle('player', i), color=LIGHT_GRAY, hover_color=(180, 180, 180)))
        for i in range(len(self.enemy_team)):
            rect = (E_X, SLOT_Y + i * SLOT_SPACING, SLOT_W, SLOT_H)
            self.selection_buttons.append(Button(rect, "", self.make_class_cycle('enemy', i), color=LIGHT_GRAY, hover_color=(180, 180, 180)))

        btn_cy_offset = (SLOT_H - 26) // 2
        if len(self.player_team) > 1:
            for i in range(len(self.player_team)):
                rect = (P_X + SLOT_W - 40, SLOT_Y + i * SLOT_SPACING + btn_cy_offset, 22, 26)
                self.remove_slot_buttons.append(Button(rect, "×", lambda i=i: self._remove_slot('player', i),
                                                       color=(190, 80, 80), hover_color=(220, 100, 100)))
        if len(self.enemy_team) > 1:
            for i in range(len(self.enemy_team)):
                rect = (E_X + SLOT_W - 40, SLOT_Y + i * SLOT_SPACING + btn_cy_offset, 22, 26)
                self.remove_slot_buttons.append(Button(rect, "×", lambda i=i: self._remove_slot('enemy', i),
                                                       color=(190, 80, 80), hover_color=(220, 100, 100)))

        if len(self.player_team) < MAX_TEAM:
            add_y = SLOT_Y + len(self.player_team) * SLOT_SPACING
            self.add_slot_buttons['player'] = Button((P_X, add_y, SLOT_W, 30), "+ Add unit",
                                                     lambda: self._add_slot('player'),
                                                     color=(80, 160, 80), hover_color=(100, 190, 100))
        if len(self.enemy_team) < MAX_TEAM:
            add_y = SLOT_Y + len(self.enemy_team) * SLOT_SPACING
            self.add_slot_buttons['enemy'] = Button((E_X, add_y, SLOT_W, 30), "+ Add unit",
                                                    lambda: self._add_slot('enemy'),
                                                    color=(80, 160, 80), hover_color=(100, 190, 100))

        self.scenario_buttons = []
        for i, scenario in enumerate(self.SCENARIOS):
            rect = (WIDTH // 2 - 150, 950 + i * 65, 300, 48)
            btn = Button(rect, scenario["name"], lambda s=scenario: self.apply_scenario(s),
                         color=(90, 110, 160), hover_color=(115, 138, 190))
            self.scenario_buttons.append(btn)

    def apply_scenario(self, scenario):
        name = scenario["name"]
        small_variants = self.scenario_images.get(name) or []
        full_variants  = self.scenario_images_fullscreen.get(name) or []
        n_variants = len(small_variants)
        if self.active_scenario is scenario:
            # Repeat click on the active scenario: swap teams AND cycle to the next image variant.
            self.player_team, self.enemy_team = self.enemy_team, self.player_team
            if n_variants > 1:
                self.scenario_image_index[name] = (self.scenario_image_index.get(name, 0) + 1) % n_variants
        else:
            self.player_team = list(scenario["player"])
            self.enemy_team = list(scenario["enemy"])
            self.active_scenario = scenario
            self.scenario_image_index[name] = 0
        idx = self.scenario_image_index.get(name, 0)
        self.scenario_preview_image             = small_variants[idx] if idx < n_variants else None
        self.scenario_preview_image_fullscreen  = full_variants[idx]  if idx < n_variants else None
        self.setup_team_selection()

    def _add_slot(self, team_type):
        team = self.player_team if team_type == 'player' else self.enemy_team
        team.append('T')
        self.active_scenario = None
        self.setup_team_selection()

    def _remove_slot(self, team_type, index):
        team = self.player_team if team_type == 'player' else self.enemy_team
        if len(team) > 1:
            team.pop(index)
            self.active_scenario = None
            self.setup_team_selection()

    def _setup_game_over_buttons(self):
        cy = self.screen.get_height() // 2
        self.game_over_buttons = [
            Button((WIDTH // 2 - 220, cy + 20, 200, 50), "Restart Battle", self.replay, color=GREEN),
            Button((WIDTH // 2 + 20, cy + 20, 200, 50), "Go to Selection", self.go_to_selection, color=BLUE),
        ]

    def _setup_pause_buttons(self):
        cx = WIDTH // 2
        cy = self.screen.get_height() // 2
        self.pause_buttons = [
            Button((cx - 110, cy + 20, 100, 44), "Yes", self.go_to_selection, color=RED),
            Button((cx + 10, cy + 20, 100, 44), "No", self.resume_battle, color=GREEN),
        ]

    def _setup_quit_buttons(self):
        cx = WIDTH // 2
        cy = HEIGHT // 2
        self.quit_buttons = [
            Button((cx - 110, cy + 10, 100, 44), "Yes", self._do_quit, color=RED),
            Button((cx + 10, cy + 10, 100, 44), "No", self._cancel_quit, color=GREEN),
        ]

    def _setup_settings_ui(self):
        try:
            _cog_raw = pygame.image.load(_resource_path(os.path.join("images", "settings-cog.png"))).convert_alpha()
            _cog_icon = pygame.transform.smoothscale(_cog_raw, (26, 26))
        except Exception:
            _cog_icon = None
        BTN_SIZE = 40
        self.settings_button = Button(
            (WIDTH - BTN_SIZE - 8, 8, BTN_SIZE, BTN_SIZE), "",
            lambda: setattr(self, 'settings_open', True),
            color=LIGHT_GRAY, hover_color=(65, 65, 65),
            icon=_cog_icon,
        )
        # Placeholder rects — real positions set each frame in draw_settings_overlay
        _r = pygame.Rect(0, 0, 1, 1)
        self.settings_tab_buttons = [
            Button(_r.copy(), "Visual", lambda: setattr(self, 'settings_tab', 'visual'), color=DARK_GRAY, hover_color=(65, 65, 65)),
            Button(_r.copy(), "Audio",  lambda: setattr(self, 'settings_tab', 'audio'),  color=DARK_GRAY, hover_color=(65, 65, 65)),
            Button(_r.copy(), "Quit",   lambda: setattr(self, 'settings_tab', 'quit'),   color=DARK_GRAY, hover_color=(65, 65, 65)),
        ]
        self._settings_close_btn      = Button(_r.copy(), "X", lambda: setattr(self, 'settings_open', False), color=(160, 40, 40), hover_color=(200, 60, 60))
        self._settings_fullscreen_btn = Button(_r.copy(), "", self._toggle_fullscreen, color=DARK_GRAY, hover_color=(65, 65, 65))
        self._settings_fps_btn        = Button(_r.copy(), "", self._toggle_fps,        color=DARK_GRAY, hover_color=(65, 65, 65))
        self._settings_quit_sel_btn   = Button(_r.copy(), "Quit to Selection", self._settings_do_quit_to_sel, color=(160, 100, 30), hover_color=(200, 130, 40))
        self._settings_quit_game_btn  = Button(_r.copy(), "Quit Game",         self._do_quit,                color=(160, 40,  40), hover_color=(200, 60,  60))
        self._slider_rects = {}

    def _settings_do_quit_to_sel(self):
        self.settings_open = False
        self.go_to_selection()

    def _toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        flags = pygame.FULLSCREEN if self.fullscreen else 0
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
        self._setup_settings_ui()
        self._setup_game_over_buttons()
        self._setup_pause_buttons()
        self._setup_quit_buttons()

    def _toggle_fps(self):
        self.fps = 60 if self.fps == 30 else 30

    def draw_settings_overlay(self):
        # Dark backdrop
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))

        # Modal box
        BOX_W, BOX_H = 500, 360
        cx, cy = WIDTH // 2, HEIGHT // 2
        box = pygame.Rect(cx - BOX_W // 2, cy - BOX_H // 2, BOX_W, BOX_H)
        pygame.draw.rect(self.screen, DARK_GRAY, box, border_radius=12)
        pygame.draw.rect(self.screen, LIGHT_GRAY, box, width=2, border_radius=12)

        # Title bar — cog icon + "Settings" text
        title_surf = TITLE_FONT.render("Settings", True, WHITE)
        title_y = box.y + 14
        cog_icon = getattr(self.settings_button, 'icon', None)
        if cog_icon:
            cog_scaled = pygame.transform.smoothscale(cog_icon, (TITLE_FONT.get_linesize(), TITLE_FONT.get_linesize()))
            self.screen.blit(cog_scaled, (box.x + 20, title_y))
            self.screen.blit(title_surf, (box.x + 20 + cog_scaled.get_width() + 8, title_y))
        else:
            self.screen.blit(title_surf, (box.x + 20, title_y))

        # Close button (✕)
        close_rect = pygame.Rect(box.right - 46, box.y + 10, 34, 34)
        self._settings_close_btn.rect = close_rect
        mouse_pos = pygame.mouse.get_pos()
        self._settings_close_btn.update(mouse_pos)
        self._settings_close_btn.draw(self.screen)

        # Tab row
        TAB_Y = box.y + 54
        TAB_H = 36
        TAB_PAD_X = 4
        tab_w = BOX_W // 3
        tab_labels = ['visual', 'audio', 'quit']
        for i, (btn, label) in enumerate(zip(self.settings_tab_buttons, tab_labels)):
            tab_rect = pygame.Rect(box.x + i * tab_w + TAB_PAD_X, TAB_Y, tab_w - TAB_PAD_X * 2, TAB_H)
            btn.rect = tab_rect
            active = (self.settings_tab == label)
            fill = BLUE if active else DARK_GRAY
            hover_fill = (90, 150, 200) if active else (65, 65, 65)
            btn.color = fill
            btn.hover_color = hover_fill
            btn.update(mouse_pos)
            btn.draw(self.screen)
        # Tab underline
        pygame.draw.line(self.screen, LIGHT_GRAY, (box.x, TAB_Y + TAB_H), (box.right, TAB_Y + TAB_H), 1)

        # Content area
        CONTENT_Y = TAB_Y + TAB_H + 20
        CONTENT_X = box.x + 30
        ROW_H = 52
        BTN_W, BTN_H = 200, 36

        if self.settings_tab == 'visual':
            # --- Fullscreen toggle ---
            fs_label = FONT.render("Fullscreen", True, WHITE)
            self.screen.blit(fs_label, (CONTENT_X, CONTENT_Y + 8))
            fs_btn_rect = pygame.Rect(box.right - 30 - BTN_W, CONTENT_Y, BTN_W, BTN_H)
            self._settings_fullscreen_btn.rect = fs_btn_rect
            self._settings_fullscreen_btn.text = "ON" if self.fullscreen else "OFF"
            self._settings_fullscreen_btn.color = GREEN if self.fullscreen else (100, 100, 100)
            self._settings_fullscreen_btn.hover_color = (100, 210, 140) if self.fullscreen else (130, 130, 130)
            self._settings_fullscreen_btn.update(mouse_pos)
            self._settings_fullscreen_btn.draw(self.screen)

            # --- FPS toggle ---
            fps_label = FONT.render("FPS Cap", True, WHITE)
            self.screen.blit(fps_label, (CONTENT_X, CONTENT_Y + ROW_H + 8))
            fps_btn_rect = pygame.Rect(box.right - 30 - BTN_W, CONTENT_Y + ROW_H, BTN_W, BTN_H)
            self._settings_fps_btn.rect = fps_btn_rect
            self._settings_fps_btn.text = f"{self.fps} FPS"
            self._settings_fps_btn.color = DARK_GRAY
            self._settings_fps_btn.hover_color = (65, 65, 65)
            self._settings_fps_btn.update(mouse_pos)
            self._settings_fps_btn.draw(self.screen)

        elif self.settings_tab == 'audio':
            TRACK_W, TRACK_H = 260, 14
            TRACK_X = box.right - 30 - TRACK_W

            for i, (key, label, volume) in enumerate([
                ('bgm', 'Music Volume', self.bgm_volume),
                ('sfx', 'SFX Volume',   self.sfx_volume),
            ]):
                row_y = CONTENT_Y + i * ROW_H
                # Label
                lbl_surf = FONT.render(label, True, WHITE)
                self.screen.blit(lbl_surf, (CONTENT_X, row_y + 8))
                # Percentage
                pct_surf = SMALL_FONT.render(f"{int(volume * 100)}%", True, LIGHT_GRAY)
                self.screen.blit(pct_surf, (TRACK_X - 46, row_y + 10))
                # Track background
                track_rect = pygame.Rect(TRACK_X, row_y + (ROW_H - TRACK_H) // 2, TRACK_W, TRACK_H)
                pygame.draw.rect(self.screen, (70, 70, 70), track_rect, border_radius=7)
                # Filled portion
                fill_w = max(0, int(TRACK_W * volume))
                if fill_w > 0:
                    fill_rect = pygame.Rect(track_rect.x, track_rect.y, fill_w, TRACK_H)
                    pygame.draw.rect(self.screen, BLUE, fill_rect, border_radius=7)
                # Handle circle
                handle_x = track_rect.x + fill_w
                pygame.draw.circle(self.screen, WHITE, (handle_x, track_rect.centery), 9)
                pygame.draw.circle(self.screen, BLUE,  (handle_x, track_rect.centery), 7)
                self._slider_rects[key] = track_rect

        elif self.settings_tab == 'quit':
            QUIT_BTN_W, QUIT_BTN_H = BOX_W - 60, 48
            # Quit to Selection
            qs_rect = pygame.Rect(box.x + 30, CONTENT_Y, QUIT_BTN_W, QUIT_BTN_H)
            self._settings_quit_sel_btn.rect = qs_rect
            if self.state == 'team_select':
                # Already on selection — grey out
                self._settings_quit_sel_btn.color       = (80, 80, 80)
                self._settings_quit_sel_btn.hover_color = (80, 80, 80)
            else:
                self._settings_quit_sel_btn.color       = (160, 100, 30)
                self._settings_quit_sel_btn.hover_color = (200, 130, 40)
            self._settings_quit_sel_btn.update(mouse_pos)
            self._settings_quit_sel_btn.draw(self.screen)
            # Quit Game
            qg_rect = pygame.Rect(box.x + 30, CONTENT_Y + QUIT_BTN_H + 16, QUIT_BTN_W, QUIT_BTN_H)
            self._settings_quit_game_btn.rect = qg_rect
            self._settings_quit_game_btn.update(mouse_pos)
            self._settings_quit_game_btn.draw(self.screen)

    def _apply_slider(self, key, mouse_x):
        track = self._slider_rects.get(key)
        if not track:
            return
        ratio = max(0.0, min(1.0, (mouse_x - track.left) / track.width))
        if key == 'bgm':
            self.bgm_volume = ratio
            pygame.mixer.music.set_volume(ratio)
        elif key == 'sfx':
            self.sfx_volume = ratio
            for snd in self.sounds.values():
                snd.set_volume(ratio)

    def _do_quit(self):
        self.running = False

    def _cancel_quit(self):
        self.quit_confirm = False

    def draw_quit_overlay(self):
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))
        cx = WIDTH // 2
        cy = HEIGHT // 2
        box_w, box_h = 300, 150
        box_rect = pygame.Rect(cx - box_w // 2, cy - box_h // 2, box_w, box_h)
        pygame.draw.rect(self.screen, DARK_GRAY, box_rect, border_radius=10)
        pygame.draw.rect(self.screen, LIGHT_GRAY, box_rect, width=2, border_radius=10)
        title_surf = TITLE_FONT.render("Quit game?", True, WHITE)
        self.screen.blit(title_surf, (cx - title_surf.get_width() // 2, box_rect.y + 18))
        mouse_pos = pygame.mouse.get_pos()
        for button in self.quit_buttons:
            button.update(mouse_pos)
            button.draw(self.screen)

    def resume_battle(self):
        self.paused = False

    def replay(self):
        self.start_battle()

    def go_to_selection(self):
        self.game_over = False
        self.paused = False
        self.state = 'team_select'
        # self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
        self._setup_game_over_buttons()
        self._setup_pause_buttons()
        self.setup_team_selection()
        self.play_bgm('selection')

    def make_class_cycle(self, team_type, index):
        def action():
            if team_type == 'player':
                team = self.player_team
            else:
                team = self.enemy_team
            current = team[index]
            next_index = (self.CLASS_OPTIONS.index(current) + 1) % len(self.CLASS_OPTIONS)
            team[index] = self.CLASS_OPTIONS[next_index]
            self.active_scenario = None
        return action

    def _ai_toggle_colors(self, enabled):
        """Returns (color, hover_color) for the AI toggle: red when ON, grey when OFF."""
        if enabled:
            return ((170, 50, 50), (205, 75, 75))
        return ((90, 90, 90), (115, 115, 115))

    def toggle_enemy_ai(self):
        self.enemy_ai_enabled = not self.enemy_ai_enabled
        colors = self._ai_toggle_colors(self.enemy_ai_enabled)
        self.ai_toggle_button.color, self.ai_toggle_button.hover_color = colors

    def start_battle(self):
        self.setup_game()
        self.state = 'battle'
        # self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
        self._setup_game_over_buttons()
        self._setup_pause_buttons()
        self.play_bgm('battle')
        self.current_team = 0
        self.current_index = 0
        self.current_unit = None
        self.game_over = False
        self.message_log.clear()
        self.log("Battle begins!")
        self.next_turn()

    def log(self, message):
        # timestamp = time.strftime("%H:%M:%S")
        # self.message_log.append(f"[{timestamp}] {message}")
        self.message_log.append(f"{message}")
        self.message_log = self.message_log[-50:]
        max_lines = 7
        if len(self.message_log) <= max_lines:
            self.log_scroll = 0
        else:
            self.log_scroll = min(self.log_scroll + 1, len(self.message_log) - max_lines)

    def get_winner_text(self):
        if Unit.num_units(0, "alive") == 0:
            return "Enemies win!"
        if Unit.num_units(1, "alive") == 0:
            return "Players win!"
        return ""

    def _get_incap_status(self, unit):
        """Returns the name of an incapacitating status active on the unit
        (STUN, SLEEP, ...) or None if the unit can act normally."""
        for status in unit.effect_stacks_dict:
            if status in self._incap_statuses:
                return status
        return None

    def next_turn(self):
        if self.battle.is_battle_over():
            self.game_over = True
            self.info_text = self.get_winner_text()
            return

        active_team = [u for u in Unit.get_units("all", self.current_team) if not u.dead]
        if not active_team:
            self.current_team = 1 - self.current_team
            self.current_index = 0
            active_team = [u for u in Unit.get_units("all", self.current_team) if not u.dead]

        if not active_team:
            self.game_over = True
            self.info_text = self.get_winner_text()
            return

        if self.current_index >= len(active_team):
            self.current_team = 1 - self.current_team
            self.current_index = 0
            active_team = [u for u in Unit.get_units("all", self.current_team) if not u.dead]
            if not active_team:
                self.game_over = True
                self.info_text = self.get_winner_text()
                return

        self.current_unit = active_team[self.current_index]

        if self.current_unit.downed:
            self.battle.resolve_ghost_caster_turns(self.current_unit)
            Unit.process_downed(self.battle)
            self.current_index += 1
            self.next_turn()
            return

        # Incapacitating effect (Stun / Sleep) — skip the action but still
        # tick every phase so the effect counts down and expires normally.
        incap = self._get_incap_status(self.current_unit)
        if incap:
            self.log("{} is {}!".format(str(self.current_unit), incap.lower()))
            self.battle.resolve_turn_start(self.current_unit)
            self.battle.resolve_before_action(self.current_unit)
            self.battle.resolve_after_action(self.current_unit)
            self.battle.resolve_turn_end(self.current_unit)
            Unit.process_downed(self.battle)
            time.sleep(0.4)
            self.current_index += 1
            self.next_turn()
            return

        self.current_unit_target_team = 1 - self.current_team
        self.battle.resolve_turn_start(self.current_unit)
        self.battle.resolve_before_action(self.current_unit)
        Unit.process_downed(self.battle)
        if self.battle.is_battle_over():
            self.game_over = True
            self.info_text = self.get_winner_text()
            return
        if self.current_unit not in Unit.get_units("alive", self.current_team):
            self.next_turn()
            return
        self.info_text = f"{self.current_unit} is choosing a move."
        self.selected_ability = None
        self.available_targets = None
        self.build_action_buttons()
        self.action_locked = False
        if self.current_unit.team == 1 and self.enemy_ai_enabled:
            self.execute_enemy_ai()

    def build_action_buttons(self):
        self.action_buttons.clear()
        moves = self.current_unit.movesList

        visible_team = [u for u in Unit.get_units("all", self.current_unit.team) if not u.dead]
        try:
            unit_index = visible_team.index(self.current_unit)
        except ValueError:
            unit_index = 0
        max_total = max(Unit.num_units(0, "all"), Unit.num_units(1, "all"), 1)
        v_spacing, card_w, card_h = self._get_slot_layout(max_total)
        is_player = self.current_unit.team == 0
        card_x = PLAYER_CARD_X if is_player else ENEMY_CARD_X
        col_top = self._column_top_y(len(visible_team), v_spacing, card_h)
        card_y = col_top + unit_index * v_spacing

        BTN_H = 38
        BTN_GAP = 6
        BTN_W = ACTION_BTN_W
        # Player: buttons stack to the right of the card. Enemy: to the left.
        if is_player:
            btn_x = card_x + card_w + ACTION_BTN_GAP
        else:
            btn_x = card_x - ACTION_BTN_GAP - BTN_W

        other_moves = [m for m in moves if m != "Rest"]
        has_rest = "Rest" in moves
        # Rest nearest to card (= first), then other moves below
        ordered = (["Rest"] + other_moves) if has_rest else other_moves

        self.hotkey_abilities = list(ordered)   # index → move name
        for i, move in enumerate(ordered):
            def make_action(move_name=move):
                return lambda: self.select_move(move_name)
            tooltip = ""
            mp_cost = 0
            try:
                tooltip = "\n".join(self.ability_tooltip_lines(move))
                if move != "Rest":
                    mp_cost = Ability.get_attr(move, "MP_COST") or 0
            except Exception:
                tooltip, mp_cost = "", 0
            btn_y = card_y + i * (BTN_H + BTN_GAP)
            rect = (btn_x, btn_y, BTN_W, BTN_H)
            right_text = f"MP {mp_cost}" if move != "Rest" else ""
            left_text = ABILITY_HOTKEY_LABELS[i] if i < len(ABILITY_HOTKEY_LABELS) else ""
            not_enough_mp = move != "Rest" and mp_cost > self.current_unit.mp
            btn_color = (90, 90, 90) if not_enough_mp else BUTTON_COLOR
            btn_hover = (110, 110, 110) if not_enough_mp else BUTTON_HOVER
            self.action_buttons.append(Button(rect, move, make_action(), color=btn_color,
                                            hover_color=btn_hover, tooltip=tooltip,
                                            right_text=right_text, left_text=left_text))

    def select_move(self, move_name):
        if self.game_over:
            return
        self.selected_ability = Ability(move_name, Ability.ability_ID_counter)
        if self.selected_ability.AttrValDict["MP_COST"] > self.current_unit.mp:
            self.log(f"Not enough MP for {move_name}.")
            return
        available_targets = self.selected_ability.get_valid_targets(self.current_unit)
        if not available_targets:
            self.log(f"No valid targets for {move_name}.")
            self.selected_ability = None
            return
        if self.selected_ability.AttrValDict["TARGET_TYPE"] == 1 and len(available_targets) > 1:
            self.available_targets = available_targets
            self.info_text = f"Select a target for {move_name}."
            return

        self.available_targets = None
        self.cast_selected_ability(available_targets)

    def cast_selected_ability(self, targets):
        if not self.selected_ability or not targets:
            return
        self.action_locked = True
        self._pending_hit_sound = None
        cast_snd = self.sounds.get(self.selected_ability.ABILITY_NAME)
        if cast_snd:
            cast_snd.play()
        # Nudge the caster's card toward centre briefly to sell the "cast" motion
        self.nudge_state[id(self.current_unit)] = {"spawn_t": time.time(), "duration": 0.45}
        success = self.selected_ability.initial_cast(targets, self.current_unit, self.battle)
        if success is False:
            miss_snd = self.sounds.get("miss")
            if miss_snd:
                miss_snd.play()
        else:
            dmg_type = self.selected_ability.AttrValDict.get("DMG_TYPE")
            if dmg_type:
                self._pending_hit_sound = {
                    "dmg_type": dmg_type,
                    "hit_type": self.selected_ability.AttrValDict.get("HIT_TYPE"),
                    "damage": getattr(self.selected_ability, "last_damage_dealt", 0),
                }
                pygame.time.set_timer(HIT_SOUND_EVENT, 40, loops=1)
        self.battle.resolve_after_action(self.current_unit)
        self.battle.resolve_turn_end(self.current_unit)
        Unit.process_downed(self.battle)
        self.log("")
        pygame.time.set_timer(NEXT_TURN_EVENT, 200, loops=1)

    def cancel_target_selection(self):
        self.selected_ability = None
        self.available_targets = None
        self.info_text = f"{self.current_unit} is choosing a move."

    def execute_enemy_ai(self):
        self.action_locked = True
        from ai import choose_action
        move_name, targets = choose_action(self.battle, self.current_unit)
        if not move_name or not targets:
            self.log(f"{self.current_unit} cannot act.")
            self.ai_pending_targets = []
            pygame.time.set_timer(AI_CAST_EVENT, 200, loops=1)
            return
        self.selected_ability = Ability(move_name, Ability.ability_ID_counter)
        self.ai_pending_targets = targets
        pygame.time.set_timer(AI_SHOW_EVENT, 600, loops=1)

    def _get_slot_layout(self, team_size):
        """Returns (v_spacing, card_w, card_h) for a vertical column of unit cards."""
        available_h = HEIGHT - 2 * BATTLE_COLUMN_PAD - LOG_BOX_H - LOG_BOX_MARGIN_BOTTOM
        gap = 10
        n = max(team_size, 1)
        card_h = max(90, min(170, (available_h - (n - 1) * gap) // n))
        v_spacing = card_h + gap
        return v_spacing, BATTLE_COLUMN_W, card_h

    def _get_shake_offset(self, unit):
        """Returns (dx, dy) for a shaking card. Decays from full amplitude to 0
        over the shake duration."""
        state = self.shake_state.get(id(unit))
        if not state:
            return 0, 0
        elapsed = time.time() - state["spawn_t"]
        dur = state["duration"]
        if elapsed >= dur:
            return 0, 0
        amp = 9 * (1 - elapsed / dur)   # start at ~9px, decay to 0
        # Two out-of-phase sinusoids give a scrambled shake instead of a bounce
        dx = int(math.sin(elapsed * 70.0) * amp)
        dy = int(math.cos(elapsed * 55.0) * amp * 0.5)
        return dx, dy

    def _get_nudge_offset(self, unit):
        """Returns dx for the 'lunge toward centre' motion of a casting unit.
        Player team (team 0) nudges right; enemy team (team 1) nudges left."""
        state = self.nudge_state.get(id(unit))
        if not state:
            return 0
        elapsed = time.time() - state["spawn_t"]
        dur = state["duration"]
        if elapsed >= dur:
            return 0
        t = elapsed / dur
        # Fast out, slow back: peak amount at t=0.3
        peak = 0.3
        if t < peak:
            amount = (t / peak) ** 0.6
        else:
            amount = 1.0 - ((t - peak) / (1 - peak)) ** 1.6
        direction = 1 if unit.team == 0 else -1
        return int(8 * amount * direction)

    def _column_top_y(self, team_units_visible, v_spacing, card_h):
        """Vertical origin for a team's card column — centred in the playable band."""
        top_edge = BATTLE_COLUMN_PAD
        bottom_edge = HEIGHT - LOG_BOX_H - LOG_BOX_MARGIN_BOTTOM
        n = max(team_units_visible, 1)
        total_h = (n - 1) * v_spacing + card_h
        return top_edge + max(0, (bottom_edge - top_edge - total_h) // 2)

    def draw_units(self, mouse_pos):
        player_units = [u for u in Unit.get_units("all", 0) if not u.dead]
        enemy_units = [u for u in Unit.get_units("all", 1) if not u.dead]
        max_total = max(Unit.num_units(0, "all"), Unit.num_units(1, "all"), 1)
        v_spacing, card_w, card_h = self._get_slot_layout(max_total)
        hovered_unit = None
        self.card_rects = []
        available_hover_targets = self.available_targets or []
        hovered_ability_targets = []
        self.hovered_ability_info = {}
        if self.hovered_ability_button and not self.available_targets and self.current_unit:
            hovered_ability_targets = self.get_available_targets_for_move(self.hovered_ability_button.text)
            self.hovered_ability_info = self.get_hovered_ability_info(self.hovered_ability_button.text)
        # Each team's column is centred vertically within the playable band above the log
        player_top = self._column_top_y(len(player_units), v_spacing, card_h)
        enemy_top  = self._column_top_y(len(enemy_units),  v_spacing, card_h)
        # Player team: left column, stacked top → bottom
        for index, unit in enumerate(player_units):
            shake_dx, shake_dy = self._get_shake_offset(unit)
            nudge_dx = self._get_nudge_offset(unit)
            card_x = PLAYER_CARD_X + shake_dx + nudge_dx
            card_y = player_top + index * v_spacing + shake_dy
            rect = pygame.Rect(card_x, card_y, card_w, card_h)
            fill = self.get_unit_card_fill(unit, rect, mouse_pos, hovered_ability_targets, available_hover_targets)
            self.draw_unit_card(unit, card_x, card_y, GREEN, fill, hovered_ability_targets, card_h, card_w)
            self.card_rects.append((rect, unit))
            if rect.collidepoint(mouse_pos):
                hovered_unit = unit
        # Enemy team: right column, stacked top → bottom
        for index, unit in enumerate(enemy_units):
            shake_dx, shake_dy = self._get_shake_offset(unit)
            nudge_dx = self._get_nudge_offset(unit)
            card_x = ENEMY_CARD_X + shake_dx + nudge_dx
            card_y = enemy_top + index * v_spacing + shake_dy
            rect = pygame.Rect(card_x, card_y, card_w, card_h)
            fill = self.get_unit_card_fill(unit, rect, mouse_pos, hovered_ability_targets, available_hover_targets)
            self.draw_unit_card(unit, card_x, card_y, RED, fill, hovered_ability_targets, card_h, card_w)
            self.card_rects.append((rect, unit))
            if rect.collidepoint(mouse_pos):
                hovered_unit = unit
        return hovered_unit

    def draw_unit_card(self, unit, x, y, color, fill=None, hovered_ability_targets=None, card_h=160, card_w=300):
        rect = pygame.Rect(x, y, card_w, card_h)
        fill_color = fill if fill is not None else LIGHT_GRAY
        pygame.draw.rect(self.screen, fill_color, rect, border_radius=10)
        border_color = BLACK
        if hovered_ability_targets and unit in hovered_ability_targets and self.hovered_ability_info.get("target_type") == 0:
            border_color = (255, 215, 0)
        elif unit == self.current_unit:
            border_color = BLUE
        elif hovered_ability_targets and unit in hovered_ability_targets:
            border_color = (255, 215, 0)
        elif self.available_targets and unit in self.available_targets:
            border_color = (255, 215, 0)
        if self.ai_targeted_units and unit in self.ai_targeted_units:
            border_color = RED
        pygame.draw.rect(self.screen, border_color, rect, 2, border_radius=10)

        show_avatar = card_h >= 110
        if show_avatar:
            avatar_rect = pygame.Rect(x + 10, y + 10, 48, 48)
            pygame.draw.rect(self.screen, WHITE, avatar_rect, border_radius=5)
            pygame.draw.rect(self.screen, BLACK, avatar_rect, 1, border_radius=5)
            unit_portrait = self.get_portrait_for_unit(unit)
            if unit_portrait is not None:
                self.screen.blit(unit_portrait, (x + 12, y + 12))
            name_x, name_y = x + 72, y + 16
            content_y = y + 70
        else:
            name_x, name_y = x + 10, y + 6
            content_y = y + 6 + FONT.get_linesize() + 4

        title = FONT.render(str(unit), True, BLACK)
        self.screen.blit(title, (name_x, name_y))

        # Header rect: bounding box of avatar (if shown) + name text
        if show_avatar:
            header_w = (54 + title.get_width()) - 10
            header_h = max(38, FONT.get_linesize() + 6)
            self.unit_header_rects[unit] = pygame.Rect(x + 8, y + 8, header_w + 6, header_h + 8)
        else:
            self.unit_header_rects[unit] = pygame.Rect(x + 8, y + 4, title.get_width() + 8, FONT.get_linesize() + 6)

        bar_h = max(14, min(20, card_h // 8))
        bar_w = card_w - 20
        mp_bar_width = int(bar_w * (unit.max_mp / 100))
        disp_hp = self.unit_display_hp.get(id(unit), unit.hp)
        disp_mp = self.unit_display_mp.get(id(unit), unit.mp)
        hp_ratio = disp_hp / unit.max_hp if unit.max_hp else 0
        mp_ratio = disp_mp / unit.max_mp if unit.max_mp else 0
        hp_y, mp_y = content_y, content_y + bar_h + 4
        hp_bar = pygame.Rect(x + 10, hp_y, int(bar_w * hp_ratio), bar_h)
        mp_bar = pygame.Rect(x + 10, mp_y, int(mp_bar_width * mp_ratio), bar_h)
        pygame.draw.rect(self.screen, RED, hp_bar, border_radius=2)
        pygame.draw.rect(self.screen, BLUE, mp_bar, border_radius=2)
        pygame.draw.rect(self.screen, BLACK, (x + 10, hp_y, bar_w, bar_h), 2, border_radius=2)
        pygame.draw.rect(self.screen, BLACK, (x + 10, mp_y, mp_bar_width, bar_h), 2, border_radius=2)
        self.screen.blit(SMALL_FONT.render(f"{int(round(disp_hp))}/{unit.max_hp}", True, BLACK), (x + 14, hp_y + 1))
        self.screen.blit(SMALL_FONT.render(f"{int(round(disp_mp))}/{unit.max_mp}", True, BLACK), (x + 14, mp_y + 1))
        effect_y_start = mp_y + bar_h + 6
        effect_y = effect_y_start
        pill_h = SMALL_FONT.get_linesize() + 4
        pill_pad = 4
        pill_gap = 3
        pill_x = x + 10
        # Clear old per-effect rects for this unit
        for key in [k for k in self.unit_effect_rects if k[0] is unit]:
            del self.unit_effect_rects[key]
        self.unit_effect_area_rects.pop(unit, None)
        # Iterate the animated pill list (may include entries whose stack was already
        # removed but are still fading out). Falls back to raw state on the first
        # frame before _update_pill_animations has run.
        tracked = self.pill_states.get(id(unit))
        if tracked is None:
            tracked = []
            if unit.downed:
                tracked.append({"status": "__downed__", "stacks": 1, "phase": "steady", "start_t": 0})
            for status, stacks in unit.effect_stacks_dict.items():
                tracked.append({"status": status, "stacks": stacks, "phase": "steady", "start_t": 0})
        if tracked:
            now = time.time()
            FADE = self.PILL_FADE_DUR
            drew_any = False
            for pill in tracked:
                status = pill["status"]
                is_downed = (status == "__downed__")
                display_status = "Downed" if is_downed else status
                stacks = pill["stacks"]
                label = "Downed" if is_downed else (f"{status} x{stacks}" if stacks > 1 else status)
                bg_color = (160, 40, 40) if is_downed else DARK_GRAY
                elapsed = now - pill["start_t"]
                if pill["phase"] == "in":
                    alpha = int(255 * min(1.0, elapsed / FADE))
                elif pill["phase"] == "out":
                    alpha = int(255 * max(0.0, 1.0 - elapsed / FADE))
                else:
                    alpha = 255
                if alpha <= 0:
                    continue
                text_w = SMALL_FONT.size(label)[0]
                pill_w = text_w + pill_pad * 2
                if pill_x + pill_w > x + card_w - 10:
                    pill_x = x + 10
                    effect_y += pill_h + 2
                if effect_y + pill_h > y + card_h - 2:
                    break
                # Compose the pill on an alpha surface so bg + text fade together
                pill_surf = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
                pygame.draw.rect(pill_surf, bg_color, pill_surf.get_rect(), border_radius=3)
                pill_surf.blit(SMALL_FONT.render(label, True, WHITE), (pill_pad, 2))
                pill_surf.set_alpha(alpha)
                self.screen.blit(pill_surf, (pill_x, effect_y))
                pill_rect = pygame.Rect(pill_x, effect_y, pill_w, pill_h)
                self.unit_effect_rects[(unit, display_status)] = pill_rect
                pill_x += pill_w + pill_gap
                drew_any = True
            if drew_any:
                self.unit_effect_area_rects[unit] = pygame.Rect(x + 10, effect_y_start, bar_w, effect_y + pill_h - effect_y_start)
        return rect

    # Precompiled log-highlight regexes: (pattern, colour, priority).
    # Higher priority wins on overlaps. Names get top priority so they
    # always render gold even when embedded in a damage/heal phrase.
    _LOG_PATTERNS = [
        # Damage
        (re.compile(r"\b\d+\s+(?:physical|magic)\s+damage\b", re.IGNORECASE), LOG_DMG_COLOR, 1),
        (re.compile(r"\btook\s+\d+\s+damage\b", re.IGNORECASE),               LOG_DMG_COLOR, 1),
        (re.compile(r"\brecoil damage\b", re.IGNORECASE),                     LOG_DMG_COLOR, 1),
        (re.compile(r"\bfrom (?:a )?poison(?: dart)?\b", re.IGNORECASE),      LOG_DMG_COLOR, 1),
        (re.compile(r"\bCritical hit\b"),                                     LOG_DMG_COLOR, 1),
        (re.compile(r"\bis down\b"),                                          LOG_DMG_COLOR, 1),
        # Heal
        (re.compile(r"\bhealed\s+for\s+\d+\s+health\b", re.IGNORECASE),       LOG_HEAL_COLOR, 1),
        (re.compile(r"\bwas fully healed\b", re.IGNORECASE),                  LOG_HEAL_COLOR, 1),
        (re.compile(r"\brecovered\s+\d+\s+mana\b", re.IGNORECASE),            LOG_HEAL_COLOR, 1),
        (re.compile(r"\bmana was fully restored\b", re.IGNORECASE),           LOG_HEAL_COLOR, 1),
        # Buffs
        (re.compile(r"\b(?:ATK|DEF|CRIT|DODGE|MAGIC|MP|HP)(?:[/ ][A-Za-z]+)*\s+(?:has\s+)?increased(?:\s+by\s+\d+)?"), LOG_BUFF_COLOR, 1),
        (re.compile(r"\+\d+\s*(?:ATK|DEF|CRIT|DODGE|MP|HP)\b"),               LOG_BUFF_COLOR, 1),
        # Debuffs
        (re.compile(r"\b(?:ATK|DEF|CRIT|DODGE|MAGIC|MP|HP)(?:[/ ][A-Za-z]+)*\s+(?:has\s+)?decreased(?:\s+by\s+\d+)?"), LOG_DEBUFF_COLOR, 1),
        (re.compile(r"-\d+\s*(?:ATK|DEF|CRIT|DODGE|MP|HP)\b"),                LOG_DEBUFF_COLOR, 1),
        (re.compile(r"\bis stunned\b"),                                       LOG_DEBUFF_COLOR, 1),
    ]
    _LOG_CLASS_NAME_RE = re.compile(r"\b(?:Knight|Priest|Thief|Berserker|Assassin|Thug)\s*\|\s*[A-Za-z']+")

    def _color_log_segments(self, line, unit_names):
        """Splits a log line into (text, colour) segments for coloured rendering.
        Names take priority over damage/heal/buff/debuff phrases."""
        if not line:
            return []
        n = len(line)
        colours = [LOG_TEXT] * n
        priority = [0] * n

        def paint(start, end, colour, prio):
            for i in range(start, end):
                if prio >= priority[i]:
                    colours[i] = colour
                    priority[i] = prio

        # Domain patterns (prio 1)
        for pattern, colour, prio in self._LOG_PATTERNS:
            for m in pattern.finditer(line):
                paint(m.start(), m.end(), colour, prio)
        # Ability names (prio 2)
        for pattern in self._ability_name_patterns:
            for m in pattern.finditer(line):
                paint(m.start(), m.end(), LOG_ABILITY_COLOR, 2)
        # Unit names (prio 3 — highest, so a name that clashes with an ability still reads as a name)
        for m in self._LOG_CLASS_NAME_RE.finditer(line):
            paint(m.start(), m.end(), LOG_NAME_COLOR, 3)
        for name in unit_names:
            if not name:
                continue
            for m in re.finditer(r"\b" + re.escape(name) + r"\b", line):
                paint(m.start(), m.end(), LOG_NAME_COLOR, 3)

        segments = []
        start = 0
        for i in range(1, n):
            if colours[i] != colours[start]:
                segments.append((line[start:i], colours[start]))
                start = i
        segments.append((line[start:], colours[start]))
        return segments

    def draw_info_panel(self):
        log_x = (WIDTH - LOG_BOX_W) // 2
        log_y = HEIGHT - LOG_BOX_H - LOG_BOX_MARGIN_BOTTOM
        info_rect = pygame.Rect(log_x, log_y, LOG_BOX_W, LOG_BOX_H)
        log_surface = pygame.Surface((LOG_BOX_W, LOG_BOX_H), pygame.SRCALPHA)
        log_surface.fill((LOG_BG[0], LOG_BG[1], LOG_BG[2], 170))
        self.screen.blit(log_surface, (log_x, log_y))
        pygame.draw.rect(self.screen, BLACK, info_rect, 2, border_radius=6)
        title = TITLE_FONT.render("Battle Log", True, WHITE)
        self.screen.blit(title, (log_x + LOG_BOX_W // 2 - title.get_width() // 2, log_y + 6))
        pad = 10
        header_h = TITLE_FONT.get_linesize() + 8
        visible_height = LOG_BOX_H - header_h - pad
        log_rect = pygame.Rect(log_x + pad, log_y + header_h, LOG_BOX_W - pad * 2, visible_height)
        line_height = SMALL_FONT.get_linesize()
        max_lines = visible_height // line_height
        start_index = max(0, min(self.log_scroll, max(0, len(self.message_log) - max_lines)))
        visible_logs = self.message_log[start_index:start_index + max_lines]
        # Snapshot unit names once per frame — used for gold-highlight of names
        unit_names = set()
        for team in (0, 1):
            for u in Unit.get_units("all", team):
                if u.name:
                    unit_names.add(u.name)
        for i, line in enumerate(visible_logs):
            segments = self._color_log_segments(line, unit_names)
            x_cursor = log_rect.x
            row_right = log_rect.right
            for text, colour in segments:
                if x_cursor >= row_right:
                    break
                surf = SMALL_FONT.render(text, True, colour)
                max_w = row_right - x_cursor
                if surf.get_width() > max_w:
                    surf = surf.subsurface((0, 0, max_w, surf.get_height()))
                self.screen.blit(surf, (x_cursor, log_rect.y + i * line_height))
                x_cursor += surf.get_width()
        if len(self.message_log) > max_lines:
            scroll_text = SMALL_FONT.render(f"{start_index + 1}-{min(start_index + max_lines, len(self.message_log))}/{len(self.message_log)}", True, LOG_TEXT)
            self.screen.blit(scroll_text, (log_x + LOG_BOX_W - scroll_text.get_width() - 8, log_y + 8))
        self._log_box_rect = info_rect

    def get_available_targets_for_move(self, move_name):
        if not self.current_unit:
            return []
        try:
            ability = Ability(move_name, Ability.ability_ID_counter)
        except Exception:
            return []
        return ability.get_valid_targets(self.current_unit)

    def get_hovered_ability_info(self, move_name):
        try:
            return {
                "target_type": Ability.get_attr(move_name, "TARGET_TYPE"),
                "enemy": Ability.get_attr(move_name, "TARGET_ENEMY"),
                "is_heal": bool(Ability.get_attr(move_name, "IS_HEAL")),
            }
        except Exception:
            return {}

    def get_unit_card_fill(self, unit, rect, mouse_pos, hovered_ability_targets, available_hover_targets):
        if unit.downed:
            return (90, 90, 90)
        fill_color = LIGHT_GRAY
        if hovered_ability_targets and unit in hovered_ability_targets and self.hovered_ability_info.get("target_type") == 0:
            fill_color = (255, 255, 170)
        elif unit == self.current_unit:
            fill_color = (230, 240, 255)
        if available_hover_targets and unit in available_hover_targets:
            if rect.collidepoint(mouse_pos):
                is_healing = self.selected_ability and self.selected_ability.AttrValDict.get("IS_HEAL")
                fill_color = (200, 255, 200) if is_healing else (255, 200, 200)
            else:
                fill_color = (255, 255, 170)
        elif hovered_ability_targets and unit in hovered_ability_targets:
            target_type = self.hovered_ability_info.get("target_type")
            if target_type in (2, 3, 4):
                is_healing = self.hovered_ability_info.get("is_heal")
                fill_color = (200, 255, 200) if is_healing else (255, 200, 200)
        if self.ai_targeted_units and unit in self.ai_targeted_units:
            fill_color = (255, 190, 190)
        return fill_color

    def _get_stat_modifiers(self, unit):
        """Sums each stat's applied delta across all active effects targeting this unit.
        Uses effect.sp_val (actual clamped changes) so the number matches what the
        unit's stats really shifted by, not just what EFFECT_VALUES said on paper."""
        mods = {}
        for effect in self.battle.active_effects:
            if unit not in effect.target_list:
                continue
            sp_val = getattr(effect, 'sp_val', None)
            if not isinstance(sp_val, dict):
                continue
            for stat, delta in sp_val.items():
                if delta:
                    mods[stat] = mods.get(stat, 0) + delta
        return mods

    def draw_unit_tooltip(self, unit, mouse_pos):
        mods = self._get_stat_modifiers(unit)
        # (label, stat_attr) — stat_attr matches the keys used inside EFFECT_VALUES
        left_stats  = [("ATK",    "ATK"),    ("MG ATK", "MAGIC"),     ("CRIT",  "CRIT")]
        right_stats = [("DEF",    "DEF"),    ("MG DEF", "MAGIC_DEF"), ("DODGE", "DODGE")]

        def base_text(label, stat_attr):
            return f"{label}: {getattr(unit, stat_attr)}"

        def mod_text(stat_attr):
            m = mods.get(stat_attr, 0)
            if m == 0:
                return "", None
            return (f" ({'+' if m > 0 else ''}{m})", GREEN if m > 0 else RED)

        # Measure width including any modifier suffix so both columns align consistently
        def line_width(label, stat_attr):
            base = FONT.size(base_text(label, stat_attr))[0]
            suffix, _ = mod_text(stat_attr)
            return base + (FONT.size(suffix)[0] if suffix else 0)

        padding = 8
        col_gap = 16
        line_height = FONT.get_linesize()
        col_left_w  = max(line_width(l, a) for l, a in left_stats)
        col_right_w = max(line_width(l, a) for l, a in right_stats)
        width  = padding + col_left_w + col_gap + col_right_w + padding
        height = line_height * len(left_stats) + padding * 2
        tooltip_rect = pygame.Rect(mouse_pos[0] + 16, mouse_pos[1] + 16, width, height)
        if tooltip_rect.right > WIDTH:
            tooltip_rect.right = WIDTH - 10
        if tooltip_rect.bottom > self.screen.get_height():
            tooltip_rect.bottom = self.screen.get_height() - 10
        pygame.draw.rect(self.screen, LIGHT_GRAY, tooltip_rect, border_radius=6)
        pygame.draw.rect(self.screen, BLACK, tooltip_rect, 2, border_radius=6)
        rx, ry = tooltip_rect.x + padding, tooltip_rect.y + padding

        def draw_stat_line(x, y, label, stat_attr):
            base_surf = FONT.render(base_text(label, stat_attr), True, BLACK)
            self.screen.blit(base_surf, (x, y))
            suffix, colour = mod_text(stat_attr)
            if suffix:
                self.screen.blit(FONT.render(suffix, True, colour), (x + base_surf.get_width(), y))

        for i in range(len(left_stats)):
            y = ry + i * line_height
            draw_stat_line(rx, y, *left_stats[i])
            draw_stat_line(rx + col_left_w + col_gap, y, *right_stats[i])

    def ability_tooltip_lines(self, ability_name):
        lines = []
        try:
            attrs = Ability.AbilitiesDict.get(ability_name, {})
            info = attrs.get("TOOLTIP_INFO", "")
            if info:
                lines.append(info)
            dmg_type = attrs.get("DMG_TYPE")
            if dmg_type:
                dmg_base = attrs.get("DMG_BASE", 0)
                dmg_roll = attrs.get("DMG_ROLL", 0)
                hit_type = attrs.get("HIT_TYPE")
                if dmg_type == "MAGIC":
                    base_str = "MAGIC"
                else:
                    base_str = f"ATK+{dmg_base}" if dmg_base else "ATK"
                roll_str = f"(\u00b1{dmg_roll})" if dmg_roll else ""
                hit_str = f" [{hit_type}]" if hit_type else ""
                lines.append(f"DMG: {base_str}{roll_str}{hit_str}")
            hp_gain = attrs.get("HP_GAIN", 0)
            if attrs.get("IS_HEAL") and hp_gain:
                lines.append(f"Heal: {hp_gain} HP")
            mp_gain = attrs.get("MP_GAIN", 0)
            if mp_gain:
                lines.append(f"MP: +{mp_gain}")
            effect_tooltip = attrs.get("EFFECT_TOOLTIP")
            if effect_tooltip:
                lines.append(effect_tooltip)
            ticks = attrs.get("TICKS", 0)
            if ticks:
                if ( attrs.get("EFFECT_TICKS_ON") == 0 ):
                    lines.append(f"Duration: {ticks} turns")
                if ( attrs.get("EFFECT_TICKS_ON") == 1 ):
                    lines.append(f"Duration: {ticks} hits")
                if ( attrs.get("EFFECT_TICKS_ON") == 2 ):
                    lines.append(f"Duration: {ticks} attacks")
            effect_stacks = attrs.get("EFFECT_STACKS", 0)
            if effect_stacks > 1:
                lines.append(f"Max stacks: {effect_stacks}")
        except Exception:
            pass
        return lines

    def get_hovered_effect_tooltip(self, mouse_pos):
        for (unit, status), pill_rect in self.unit_effect_rects.items():
            if pill_rect.collidepoint(mouse_pos):
                tip = self.effect_tooltip_map.get(status)
                if tip:
                    stacks = unit.effect_stacks_dict.get(status, 1)
                    return "\n".join([tip] * stacks)
        return None

    def get_hovered_ability_tooltip(self):
        if self.state != 'battle':
            return None
        for button in self.action_buttons:
            if button.hover and button.tooltip:
                return button.tooltip
        return None

    def draw_ability_tooltip(self, tooltip, mouse_pos):
        tooltip_lines = tooltip.splitlines() if tooltip else [tooltip]
        padding = 8
        line_height = FONT.get_linesize()
        width = max(FONT.size(line)[0] for line in tooltip_lines) + padding * 2
        height = line_height * len(tooltip_lines) + padding * 2
        tooltip_rect = pygame.Rect(mouse_pos[0] + 16, mouse_pos[1] + 16, width, height)
        if tooltip_rect.right > WIDTH:
            tooltip_rect.right = WIDTH - 10
        if tooltip_rect.bottom > self.screen.get_height():
            tooltip_rect.bottom = self.screen.get_height() - 10
        pygame.draw.rect(self.screen, LIGHT_GRAY, tooltip_rect, border_radius=6)
        pygame.draw.rect(self.screen, BLACK, tooltip_rect, 2, border_radius=6)
        for i, line in enumerate(tooltip_lines):
            text_surface = FONT.render(line, True, BLACK)
            self.screen.blit(text_surface, (tooltip_rect.x + padding, tooltip_rect.y + padding + i * line_height))

    def draw_selection_screen(self):
        self.screen.fill(TRUE_BLACK)
        title = TITLE_FONT.render("Team Selection", True, WHITE)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 30))
        player_title = TITLE_FONT.render("Player Team", True, WHITE)
        enemy_title = TITLE_FONT.render("Enemy Team", True, WHITE)
        self.screen.blit(player_title, (SEL_P_X + 30, 130))
        self.screen.blit(enemy_title, (SEL_E_X + 30, 130))

        mouse_pos = pygame.mouse.get_pos() if not self.quit_confirm else (-1, -1)
        for button in self.selection_buttons:
            button.update(mouse_pos)

        self.draw_team_preview(self.player_team, SEL_P_X, 180)
        self.draw_team_preview(self.enemy_team, SEL_E_X, 180)

        # info_text = "Click a slot to cycle through unit classes. Then press START BATTLE."
        # draw_text(self.screen, info_text, pygame.Rect(WIDTH // 2 - 300, 90, 600, 40), FONT, BLACK)

        scenario_label = FONT.render("— Scenarios —", True, LIGHT_GRAY)
        self.screen.blit(scenario_label, (WIDTH // 2 - scenario_label.get_width() // 2, 900))
        for button in self.scenario_buttons:
            button.update(mouse_pos)
            button.draw(self.screen)

        for button in self.remove_slot_buttons:
            button.update(mouse_pos)
            button.draw(self.screen)
        for button in self.add_slot_buttons.values():
            button.update(mouse_pos)
            button.draw(self.screen)

        self.ai_toggle_button.update(mouse_pos)
        self.ai_toggle_button.draw(self.screen)
        self.start_button.update(mouse_pos)
        self.start_button.draw(self.screen)
        if self.scenario_preview_image is not None:
            self.draw_scenario_preview()
        if self.quit_confirm:
            self.draw_quit_overlay()
        mouse_pos_s = pygame.mouse.get_pos() if not self.quit_confirm else (-1, -1)
        self.settings_button.update(mouse_pos_s)
        self.settings_button.draw(self.screen)
        if self.settings_open:
            self.draw_settings_overlay()
        pygame.display.flip()

    def draw_scenario_preview(self):
        img_rect = self.scenario_preview_image.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 100))
        self.screen.blit(self.scenario_preview_image, img_rect)

    def draw_team_preview(self, team, x, y):
        ICON_SIZE = 76
        for index, class_key in enumerate(team):
            button_index = index if x < WIDTH // 2 else len(self.player_team) + index
            button = self.selection_buttons[button_index]
            fill = button.hover_color if button.hover else button.color
            row_y = y + index * SEL_SLOT_SPACING
            card = pygame.Rect(x, row_y, SEL_SLOT_W, SEL_SLOT_H)
            pygame.draw.rect(self.screen, fill, card, border_radius=8)
            pygame.draw.rect(self.screen, BLACK, card, 2, border_radius=8)
            icon_y = row_y + (SEL_SLOT_H - ICON_SIZE) // 2
            self.draw_class_icon(class_key, x + 14, icon_y, size=ICON_SIZE)
            text_x = x + 14 + ICON_SIZE + 14
            label = TITLE_FONT.render(self.CLASS_NAMES[class_key], True, BLACK)
            self.screen.blit(label, (text_x, row_y + 22))
            detail = FONT.render("Click to change", True, DARK_GRAY)
            self.screen.blit(detail, (text_x, row_y + 52))

    def draw_class_icon(self, class_key, x, y, size=50):
        frame = pygame.Rect(x, y, size, size)
        pygame.draw.rect(self.screen, WHITE, frame, border_radius=8)
        pygame.draw.rect(self.screen, BLACK, frame, 2, border_radius=8)

        class_name = self.CLASS_NAMES.get(class_key, "Thug")
        portrait = self.unit_portraits.get(class_name, self.create_fallback_portrait())
        icon_surface = pygame.transform.smoothscale(portrait, (size - 8, size - 8))
        self.screen.blit(icon_surface, (x + 4, y + 4))

    def draw_game_over_overlay(self):
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))
        cy = self.screen.get_height() // 2
        winner_surf = TITLE_FONT.render(self.info_text, True, WHITE)
        self.screen.blit(winner_surf, (WIDTH // 2 - winner_surf.get_width() // 2, cy - 40))
        mouse_pos = pygame.mouse.get_pos()
        for button in self.game_over_buttons:
            button.update(mouse_pos)
            button.draw(self.screen)

    def draw_pause_overlay(self):
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))
        cx = WIDTH // 2
        cy = self.screen.get_height() // 2
        box_w, box_h = 320, 180
        box_rect = pygame.Rect(cx - box_w // 2, cy - 90, box_w, box_h)
        pygame.draw.rect(self.screen, DARK_GRAY, box_rect, border_radius=10)
        pygame.draw.rect(self.screen, LIGHT_GRAY, box_rect, width=2, border_radius=10)
        title_surf = TITLE_FONT.render("Quit to Selection?", True, WHITE)
        self.screen.blit(title_surf, (cx - title_surf.get_width() // 2, box_rect.y + 20))
        msg_surf = FONT.render("All battle progress will be lost.", True, LIGHT_GRAY)
        self.screen.blit(msg_surf, (cx - msg_surf.get_width() // 2, box_rect.y + 58))
        mouse_pos = pygame.mouse.get_pos()
        for button in self.pause_buttons:
            button.update(mouse_pos)
            button.draw(self.screen)

    def _update_hp_animations(self):
        """Runs once per frame: detects HP/MP changes to spawn damage/heal splashes
        and lerps the animated bar values toward the real ones."""
        now = time.time()
        dt = min(0.1, now - self._last_frame_t)  # clamp to avoid huge catch-up jumps
        self._last_frame_t = now
        # Drain queued combat events — non-damage messages (Blocked / Dodged) and
        # source-attributed damage (Poison ticks) that need their own splash colour.
        # attributed[id(unit)] is the total HP delta already accounted for by events,
        # so the generic HP-delta detector below can subtract it and only splash
        # anything left over.
        attributed = {}
        for evt in Ability._combat_events:
            kind = evt.get("kind")
            # cast_sound is target-less — plays the ability's CAST_SOUND when a
            # passive (e.g. Uproar on ally death) is triggered by Battle.
            if kind == "cast_sound":
                snd = self.sounds.get(evt.get("ability"))
                if snd:
                    snd.play()
                continue
            target = evt.get("target")
            if target is None:
                continue
            if kind == "blocked":
                self.hp_splashes.append({
                    "unit": target, "text": "Blocked", "color": (210, 210, 235),
                    "spawn_t": now, "small": True,
                })
            elif kind == "dodged":
                self.hp_splashes.append({
                    "unit": target, "text": "Dodged", "color": WHITE,
                    "spawn_t": now, "small": True,
                })
            elif kind == "poison_tick":
                amount = int(evt.get("amount", 0))
                if amount <= 0:
                    continue
                self.hp_splashes.append({
                    "unit": target, "text": f"-{amount}", "color": DARK_GREEN,
                    "spawn_t": now,
                })
                attributed[id(target)] = attributed.get(id(target), 0) - amount
                self.shake_state[id(target)] = {"spawn_t": now, "duration": 0.35}
                snd = self.sounds.get("poison_tick")
                if snd:
                    snd.play()
        Ability._combat_events.clear()
        # Walk every non-permanently-dead unit
        for team in (0, 1):
            for unit in Unit.get_units("all", team):
                if unit.dead:
                    continue
                uid = id(unit)
                actual_hp = unit.hp
                actual_mp = unit.mp
                # Splash on unattributed HP delta (poison ticks etc. already
                # spawned their own splash and reported the amount in `attributed`).
                last_hp = self.unit_last_hp.get(uid, actual_hp)
                raw_delta = actual_hp - last_hp
                remaining = raw_delta - attributed.get(uid, 0)
                if remaining != 0:
                    color = GREEN if remaining > 0 else RED
                    sign = "+" if remaining > 0 else "-"
                    self.hp_splashes.append({
                        "unit": unit,
                        "text": f"{sign}{abs(remaining)}",
                        "color": color,
                        "spawn_t": now,
                    })
                    if remaining < 0:
                        self.shake_state[uid] = {"spawn_t": now, "duration": 0.35}
                self.unit_last_hp[uid] = actual_hp
                # Lerp display values toward actual — visible drain at ~150 HP/sec (min)
                for key, actual, store in (
                    ("hp", actual_hp, self.unit_display_hp),
                    ("mp", actual_mp, self.unit_display_mp),
                ):
                    if uid not in store:
                        store[uid] = float(actual)
                        continue
                    disp = store[uid]
                    diff = actual - disp
                    if abs(diff) < 0.5:
                        store[uid] = float(actual)
                        continue
                    rate = max(150.0, unit.max_hp * 1.5) if key == "hp" else max(30.0, unit.max_mp * 1.5)
                    step = rate * dt
                    if diff > 0:
                        store[uid] = min(actual, disp + step)
                    else:
                        store[uid] = max(actual, disp - step)
        # Prune expired splashes (lifetime 1s)
        SPLASH_LIFE = 1.0
        self.hp_splashes = [s for s in self.hp_splashes if now - s["spawn_t"] < SPLASH_LIFE]

    PILL_FADE_DUR = 0.25

    def _update_pill_animations(self):
        """Mirrors each unit's effect_stacks_dict + downed flag into pill_states,
        starting fade-in animations for new pills and fade-out for removed ones.
        Fading-out pills stay in the list until the fade completes so they don't
        pop off, and re-adding one that's still fading in redirects it back to steady."""
        now = time.time()
        FADE = self.PILL_FADE_DUR
        for team in (0, 1):
            for unit in Unit.get_units("all", team):
                uid = id(unit)
                if unit.dead:
                    self.pill_states.pop(uid, None)
                    continue
                # Ground truth for this frame
                current = []
                if unit.downed:
                    current.append(("__downed__", 1))
                current.extend(unit.effect_stacks_dict.items())
                current_set = {s for s, _ in current}
                tracked = self.pill_states.setdefault(uid, [])
                tracked_set = {p["status"] for p in tracked}
                # Update existing entries: mark removed ones as fading out; refresh stacks/phase for still-present ones
                for pill in tracked:
                    status = pill["status"]
                    if status not in current_set:
                        if pill["phase"] != "out":
                            pill["phase"] = "out"
                            pill["start_t"] = now
                    else:
                        for s, n in current:
                            if s == status:
                                pill["stacks"] = n
                                break
                        if pill["phase"] == "out":
                            # Re-added mid fade-out → revert to steady (no fresh fade-in)
                            pill["phase"] = "steady"
                # Append newly-appearing pills at the end (preserves insertion order)
                for s, n in current:
                    if s not in tracked_set:
                        tracked.append({"status": s, "stacks": n, "phase": "in", "start_t": now})
                # Prune fully-faded-out entries; promote finished fade-ins to steady
                still_live = []
                for pill in tracked:
                    elapsed = now - pill["start_t"]
                    if pill["phase"] == "out" and elapsed >= FADE:
                        continue
                    if pill["phase"] == "in" and elapsed >= FADE:
                        pill["phase"] = "steady"
                    still_live.append(pill)
                tracked[:] = still_live

    def _draw_hp_splashes(self):
        """Draws floating damage/heal numbers rising from each unit's card."""
        now = time.time()
        SPLASH_LIFE = 1.0
        RISE = 55  # pixels the number floats upward over its lifetime
        # Group by unit so simultaneous hits stack rather than overlap
        by_unit = {}
        for s in self.hp_splashes:
            by_unit.setdefault(id(s["unit"]), []).append(s)
        for uid, splashes in by_unit.items():
            card_rect = next((r for r, u in self.card_rects if id(u) == uid), None)
            if not card_rect:
                continue
            # Newest at the bottom of the stack, oldest at the top
            for stack_i, s in enumerate(reversed(splashes)):
                elapsed = now - s["spawn_t"]
                if elapsed >= SPLASH_LIFE:
                    continue
                t = elapsed / SPLASH_LIFE
                alpha = int(255 * (1 - t))
                y_off = int(-RISE * t) - stack_i * 22
                font = FONT if s.get("small") else TITLE_FONT
                surf = font.render(s["text"], True, s["color"])
                # Outline for readability against any background
                outline = font.render(s["text"], True, BLACK)
                overlay = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    overlay.blit(outline, (dx, dy))
                overlay.blit(surf, (0, 0))
                overlay.set_alpha(alpha)
                r = overlay.get_rect(center=(card_rect.centerx, card_rect.top + 24 + y_off))
                self.screen.blit(overlay, r)

    def draw_target_hotkey_badges(self):
        """Draws a pulsing glowing digit next to each available target card during target selection."""
        if not self.available_targets:
            return
        # Pulse value in [0, 1] at ~2.5 Hz
        pulse = (math.sin(time.time() * 5.0) + 1) * 0.5
        for i, target in enumerate(self.available_targets):
            if i >= len(TARGET_HOTKEY_KEYS):
                break
            # Find this target's card rect
            card_rect = next((rect for rect, unit in self.card_rects if unit is target), None)
            if not card_rect:
                continue
            digit = str(i + 1)
            # Player cards are in the left column, enemies in the right column.
            # Place the badge just outside the card, on the side facing the middle of the screen.
            base_r = 22
            r = int(base_r + pulse * 4)
            if target.team == 0:
                cx = card_rect.right + base_r + 6
            else:
                cx = card_rect.left - base_r - 6
            cy = card_rect.centery
            # Glow layers on an alpha surface, then digit on top
            glow_size = (base_r + 12) * 2
            glow_surf = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
            center = (glow_size // 2, glow_size // 2)
            outer_alpha = int(60 + pulse * 90)
            inner_alpha = int(180 + pulse * 75)
            pygame.draw.circle(glow_surf, (255, 215, 0, outer_alpha), center, r + 8)
            pygame.draw.circle(glow_surf, (255, 215, 0, inner_alpha), center, r)
            pygame.draw.circle(glow_surf, (255, 255, 255, 220), center, r, 2)
            digit_surf = TITLE_FONT.render(digit, True, BLACK)
            glow_surf.blit(digit_surf, digit_surf.get_rect(center=center))
            self.screen.blit(glow_surf, (cx - glow_size // 2, cy - glow_size // 2))

    def draw_battle_screen(self):
        self.screen.fill(TRUE_BLACK)
        if self.scenario_preview_image_fullscreen is not None:
            img = self.scenario_preview_image_fullscreen
            bg_x = (WIDTH - img.get_width()) // 2
            bg_y = (HEIGHT - LOG_BOX_H - LOG_BOX_MARGIN_BOTTOM - img.get_height()) // 2
            self.screen.blit(img, (bg_x, bg_y))
        elif self.scenario_preview_image is not None:
            self.draw_scenario_preview()
        if not self.paused:
            self._update_hp_animations()
            self._update_pill_animations()
        else:
            # Keep the frame timer sane while paused so we don't lurch on resume
            self._last_frame_t = time.time()
        self.draw_buttons()
        mouse_pos = pygame.mouse.get_pos()
        hovered_unit = self.draw_units(mouse_pos)
        self._draw_hp_splashes()
        self.draw_target_hotkey_badges()
        self.draw_info_panel()
        if not self.paused:
            mouse_over_effect_area = any(r.collidepoint(mouse_pos) for r in self.unit_effect_area_rects.values())
            effect_tooltip = self.get_hovered_effect_tooltip(mouse_pos)
            if effect_tooltip:
                self.draw_ability_tooltip(effect_tooltip, mouse_pos)
            elif hovered_unit and not mouse_over_effect_area:
                header = self.unit_header_rects.get(hovered_unit)
                if header and header.collidepoint(mouse_pos):
                    self.draw_unit_tooltip(hovered_unit, mouse_pos)
            ability_tooltip = self.get_hovered_ability_tooltip()
            if ability_tooltip:
                self.draw_ability_tooltip(ability_tooltip, mouse_pos)
        if self.game_over:
            self.draw_game_over_overlay()
        elif self.paused:
            self.draw_pause_overlay()
        mouse_pos_s = pygame.mouse.get_pos() if not (self.game_over or self.paused) else (-1, -1)
        self.settings_button.update(mouse_pos_s)
        self.settings_button.draw(self.screen)
        if self.settings_open:
            self.draw_settings_overlay()
        pygame.display.flip()

    def draw_buttons(self):
        mouse_pos = pygame.mouse.get_pos()
        self.hovered_ability_button = None
        self.cancel_target_button = None
        if self.state == 'battle' and not self.game_over:
            for button in self.action_buttons:
                if not self.paused:
                    button.update(mouse_pos)
                    if button.hover:
                        self.hovered_ability_button = button
                button.draw(self.screen)

            if self.selected_ability and self.available_targets:
                selected_button = next((b for b in self.action_buttons if b.text == self.selected_ability.ABILITY_NAME), None)
                if selected_button:
                    BACK_SIZE = 30
                    GAP = 5
                    btn_cy = selected_button.rect.centery
                    bx = selected_button.rect.left + 4
                    back_rect = pygame.Rect(bx, btn_cy - BACK_SIZE // 2, BACK_SIZE, BACK_SIZE)
                    self.cancel_target_button = Button(back_rect, "X", self.cancel_target_selection, color=(200, 80, 80), hover_color=(220, 100, 100))
                    self.cancel_target_button.update(mouse_pos)
                    self.cancel_target_button.draw(self.screen)
        elif self.state == 'team_select':
            for button in self.selection_buttons:
                button.update(mouse_pos)
            self.ai_toggle_button.update(mouse_pos)
            self.ai_toggle_button.draw(self.screen)
            self.start_button.update(mouse_pos)
            self.start_button.draw(self.screen)

    def _print_and_log(self, *args, sep=" ", end="\n", file=None, flush=False, **kwargs):
        self.original_print(*args, sep=sep, end=end, file=file, flush=flush, **kwargs)
        if file is None or file is sys.stdout:
            message = sep.join(str(arg) for arg in args)
            if message:
                self.log(message)

    def cleanup(self):
        builtins.print = self.original_print
        pygame.quit()

    def run(self):
        try:
            while self.running:
                self.clock.tick(self.fps)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        if self.settings_open:
                            self.settings_open = False
                        elif self.state == 'battle' and not self.game_over and self.available_targets and not self.action_locked:
                            self.cancel_target_selection()
                        elif self.state == 'battle' and not self.game_over:
                            self.paused = not self.paused
                        elif self.state == 'team_select':
                            self.quit_confirm = not self.quit_confirm
                    # Battle hotkeys: Q/W/E/R/T/Y for abilities, 1..5 for target selection.
                    # Enemies are hotkey-controllable when their AI toggle is off.
                    is_human_turn = (
                        self.current_unit is not None
                        and (self.current_unit.team == 0 or not self.enemy_ai_enabled)
                    )
                    if (event.type == pygame.KEYDOWN
                            and self.state == 'battle'
                            and not self.paused
                            and not self.settings_open
                            and not self.game_over
                            and not self.action_locked
                            and is_human_turn):
                        if self.available_targets:
                            # Target-selection mode: only digit keys pick a target.
                            for i, key in enumerate(TARGET_HOTKEY_KEYS):
                                if event.key == key and i < len(self.available_targets):
                                    self.cast_selected_ability([self.available_targets[i]])
                                    break
                        else:
                            for i, key in enumerate(ABILITY_HOTKEY_KEYS):
                                if event.key == key and i < len(self.hotkey_abilities):
                                    self.select_move(self.hotkey_abilities[i])
                                    break
                    if event.type == MUSIC_END_EVENT:
                        if self._bgm_folder:
                            self.play_bgm(self._bgm_folder)
                    if event.type == HIT_SOUND_EVENT:
                        pygame.time.set_timer(HIT_SOUND_EVENT, 0)
                        info = self._pending_hit_sound
                        self._pending_hit_sound = None
                        if info:
                            dmg = info["damage"]
                            if dmg == 0:
                                tier = "no_dmg"
                            elif dmg <= HIT_DMG_LIGHT:
                                tier = "light"
                            elif dmg <= HIT_DMG_MEDIUM:
                                tier = "medium"
                            else:
                                tier = "heavy"
                            if tier:
                                if info["dmg_type"] == "MAGIC":
                                    key = f"hit_magic_{tier}"
                                else:
                                    hit_type = (info["hit_type"] or "blunt").lower()
                                    key = f"hit_{hit_type}_{tier}"
                                hit_snd = self.sounds.get(key)
                                if hit_snd:
                                    hit_snd.play()
                    if event.type == AI_SHOW_EVENT:
                        if self.paused:
                            pygame.time.set_timer(AI_SHOW_EVENT, 200, loops=1)
                        else:
                            pygame.time.set_timer(AI_SHOW_EVENT, 0)
                            if self.selected_ability:
                                for button in self.action_buttons:
                                    if button.text == self.selected_ability.ABILITY_NAME:
                                        button.color = RED
                                        button.hover_color = (240, 110, 110)
                                        break
                            self.ai_targeted_units = list(self.ai_pending_targets or [])
                            pygame.time.set_timer(AI_CAST_EVENT, 500, loops=1)
                    if event.type == AI_CAST_EVENT:
                        if self.paused:
                            pygame.time.set_timer(AI_CAST_EVENT, 200, loops=1)
                        else:
                            pygame.time.set_timer(AI_CAST_EVENT, 0)
                            targets = self.ai_pending_targets
                            self.ai_pending_targets = None
                            self.ai_targeted_units = []
                            if targets:
                                self.cast_selected_ability(targets)
                            else:
                                self.log("")
                                self.current_index += 1
                                self.next_turn()
                    if event.type == NEXT_TURN_EVENT:
                        if self.paused:
                            pygame.time.set_timer(NEXT_TURN_EVENT, 200, loops=1)
                        else:
                            pygame.time.set_timer(NEXT_TURN_EVENT, 0)
                            self.current_index += 1
                            self.next_turn()
                    if event.type == pygame.MOUSEMOTION and self._dragging_slider:
                        self._apply_slider(self._dragging_slider, event.pos[0])
                    if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                        self._dragging_slider = None
                    if event.type == pygame.MOUSEWHEEL and self.state == 'battle':
                        line_height = SMALL_FONT.get_linesize()
                        header_h = TITLE_FONT.get_linesize() + 8
                        max_lines = max(1, (LOG_BOX_H - header_h - 10) // line_height)
                        self.log_scroll = max(0, min(self.log_scroll - event.y, max(0, len(self.message_log) - max_lines)))
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        # ── Settings modal (intercepts all other clicks when open) ──
                        if self.settings_open:
                            if self._settings_close_btn.rect.collidepoint(event.pos):
                                self._settings_close_btn.click()
                            for btn in self.settings_tab_buttons:
                                if btn.rect.collidepoint(event.pos):
                                    btn.click()
                            if self.settings_tab == 'visual':
                                if self._settings_fullscreen_btn.rect.collidepoint(event.pos):
                                    self._settings_fullscreen_btn.click()
                                if self._settings_fps_btn.rect.collidepoint(event.pos):
                                    self._settings_fps_btn.click()
                            elif self.settings_tab == 'audio':
                                for key, track in self._slider_rects.items():
                                    if track.collidepoint(event.pos):
                                        self._dragging_slider = key
                                        self._apply_slider(key, event.pos[0])
                            elif self.settings_tab == 'quit':
                                if self._settings_quit_sel_btn.rect.collidepoint(event.pos) and self.state != 'team_select':
                                    self._settings_quit_sel_btn.click()
                                if self._settings_quit_game_btn.rect.collidepoint(event.pos):
                                    self._settings_quit_game_btn.click()
                        # ── Settings gear button ─────────────────────────────────
                        elif self.settings_button and self.settings_button.rect.collidepoint(event.pos):
                            self.settings_button.click()
                        elif self.state == 'battle':
                            if self.paused:
                                for button in self.pause_buttons:
                                    if button.rect.collidepoint(event.pos):
                                        button.click()
                            elif self.game_over:
                                for button in self.game_over_buttons:
                                    if button.rect.collidepoint(event.pos):
                                        button.click()
                            elif not self.action_locked and self.selected_ability and self.available_targets:
                                if self.cancel_target_button and self.cancel_target_button.rect.collidepoint(event.pos):
                                    self.cancel_target_button.click()
                                else:
                                    for rect, unit in self.card_rects:
                                        if rect.collidepoint(event.pos) and unit in self.available_targets:
                                            self.cast_selected_ability([unit])
                                            break
                                    else:
                                        for button in self.action_buttons:
                                            if button.rect.collidepoint(event.pos):
                                                button.click()
                            elif not self.action_locked and not self.game_over:
                                for button in self.action_buttons:
                                    if button.rect.collidepoint(event.pos):
                                        button.click()
                        elif self.state == 'team_select':
                            if self.quit_confirm:
                                for button in self.quit_buttons:
                                    if button.rect.collidepoint(event.pos):
                                        button.click()
                            else:
                                _menu_click_played = False
                                for button in self.remove_slot_buttons:
                                    if button.rect.collidepoint(event.pos):
                                        if not _menu_click_played and "menu_click" in self.sounds:
                                            self.sounds["menu_click"].play()
                                            _menu_click_played = True
                                        button.click()
                                for button in self.add_slot_buttons.values():
                                    if button.rect.collidepoint(event.pos):
                                        if not _menu_click_played and "menu_click" in self.sounds:
                                            self.sounds["menu_click"].play()
                                            _menu_click_played = True
                                        button.click()
                                for button in self.selection_buttons:
                                    if button.rect.collidepoint(event.pos):
                                        if not _menu_click_played and "menu_click" in self.sounds:
                                            self.sounds["menu_click"].play()
                                            _menu_click_played = True
                                        button.click()
                                for button in self.scenario_buttons:
                                    if button.rect.collidepoint(event.pos):
                                        if not _menu_click_played and "menu_click" in self.sounds:
                                            self.sounds["menu_click"].play()
                                            _menu_click_played = True
                                        button.click()
                                if self.ai_toggle_button.rect.collidepoint(event.pos):
                                    if not _menu_click_played and "menu_click" in self.sounds:
                                        self.sounds["menu_click"].play()
                                        _menu_click_played = True
                                    self.ai_toggle_button.click()
                                if self.start_button.rect.collidepoint(event.pos):
                                    if not _menu_click_played and "menu_click" in self.sounds:
                                        self.sounds["menu_click"].play()
                                    self.start_button.click()

                if self.state == 'team_select':
                    self.draw_selection_screen()
                else:
                    self.draw_battle_screen()
        finally:
            self.cleanup()


if __name__ == "__main__":
    try:
        GameGUI().run()
    except KeyboardInterrupt:
        pygame.quit()
        sys.exit()
