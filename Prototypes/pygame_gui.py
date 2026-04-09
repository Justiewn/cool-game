import builtins
import os
import pygame
import random
import sys
import time
from battle import Battle
from Units import Unit, Unit_Knight, Unit_Thief, Unit_Priest, Unit_Berserker, Unit_Assassin
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
DARK_GRAY = (45, 45, 45)
LIGHT_GRAY = (200, 200, 200)
BLUE = (70, 130, 180)
GREEN = (80, 190, 120)
RED = (220, 80, 80)

BUTTON_COLOR = (70, 130, 180)
BUTTON_HOVER = (90, 160, 205)
BUTTON_TEXT = WHITE
LOG_BG = (35, 35, 35)
LOG_TEXT = (230, 230, 230)
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
LOG_PANEL_W = 300
PLAYER_CARD_X = 30
CARD_W = 300
ENEMY_CARD_X = WIDTH - LOG_PANEL_W - 30 - CARD_W
# Selection layout constants
SEL_SLOT_W = 220
SEL_P_X = 80
SEL_E_X = WIDTH - 80 - SEL_SLOT_W
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
    def __init__(self, rect, text, action=None, color=BUTTON_COLOR, hover_color=BUTTON_HOVER, tooltip="", right_text=""):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.action = action
        self.color = color
        self.hover_color = hover_color
        self.tooltip = tooltip
        self.right_text = right_text
        self.hover = False

    def draw(self, surface):
        fill = self.hover_color if self.hover else self.color
        pygame.draw.rect(surface, fill, self.rect, border_radius=6)
        pygame.draw.rect(surface, BLACK, self.rect, 2, border_radius=6)
        if self.text:
            text_surface = FONT.render(self.text, True, BUTTON_TEXT)
            # if self.right_text:
            #     text_rect = text_surface.get_rect(midleft=(self.rect.x + 12, self.rect.centery))
            # else:
            text_rect = text_surface.get_rect(center=self.rect.center)
            surface.blit(text_surface, text_rect)
        if self.right_text:
            cost_surface = SMALL_FONT.render(self.right_text, True, BUTTON_TEXT)
            cost_rect = cost_surface.get_rect(midright=(self.rect.right - 10, self.rect.centery))
            surface.blit(cost_surface, cost_rect)

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
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("BEST GAME EVER - Turn-Based Battle")
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
        self.play_bgm('selection')

    def create_fallback_portrait(self):
        fallback = pygame.Surface((44, 44), pygame.SRCALPHA)
        fallback.fill((180, 180, 180, 255))
        pygame.draw.line(fallback, BLACK, (6, 6), (28, 28), 3)
        pygame.draw.line(fallback, BLACK, (28, 6), (6, 28), 3)
        return fallback

    def load_unit_portraits(self):
        portraits_dir = os.path.join(os.path.dirname(__file__), "images", "portraits")
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
        bgm_dir = os.path.join(os.path.dirname(__file__), "sounds", "bgm", folder)
        if not os.path.isdir(bgm_dir):
            return
        tracks = [f for f in os.listdir(bgm_dir) if f.lower().endswith(('.mp3', '.ogg', '.wav'))]
        if not tracks:
            return
        self._bgm_folder = folder
        track = os.path.join(bgm_dir, random.choice(tracks))
        pygame.mixer.music.load(track)
        pygame.mixer.music.set_volume(0.5)
        pygame.mixer.music.set_endevent(MUSIC_END_EVENT)
        pygame.mixer.music.play()

    def load_sounds(self):
        sounds_dir = os.path.join(os.path.dirname(__file__), "sounds", "effects")
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
                               ("miss", "miss.wav")):
            path = os.path.join(sounds_dir, filename)
            try:
                self.sounds[name] = pygame.mixer.Sound(path)
            except Exception:
                pass
        menu_click_path = os.path.join(os.path.dirname(__file__), "sounds", "menu_click.mp3")
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
        for index, class_key in enumerate(self.player_team):
            name = f"Player {index + 1}"
            if class_key == 'K':
                Unit_Knight(name, 0)
            elif class_key == 'P':
                Unit_Priest(name, 0)
            elif class_key == 'TH':
                Unit_Thief(name, 0)
            elif class_key == 'B':
                Unit_Berserker(name, 0)
            elif class_key == 'A':
                Unit_Assassin(name, 0)
            else:
                Unit(name, 0)

        for index, class_key in enumerate(self.enemy_team):
            name = f"Enemy {index + 1}"
            if class_key == 'K':
                Unit_Knight(name, 1)
            elif class_key == 'P':
                Unit_Priest(name, 1)
            elif class_key == 'TH':
                Unit_Thief(name, 1)
            elif class_key == 'B':
                Unit_Berserker(name, 1)
            elif class_key == 'A':
                Unit_Assassin(name, 1)
            else:
                Unit(name, 1)

        self.message_log.clear()
        self.log_scroll = 0
        self.log("Battle begins!")

    def setup_team_selection(self):
        MAX_TEAM = 5
        P_X, E_X = SEL_P_X, SEL_E_X
        SLOT_W, SLOT_H, SLOT_SPACING, SLOT_Y = 220, 70, 90, 180

        self.selection_buttons.clear()
        self.remove_slot_buttons = []
        self.add_slot_buttons = {}

        self.start_button = Button((WIDTH // 2 - 120, HEIGHT - 130, 240, 50), "START BATTLE", self.start_battle, color=GREEN)
        self.ai_toggle_button = Button((WIDTH // 2 - 120, HEIGHT - 190, 240, 50), f"Enemy AI: {'ON' if self.enemy_ai_enabled else 'OFF'}", self.toggle_enemy_ai, color=BLUE)

        for i in range(len(self.player_team)):
            rect = (P_X, SLOT_Y + i * SLOT_SPACING, SLOT_W, SLOT_H)
            self.selection_buttons.append(Button(rect, "", self.make_class_cycle('player', i), color=LIGHT_GRAY, hover_color=(180, 180, 180)))
        for i in range(len(self.enemy_team)):
            rect = (E_X, SLOT_Y + i * SLOT_SPACING, SLOT_W, SLOT_H)
            self.selection_buttons.append(Button(rect, "", self.make_class_cycle('enemy', i), color=LIGHT_GRAY, hover_color=(180, 180, 180)))

        btn_cy_offset = (SLOT_H - 26) // 2
        if len(self.player_team) > 1:
            for i in range(len(self.player_team)):
                rect = (P_X + SLOT_W + 4, SLOT_Y + i * SLOT_SPACING + btn_cy_offset, 22, 26)
                self.remove_slot_buttons.append(Button(rect, "×", lambda i=i: self._remove_slot('player', i),
                                                       color=(190, 80, 80), hover_color=(220, 100, 100)))
        if len(self.enemy_team) > 1:
            for i in range(len(self.enemy_team)):
                rect = (E_X - 26, SLOT_Y + i * SLOT_SPACING + btn_cy_offset, 22, 26)
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
            rect = (WIDTH // 2 - 150, 200 + i * 65, 300, 48)
            btn = Button(rect, scenario["name"], lambda s=scenario: self.apply_scenario(s),
                         color=(90, 110, 160), hover_color=(115, 138, 190))
            self.scenario_buttons.append(btn)

    def apply_scenario(self, scenario):
        if self.active_scenario is scenario:
            self.player_team, self.enemy_team = self.enemy_team, self.player_team
        else:
            self.player_team = list(scenario["player"])
            self.enemy_team = list(scenario["enemy"])
            self.active_scenario = scenario
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
            Button((cx - 110, cy + 40, 100, 44), "Yes", self.go_to_selection, color=RED),
            Button((cx + 10, cy + 40, 100, 44), "No", self.resume_battle, color=GREEN),
        ]

    def _setup_quit_buttons(self):
        cx = WIDTH // 2
        cy = HEIGHT // 2
        self.quit_buttons = [
            Button((cx - 110, cy + 30, 100, 44), "Yes", self._do_quit, color=RED),
            Button((cx + 10, cy + 30, 100, 44), "No", self._cancel_quit, color=GREEN),
        ]

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

    def toggle_enemy_ai(self):
        self.enemy_ai_enabled = not self.enemy_ai_enabled
        self.ai_toggle_button.text = f"Enemy AI: {'ON' if self.enemy_ai_enabled else 'OFF'}"

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

    def is_battle_over(self):
        return Unit.num_units(0, "alive") == 0 or Unit.num_units(1, "alive") == 0

    def get_winner_text(self):
        if Unit.num_units(0, "alive") == 0:
            return "Enemies win!"
        if Unit.num_units(1, "alive") == 0:
            return "Players win!"
        return ""

    def next_turn(self):
        if self.is_battle_over():
            self.game_over = True
            self.info_text = self.get_winner_text()
            return

        alive_team = Unit.get_units("alive", self.current_team)
        if not alive_team:
            self.current_team = 1 - self.current_team
            self.current_index = 0
            alive_team = Unit.get_units("alive", self.current_team)

        if not alive_team:
            self.game_over = True
            self.info_text = self.get_winner_text()
            return

        if self.current_index >= len(alive_team):
            self.current_team = 1 - self.current_team
            self.current_index = 0
            alive_team = Unit.get_units("alive", self.current_team)
            if not alive_team:
                self.game_over = True
                self.info_text = self.get_winner_text()
                return

        self.current_unit = alive_team[self.current_index]
        self.current_unit_target_team = 1 - self.current_team
        self.battle.resolve_turn_start(self.current_unit)
        self.battle.resolve_before_action(self.current_unit)
        Unit.downed(self.battle)
        if self.is_battle_over():
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

        alive_team = Unit.get_units("alive", self.current_unit.team)
        try:
            unit_index = alive_team.index(self.current_unit)
        except ValueError:
            unit_index = 0
        max_total = max(Unit.num_units(0, "all"), Unit.num_units(1, "all"), 1)
        spacing, card_h = self._get_slot_layout(max_total)
        card_w = spacing - 10
        screen_h = self.screen.get_height()
        is_player = self.current_unit.team == 0
        card_x = (30 + OUTER_PADDING + unit_index * spacing) if is_player else (WIDTH - LOG_PANEL_W - 30 - OUTER_PADDING - card_w - unit_index * spacing)
        card_y = (screen_h - 10 - OUTER_PADDING - card_h) if is_player else (10 + OUTER_PADDING)

        BTN_H = 38
        BTN_GAP = 5
        BTN_W = card_w

        other_moves = [m for m in moves if m != "Rest"]
        has_rest = "Rest" in moves
        # Rest nearest to card, then other moves
        ordered = (["Rest"] + other_moves) if has_rest else other_moves

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
            if is_player:
                btn_y = card_y - (i + 1) * (BTN_H + BTN_GAP)
            else:
                btn_y = card_y + card_h + BTN_GAP + i * (BTN_H + BTN_GAP)
            rect = (card_x, btn_y, BTN_W, BTN_H)
            right_text = f"MP {mp_cost}" if move != "Rest" else ""
            self.action_buttons.append(Button(rect, move, make_action(), color=BUTTON_COLOR,
                                            hover_color=BUTTON_HOVER, tooltip=tooltip,
                                            right_text=right_text))

    def select_move(self, move_name):
        if self.game_over:
            return
        self.selected_ability = Ability(move_name, Ability.ability_ID_counter)
        if self.selected_ability.AttrValDict["MP_COST"] > self.current_unit.mp:
            self.log(f"Not enough MP for {move_name}.")
            return
        available_targets = self.resolve_available_targets(self.selected_ability)
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

    def resolve_available_targets(self, ability):
        target_type = ability.AttrValDict["TARGET_TYPE"]
        enemy = ability.AttrValDict["TARGET_ENEMY"]
        if target_type == 0:
            return [self.current_unit]

        if enemy:
            team = Unit.get_units("alive", 1 - self.current_unit.team)
        else:
            team = Unit.get_units("alive", self.current_unit.team)

        if target_type in (1, 2, 3):
            if ability.ABILITY_NAME == "Finish":
                team = [u for u in team if "MARKED" in u.effect_stacks_dict]
            return team
        if target_type == 4:
            return Unit.get_units("alive", 0) + Unit.get_units("alive", 1)
        return []

    def cast_selected_ability(self, targets):
        if not self.selected_ability or not targets:
            return
        self.action_locked = True
        self._pending_hit_sound = None
        cast_snd = self.sounds.get(self.selected_ability.ABILITY_NAME)
        if cast_snd:
            cast_snd.play()
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
        Unit.downed(self.battle)
        self.log("")
        pygame.time.set_timer(NEXT_TURN_EVENT, 200, loops=1)

    def cancel_target_selection(self):
        self.selected_ability = None
        self.available_targets = None
        self.info_text = f"{self.current_unit} is choosing a move."

    def choose_ai_move(self):
        def can_use_move(move_name):
            mp_cost = Ability.get_attr(move_name, "MP_COST")
            if mp_cost > self.current_unit.mp:
                return False
            target_type = Ability.get_attr(move_name, "TARGET_TYPE")
            target_enemy = Ability.get_attr(move_name, "TARGET_ENEMY")
            if target_type == 0:
                return True
            if target_enemy:
                targets = Unit.get_units("alive", 1 - self.current_unit.team)
            else:
                targets = Unit.get_units("alive", self.current_unit.team)
            return bool(targets)

        hp_ratio = (self.current_unit.hp / self.current_unit.max_hp) if self.current_unit.max_hp else 0
        if hp_ratio >= 0.15 and len(self.current_unit.movesList) > 1:
            second_move = self.current_unit.movesList[1]
            if can_use_move(second_move):
                return second_move

        valid_moves = []
        for move in self.current_unit.movesList:
            if can_use_move(move):
                valid_moves.append(move)

        if hp_ratio < 0.15 and "Rest" in valid_moves:
            return "Rest"

        return random.choice(valid_moves) if valid_moves else None

    def execute_enemy_ai(self):
        self.action_locked = True
        move_name = self.choose_ai_move()
        if move_name is None:
            self.log(f"{self.current_unit} cannot act.")
            self.ai_pending_targets = []
            pygame.time.set_timer(AI_CAST_EVENT, 200, loops=1)
            return
        self.selected_ability = Ability(move_name, Ability.ability_ID_counter)
        available_targets = self.resolve_available_targets(self.selected_ability)
        if self.selected_ability.AttrValDict["TARGET_TYPE"] == 1 and available_targets:
            available_targets = [random.choice(available_targets)]
        self.ai_pending_targets = available_targets
        pygame.time.set_timer(AI_SHOW_EVENT, 600, loops=1)

    def _get_slot_layout(self, team_size):
        """Returns (spacing, card_h) for horizontal card layout."""
        available_w = WIDTH - LOG_PANEL_W - 60  # 30px margins each side
        gap = 10
        card_w = max(120, min(300, (available_w - (max(team_size, 1) - 1) * gap) // max(team_size, 1)))
        spacing = card_w + gap
        card_h = 170
        return spacing, card_h

    def draw_units(self, mouse_pos):
        player_units = Unit.get_units("alive", 0)
        enemy_units = Unit.get_units("alive", 1)
        max_total = max(Unit.num_units(0, "all"), Unit.num_units(1, "all"), 1)
        spacing, card_h = self._get_slot_layout(max_total)
        screen_h = self.screen.get_height()
        hovered_unit = None
        self.card_rects = []
        available_hover_targets = self.available_targets or []
        hovered_ability_targets = []
        self.hovered_ability_info = {}
        if self.hovered_ability_button and not self.available_targets and self.current_unit:
            hovered_ability_targets = self.get_available_targets_for_move(self.hovered_ability_button.text)
            self.hovered_ability_info = self.get_hovered_ability_info(self.hovered_ability_button.text)
        card_w = spacing - 10
        # Player team: bottom row, spread left to right
        player_row_y = screen_h - 10 - OUTER_PADDING - card_h
        for index, unit in enumerate(player_units):
            card_x = 30 + OUTER_PADDING + index * spacing
            rect = pygame.Rect(card_x, player_row_y, card_w, card_h)
            fill = self.get_unit_card_fill(unit, rect, mouse_pos, hovered_ability_targets, available_hover_targets)
            self.draw_unit_card(unit, card_x, player_row_y, GREEN, fill, hovered_ability_targets, card_h, card_w)
            self.card_rects.append((rect, unit))
            if rect.collidepoint(mouse_pos):
                hovered_unit = unit
        # Enemy team: top row, spread right to left
        enemy_row_y = 10 + OUTER_PADDING
        for index, unit in enumerate(enemy_units):
            card_x = WIDTH - LOG_PANEL_W - 30 - OUTER_PADDING - card_w - index * spacing
            rect = pygame.Rect(card_x, enemy_row_y, card_w, card_h)
            fill = self.get_unit_card_fill(unit, rect, mouse_pos, hovered_ability_targets, available_hover_targets)
            self.draw_unit_card(unit, card_x, enemy_row_y, RED, fill, hovered_ability_targets, card_h, card_w)
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
        hp_ratio = unit.hp / unit.max_hp if unit.max_hp else 0
        mp_ratio = unit.mp / unit.max_mp if unit.max_mp else 0
        hp_y, mp_y = content_y, content_y + bar_h + 4
        hp_bar = pygame.Rect(x + 10, hp_y, int(bar_w * hp_ratio), bar_h)
        mp_bar = pygame.Rect(x + 10, mp_y, int(mp_bar_width * mp_ratio), bar_h)
        pygame.draw.rect(self.screen, RED, hp_bar, border_radius=2)
        pygame.draw.rect(self.screen, BLUE, mp_bar, border_radius=2)
        pygame.draw.rect(self.screen, BLACK, (x + 10, hp_y, bar_w, bar_h), 2, border_radius=2)
        pygame.draw.rect(self.screen, BLACK, (x + 10, mp_y, mp_bar_width, bar_h), 2, border_radius=2)
        self.screen.blit(SMALL_FONT.render(f"{unit.hp}/{unit.max_hp}", True, BLACK), (x + 14, hp_y + 1))
        self.screen.blit(SMALL_FONT.render(f"{unit.mp}/{unit.max_mp}", True, BLACK), (x + 14, mp_y + 1))
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
        if unit.effect_stacks_dict:
            for status, stacks in unit.effect_stacks_dict.items():
                label = f"{status} x{stacks}" if stacks > 1 else status
                text_w = SMALL_FONT.size(label)[0]
                pill_w = text_w + pill_pad * 2
                if pill_x + pill_w > x + card_w - 10:
                    pill_x = x + 10
                    effect_y += pill_h + 2
                if effect_y + pill_h > y + card_h - 2:
                    break
                pill_rect = pygame.Rect(pill_x, effect_y, pill_w, pill_h)
                pygame.draw.rect(self.screen, DARK_GRAY, pill_rect, border_radius=3)
                self.screen.blit(SMALL_FONT.render(label, True, WHITE), (pill_x + pill_pad, effect_y + 2))
                self.unit_effect_rects[(unit, status)] = pill_rect
                pill_x += pill_w + pill_gap
            # bounding box covering entire pill area
            self.unit_effect_area_rects[unit] = pygame.Rect(x + 10, effect_y_start, bar_w, effect_y + pill_h - effect_y_start)
        return rect

    def draw_info_panel(self):
        log_x = WIDTH - LOG_PANEL_W
        log_h = self.screen.get_height()
        info_rect = pygame.Rect(log_x, 0, LOG_PANEL_W, log_h)
        pygame.draw.rect(self.screen, LOG_BG, info_rect)
        pygame.draw.rect(self.screen, BLACK, info_rect, 2)
        title = TITLE_FONT.render("Battle Log", True, WHITE)
        self.screen.blit(title, (log_x + LOG_PANEL_W // 2 - title.get_width() // 2, 12))
        pad = 10
        visible_height = log_h - 50
        log_rect = pygame.Rect(log_x + pad, 48, LOG_PANEL_W - pad * 2, visible_height)
        line_height = SMALL_FONT.get_linesize()
        max_lines = visible_height // line_height
        start_index = max(0, min(self.log_scroll, max(0, len(self.message_log) - max_lines)))
        visible_logs = self.message_log[start_index:start_index + max_lines]
        for i, line in enumerate(visible_logs):
            text_surface = SMALL_FONT.render(line, True, LOG_TEXT)
            clipped = text_surface.subsurface((0, 0, min(text_surface.get_width(), log_rect.width), text_surface.get_height()))
            self.screen.blit(clipped, (log_rect.x, log_rect.y + i * line_height))
        if len(self.message_log) > max_lines:
            scroll_text = SMALL_FONT.render(f"{start_index + 1}-{min(start_index + max_lines, len(self.message_log))}/{len(self.message_log)}", True, LOG_TEXT)
            self.screen.blit(scroll_text, (log_x + LOG_PANEL_W // 2 - scroll_text.get_width() // 2, log_h - line_height - 6))

    def get_available_targets_for_move(self, move_name):
        if not self.current_unit:
            return []
        try:
            ability = Ability(move_name, Ability.ability_ID_counter)
        except Exception:
            return []
        return self.resolve_available_targets(ability)

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

    def draw_unit_tooltip(self, unit, mouse_pos):
        col_left  = [f"ATK: {unit.ATK}", f"MG ATK: {unit.MAGIC}", f"CRIT: {unit.CRIT}"]
        col_right = [f"DEF: {unit.DEF}", f"MG DEF: {unit.MAGIC_DEF}", f"DODGE: {unit.DODGE}"]
        padding = 8
        col_gap = 16
        line_height = FONT.get_linesize()
        col_left_w  = max(FONT.size(l)[0] for l in col_left)
        col_right_w = max(FONT.size(l)[0] for l in col_right)
        width  = padding + col_left_w + col_gap + col_right_w + padding
        height = line_height * 3 + padding * 2
        tooltip_rect = pygame.Rect(mouse_pos[0] + 16, mouse_pos[1] + 16, width, height)
        if tooltip_rect.right > WIDTH:
            tooltip_rect.right = WIDTH - 10
        if tooltip_rect.bottom > self.screen.get_height():
            tooltip_rect.bottom = self.screen.get_height() - 10
        pygame.draw.rect(self.screen, LIGHT_GRAY, tooltip_rect, border_radius=6)
        pygame.draw.rect(self.screen, BLACK, tooltip_rect, 2, border_radius=6)
        rx, ry = tooltip_rect.x + padding, tooltip_rect.y + padding
        for i, (left, right) in enumerate(zip(col_left, col_right)):
            y = ry + i * line_height
            self.screen.blit(FONT.render(left,  True, BLACK), (rx, y))
            self.screen.blit(FONT.render(right, True, BLACK), (rx + col_left_w + col_gap, y))

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
                lines.append(f"Duration: {ticks - 1} turns")
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
                    return f"{tip}"
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
        self.screen.fill(WHITE)
        title = TITLE_FONT.render("Team Selection", True, BLACK)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 30))
        player_title = TITLE_FONT.render("Player Team", True, BLACK)
        enemy_title = TITLE_FONT.render("Enemy Team", True, BLACK)
        self.screen.blit(player_title, (SEL_P_X + 30, 130))
        self.screen.blit(enemy_title, (SEL_E_X + 30, 130))

        mouse_pos = pygame.mouse.get_pos() if not self.quit_confirm else (-1, -1)
        for button in self.selection_buttons:
            button.update(mouse_pos)

        self.draw_team_preview(self.player_team, SEL_P_X, 180)
        self.draw_team_preview(self.enemy_team, SEL_E_X, 180)

        info_text = "Click a slot to cycle through unit classes. Then press START BATTLE."
        draw_text(self.screen, info_text, pygame.Rect(WIDTH // 2 - 300, 90, 600, 40), FONT, BLACK)

        scenario_label = FONT.render("— Scenarios —", True, DARK_GRAY)
        self.screen.blit(scenario_label, (WIDTH // 2 - scenario_label.get_width() // 2, 163))
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
        if self.quit_confirm:
            self.draw_quit_overlay()
        pygame.display.flip()

    def draw_team_preview(self, team, x, y):
        for index, class_key in enumerate(team):
            button_index = index if x < WIDTH // 2 else len(self.player_team) + index
            button = self.selection_buttons[button_index]
            fill = button.hover_color if button.hover else button.color
            card = pygame.Rect(x, y + index * 90, 220, 70)
            pygame.draw.rect(self.screen, fill, card, border_radius=5)
            pygame.draw.rect(self.screen, BLACK, card, 2, border_radius=5)
            self.draw_class_icon(class_key, x + 12, y + index * 90 + 15)
            label = FONT.render(self.CLASS_NAMES[class_key], True, BLACK)
            self.screen.blit(label, (x + 75, y + index * 90 + 24))
            detail = SMALL_FONT.render("Click to change", True, DARK_GRAY)
            self.screen.blit(detail, (x + 75, y + index * 90 + 44))

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

    def draw_battle_screen(self):
        self.screen.fill(WHITE)
        self.draw_buttons()
        mouse_pos = pygame.mouse.get_pos()
        hovered_unit = self.draw_units(mouse_pos)
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
                    if self.current_unit and self.current_unit.team == 0:
                        # Player: card-closest side is the left of the ability column
                        bx = selected_button.rect.left - GAP - BACK_SIZE
                    else:
                        # Enemy: card-closest side is the right of the ability column
                        bx = selected_button.rect.right + GAP
                    back_rect = pygame.Rect(bx, btn_cy - BACK_SIZE // 2, BACK_SIZE, BACK_SIZE)
                    self.cancel_target_button = Button(back_rect, "<", self.cancel_target_selection, color=(200, 80, 80), hover_color=(220, 100, 100))
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
                self.clock.tick(FPS)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        if self.state == 'battle' and not self.game_over:
                            self.paused = not self.paused
                        elif self.state == 'team_select':
                            self.quit_confirm = not self.quit_confirm
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
                    if event.type == pygame.MOUSEWHEEL and self.state == 'battle':
                        _vis_h = self.screen.get_height() - 50
                        line_height = SMALL_FONT.get_linesize()
                        max_lines = _vis_h // line_height
                        self.log_scroll = max(0, min(self.log_scroll - event.y, max(0, len(self.message_log) - max_lines)))
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if self.state == 'battle':
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
