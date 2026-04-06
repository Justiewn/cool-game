import builtins
import os
import pygame
import random
import sys
import time
from battle import Battle
from Units import Unit, Unit_Knight, Unit_Thief, Unit_Priest, Unit_Berserker
from Abilities import Ability

# Pygame GUI for the turn-based battle prototype

WIDTH = 1100
HEIGHT = 820
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

pygame.init()
pygame.font.init()
FONT = pygame.font.SysFont("arial", 18)
TITLE_FONT = pygame.font.SysFont("arial", 24, bold=True)
SMALL_FONT = pygame.font.SysFont("arial", 14)


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
            if self.right_text:
                text_rect = text_surface.get_rect(midleft=(self.rect.x + 12, self.rect.centery))
            else:
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
    CLASS_OPTIONS = ['T', 'P', 'K', 'TH', 'B']
    CLASS_NAMES = {'T': 'Thug', 'P': 'Priest', 'K': 'Knight', 'TH': 'Thief', 'B': 'Berserker'}
    CLASS_COLORS = {'T': (180, 180, 180), 'P': (170, 120, 230), 'K': (230, 200, 120), 'TH': (120, 220, 180), 'B': (220, 100, 100)}
    CLASS_ICONS = {'T': 'T', 'P': 'P', 'K': 'K', 'TH': 'TH', 'B': 'B'}

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
        self.current_team = 0
        self.current_index = 0
        self.info_text = "Select your team and enemy team to begin."
        self.state = 'team_select'
        self.player_team = ['K', 'P', 'TH']
        self.enemy_team = ['T', 'T', 'T']
        self.enemy_ai_enabled = True
        self.log_scroll = 0
        self.unit_portraits = self.load_unit_portraits()
        self.original_print = builtins.print
        builtins.print = self._print_and_log
        self.setup_team_selection()
        self.game_over_buttons = []
        self._setup_game_over_buttons()

    def create_fallback_portrait(self):
        fallback = pygame.Surface((34, 34), pygame.SRCALPHA)
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
        }
        portraits = {}
        fallback = self.create_fallback_portrait()
        for class_name, file_name in mapping.items():
            portrait_path = os.path.join(portraits_dir, file_name)
            try:
                image = pygame.image.load(portrait_path).convert_alpha()
                portraits[class_name] = pygame.transform.scale(image, (34, 34))
            except Exception:
                portraits[class_name] = fallback
        return portraits

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
            else:
                Unit(name, 1)

        self.message_log.clear()
        self.log_scroll = 0
        self.log("Battle begins!")

    def setup_team_selection(self):
        self.selection_buttons.clear()
        self.start_button = Button((430, 620, 240, 50), "START BATTLE", self.start_battle, color=GREEN)
        self.ai_toggle_button = Button((430, 540, 240, 50), f"Enemy AI: {'ON' if self.enemy_ai_enabled else 'OFF'}", self.toggle_enemy_ai, color=BLUE)

        for i in range(len(self.player_team)):
            rect = (80, 180 + i * 90, 220, 70)
            self.selection_buttons.append(Button(rect, "", self.make_class_cycle('player', i), color=LIGHT_GRAY, hover_color=(180, 180, 180)))

        for i in range(len(self.enemy_team)):
            rect = (760, 180 + i * 90, 220, 70)
            self.selection_buttons.append(Button(rect, "", self.make_class_cycle('enemy', i), color=LIGHT_GRAY, hover_color=(180, 180, 180)))

    def _setup_game_over_buttons(self):
        self.game_over_buttons = [
            Button((330, 340, 200, 50), "Replay", self.replay, color=GREEN),
            Button((570, 340, 200, 50), "Reselect", self.go_to_selection, color=BLUE),
        ]

    def replay(self):
        self.start_battle()

    def go_to_selection(self):
        self.game_over = False
        self.state = 'team_select'
        self.setup_team_selection()

    def make_class_cycle(self, team_type, index):
        def action():
            if team_type == 'player':
                team = self.player_team
            else:
                team = self.enemy_team
            current = team[index]
            next_index = (self.CLASS_OPTIONS.index(current) + 1) % len(self.CLASS_OPTIONS)
            team[index] = self.CLASS_OPTIONS[next_index]
        return action

    def toggle_enemy_ai(self):
        self.enemy_ai_enabled = not self.enemy_ai_enabled
        self.ai_toggle_button.text = f"Enemy AI: {'ON' if self.enemy_ai_enabled else 'OFF'}"

    def start_battle(self):
        self.setup_game()
        self.state = 'battle'
        self.current_team = 0
        self.current_index = 0
        self.current_unit = None
        self.game_over = False
        self.message_log.clear()
        self.log("Battle begins!")
        self.next_turn()

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.message_log.append(f"[{timestamp}] {message}")
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
        if self.current_unit.team == 1 and self.enemy_ai_enabled:
            self.execute_enemy_ai()

    def build_action_buttons(self):
        self.action_buttons.clear()
        moves = self.current_unit.movesList
        for index, move in enumerate(moves):
            def make_action(move_name=move):
                return lambda: self.select_move(move_name)
            tooltip = ""
            mp_cost = 0
            try:
                tooltip = Ability.get_attr(move, "INFO") or ""
                mp_cost = Ability.get_attr(move, "MP_COST") or 0
            except Exception:
                tooltip = ""
                mp_cost = 0
            rect = (390, 220 + index * 60, 320, 45)
            self.action_buttons.append(Button(rect, move, make_action(), color=BUTTON_COLOR, hover_color=BUTTON_HOVER, tooltip=tooltip, right_text=f"MP {mp_cost}"))

    def select_move(self, move_name):
        if self.game_over:
            return
        self.selected_ability = Ability(move_name, Ability.ability_ID_counter)
        if self.selected_ability.AttrValDict["MP_COST"] > self.current_unit.mp:
            self.log(f"Not enough MP for {move_name}.")
            return
        available_targets = self.resolve_available_targets(self.selected_ability)
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
            return team
        if target_type == 4:
            return Unit.get_units("alive", 0) + Unit.get_units("alive", 1)
        return []

    def cast_selected_ability(self, targets):
        if not self.selected_ability or not targets:
            return
        self.selected_ability.initial_cast(targets, self.current_unit, self.battle)
        # self.log(f"{self.current_unit} used {self.selected_ability.ABILITY_NAME}.")
        # if self.selected_ability.AttrValDict["MP_COST"] > 0:
        #     self.log(f"MP remaining: {self.current_unit.mp}/{self.current_unit.max_mp}")
        self.battle.resolve_after_action(self.current_unit)
        Unit.downed(self.battle)
        if self.current_unit and self.current_unit.team == 1 and self.enemy_ai_enabled:
            self.draw_battle_screen()
            pygame.event.pump()
            time.sleep(1)
        self.log("")
        self.current_index += 1
        self.next_turn()

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
        move_name = self.choose_ai_move()
        if move_name is None:
            self.log(f"{self.current_unit} cannot act.")
            self.draw_battle_screen()
            pygame.event.pump()
            time.sleep(1)
            self.log("")
            self.current_index += 1
            self.next_turn()
            return
        self.selected_ability = Ability(move_name, Ability.ability_ID_counter)
        available_targets = self.resolve_available_targets(self.selected_ability)
        if self.selected_ability.AttrValDict["TARGET_TYPE"] == 1 and available_targets:
            available_targets = [random.choice(available_targets)]
        # self.log(f"{self.current_unit} chooses {move_name}.")
        self.cast_selected_ability(available_targets)

    def draw_units(self, mouse_pos):
        player_units = Unit.get_units("alive", 0)
        enemy_units = Unit.get_units("alive", 1)
        x_start = 30
        y_start = 30
        hovered_unit = None
        self.card_rects = []
        available_hover_targets = self.available_targets or []
        hovered_ability_targets = []
        self.hovered_ability_info = {}
        if self.hovered_ability_button and not self.available_targets and self.current_unit:
            hovered_ability_targets = self.get_available_targets_for_move(self.hovered_ability_button.text)
            self.hovered_ability_info = self.get_hovered_ability_info(self.hovered_ability_button.text)
        for index, unit in enumerate(player_units):
            rect = pygame.Rect(x_start, y_start + index * 180, 300, 160)
            fill = self.get_unit_card_fill(unit, rect, mouse_pos, hovered_ability_targets, available_hover_targets)
            self.draw_unit_card(unit, x_start, y_start + index * 180, GREEN, fill, hovered_ability_targets)
            self.card_rects.append((rect, unit))
            if rect.collidepoint(mouse_pos):
                hovered_unit = unit
        x_start = 760
        for index, unit in enumerate(enemy_units):
            rect = pygame.Rect(x_start, y_start + index * 180, 300, 160)
            fill = self.get_unit_card_fill(unit, rect, mouse_pos, hovered_ability_targets, available_hover_targets)
            self.draw_unit_card(unit, x_start, y_start + index * 180, RED, fill, hovered_ability_targets)
            self.card_rects.append((rect, unit))
            if rect.collidepoint(mouse_pos):
                hovered_unit = unit
        return hovered_unit

    def draw_unit_card(self, unit, x, y, color, fill=None, hovered_ability_targets=None):
        rect = pygame.Rect(x, y, 300, 160)
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
        pygame.draw.rect(self.screen, border_color, rect, 2, border_radius=10)

        avatar_rect = pygame.Rect(x + 10, y + 10, 38, 38)
        pygame.draw.rect(self.screen, WHITE, avatar_rect, border_radius=5)
        pygame.draw.rect(self.screen, BLACK, avatar_rect, 1, border_radius=5)
        unit_portrait = self.get_portrait_for_unit(unit)
        if unit_portrait is not None:
            self.screen.blit(unit_portrait, (x + 12, y + 12))

        title = FONT.render(str(unit), True, BLACK)
        self.screen.blit(title, (x + 54, y + 16))

        mp_bar_width = int(280 * ( unit.max_mp / 100 ))

        hp_ratio = unit.hp / unit.max_hp if unit.max_hp else 0
        mp_ratio = unit.mp / unit.max_mp if unit.max_mp else 0
        hp_bar = pygame.Rect(x + 10, y + 52, int(280 * hp_ratio), 20)
        mp_bar = pygame.Rect(x + 10, y + 76, int(mp_bar_width * mp_ratio), 20)
        pygame.draw.rect(self.screen, RED, hp_bar, border_radius=2)
        pygame.draw.rect(self.screen, BLUE, mp_bar, border_radius=2)
        pygame.draw.rect(self.screen, BLACK, (x + 10, y + 52, 280, 20), 2, border_radius=2)
        pygame.draw.rect(self.screen, BLACK, (x + 10, y + 76, mp_bar_width, 20), 2, border_radius=2)
        self.screen.blit(SMALL_FONT.render(f"{unit.hp}/{unit.max_hp}", True, BLACK), (x + 14, y + 54))
        self.screen.blit(SMALL_FONT.render(f"{unit.mp}/{unit.max_mp}", True, BLACK), (x + 14, y + 78))
        buff_text = ", ".join([f"{name} x{stacks}" if stacks > 1 else name for name, stacks in unit.buff_stacks_dict.items()])
        self.screen.blit(SMALL_FONT.render(buff_text, True, BLACK), (x + 10, y + 110))
        return rect

    def draw_info_panel(self):
        info_rect = pygame.Rect(30, 570, 1020, 180)
        pygame.draw.rect(self.screen, LOG_BG, info_rect, border_radius=10)
        pygame.draw.rect(self.screen, BLACK, info_rect, 2, border_radius=10)
        title = TITLE_FONT.render("Battle Log", True, WHITE)
        self.screen.blit(title, (40, 580))
        visible_height = 130
        log_rect = pygame.Rect(40, 610, 1000, visible_height)
        line_height = SMALL_FONT.get_linesize()
        max_lines = visible_height // line_height
        start_index = max(0, min(self.log_scroll, max(0, len(self.message_log) - max_lines)))
        visible_logs = self.message_log[start_index:start_index + max_lines]
        for i, line in enumerate(visible_logs):
            text_surface = SMALL_FONT.render(line, True, LOG_TEXT)
            self.screen.blit(text_surface, (log_rect.x, log_rect.y + i * line_height))
        if len(self.message_log) > max_lines:
            scroll_text = SMALL_FONT.render(f"Scroll: {start_index + 1}-{min(start_index + max_lines, len(self.message_log))} of {len(self.message_log)}", True, LOG_TEXT)
            self.screen.blit(scroll_text, (log_rect.right - scroll_text.get_width(), log_rect.y + visible_height - line_height))

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
        return fill_color

    def draw_unit_tooltip(self, unit, mouse_pos):
        tooltip_lines = [f"ATK: {unit.ATK}", f"DEF: {unit.DEF}", f"MG ATK: {unit.MAGIC}", f"MG DEF: {unit.MAGIC_DEF}", f"CRIT: {unit.CRIT}", f"DODGE: {unit.DODGE}"]
        padding = 8
        line_height = FONT.get_linesize()
        width = max(FONT.size(line)[0] for line in tooltip_lines) + padding * 2
        height = line_height * len(tooltip_lines) + padding * 2
        tooltip_rect = pygame.Rect(mouse_pos[0] + 16, mouse_pos[1] + 16, width, height)
        if tooltip_rect.right > WIDTH:
            tooltip_rect.right = WIDTH - 10
        if tooltip_rect.bottom > HEIGHT:
            tooltip_rect.bottom = HEIGHT - 10
        pygame.draw.rect(self.screen, LIGHT_GRAY, tooltip_rect, border_radius=6)
        pygame.draw.rect(self.screen, BLACK, tooltip_rect, 2, border_radius=6)
        for i, line in enumerate(tooltip_lines):
            text_surface = FONT.render(line, True, BLACK)
            self.screen.blit(text_surface, (tooltip_rect.x + padding, tooltip_rect.y + padding + i * line_height))

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
        if tooltip_rect.bottom > HEIGHT:
            tooltip_rect.bottom = HEIGHT - 10
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
        self.screen.blit(player_title, (110, 130))
        self.screen.blit(enemy_title, (790, 130))

        mouse_pos = pygame.mouse.get_pos()
        for button in self.selection_buttons:
            button.update(mouse_pos)

        self.draw_team_preview(self.player_team, 80, 180)
        self.draw_team_preview(self.enemy_team, 760, 180)

        info_text = "Click a slot to cycle through unit classes. Then press START BATTLE."
        draw_text(self.screen, info_text, pygame.Rect(250, 90, 600, 40), FONT, BLACK)
        self.ai_toggle_button.update(mouse_pos)
        self.ai_toggle_button.draw(self.screen)
        self.start_button.update(mouse_pos)
        self.start_button.draw(self.screen)
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
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))
        winner_surf = TITLE_FONT.render(self.info_text, True, WHITE)
        self.screen.blit(winner_surf, (WIDTH // 2 - winner_surf.get_width() // 2, 280))
        mouse_pos = pygame.mouse.get_pos()
        for button in self.game_over_buttons:
            button.update(mouse_pos)
            button.draw(self.screen)

    def draw_battle_screen(self):
        self.screen.fill(WHITE)
        self.draw_buttons()
        mouse_pos = pygame.mouse.get_pos()
        hovered_unit = self.draw_units(mouse_pos)
        if hovered_unit:
            self.draw_unit_tooltip(hovered_unit, mouse_pos)
        tooltip = self.get_hovered_ability_tooltip()
        if tooltip:
            self.draw_ability_tooltip(tooltip, mouse_pos)
        self.draw_info_panel()
        if self.game_over:
            self.draw_game_over_overlay()
        pygame.display.flip()

    def draw_buttons(self):
        mouse_pos = pygame.mouse.get_pos()
        self.hovered_ability_button = None
        self.cancel_target_button = None
        if self.state == 'battle' and not self.game_over:
            for button in self.action_buttons:
                button.update(mouse_pos)
                if button.hover:
                    self.hovered_ability_button = button
                button.draw(self.screen)

            if self.selected_ability and self.available_targets:
                selected_button = next((b for b in self.action_buttons if b.text == self.selected_ability.ABILITY_NAME), None)
                if selected_button:
                    back_rect = pygame.Rect(selected_button.rect.right + 12, selected_button.rect.y, 100, selected_button.rect.height)
                    self.cancel_target_button = Button(back_rect, "BACK", self.cancel_target_selection, color=(200, 80, 80), hover_color=(220, 100, 100))
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
                    if event.type == pygame.MOUSEWHEEL and self.state == 'battle':
                        visible_height = 130
                        line_height = SMALL_FONT.get_linesize()
                        max_lines = visible_height // line_height
                        self.log_scroll = max(0, min(self.log_scroll - event.y, max(0, len(self.message_log) - max_lines)))
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if self.state == 'battle':
                            if self.game_over:
                                for button in self.game_over_buttons:
                                    if button.rect.collidepoint(event.pos):
                                        button.click()
                            elif self.selected_ability and self.available_targets:
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
                            elif not self.game_over:
                                for button in self.action_buttons:
                                    if button.rect.collidepoint(event.pos):
                                        button.click()
                        elif self.state == 'team_select':
                            for button in self.selection_buttons:
                                if button.rect.collidepoint(event.pos):
                                    button.click()
                            if self.ai_toggle_button.rect.collidepoint(event.pos):
                                self.ai_toggle_button.click()
                            if self.start_button.rect.collidepoint(event.pos):
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
