import time


# EFFECT_TICKS_ON values that participate in each kind of trigger — matches the
# semantics documented in abilities_readme.txt:
#   0 = per turn only
#   1 = per turn OR attacking
#   2 = per turn OR attacked
#   3 = per turn OR attacked OR attacking
#   4 = attacking only
#   5 = attacked only
#   6 = attacked OR attacking
_TICKS_ON_TURN_TICK       = (0, 1, 2, 3)   # fires in the four resolve_*_action / turn_* methods
_TICKS_ON_ATTACKED        = (2, 3, 5, 6)   # fires from resolve_on_attacked
_TICKS_ON_ATTACKING       = (1, 3, 4, 6)   # fires from resolve_on_attacking


class Battle:
    """Encapsulates active effects and turn-based timing."""

    def __init__(self):
        self.active_effects = []

    def register_effect(self, effect):
        if effect.turns_left <= 0:
            return
        # EFFECT_TICK_OWNER == 1 means the effect ticks on the caster's action (not the target's turn).
        # EFFECT_TICK_PHASE == 1 means it fires after the action; skip the immediate post-cast call.
        effect.skip_first_after_action_tick = (
            effect.AttrValDict.get("EFFECT_TICKS_ON", 0) == 0
            and effect.AttrValDict.get("EFFECT_TICK_OWNER", 0) == 1
            and effect.AttrValDict.get("EFFECT_TICK_PHASE", 0) == 1
        )
        if effect not in self.active_effects:
            self.active_effects.append(effect)
        for target in effect.target_list:
            if effect not in target.target_Ability_queue:
                target.target_Ability_queue.append(effect)

    def remove_effect(self, effect):
        if effect in self.active_effects:
            # print(f"Removing effect {effect.ABILITY_NAME} from battle")  # debug
            self.active_effects.remove(effect)
        effect_status = effect.AttrValDict.get("EFFECT_STATUS")
        # If this effect applied stat modifiers that haven't been reversed yet
        # (e.g. caster/target was downed mid-buff), reverse them now.
        needs_reversal = (
            effect.AttrValDict.get("EFFECT_VALUES")
            and isinstance(getattr(effect, 'sp_val', None), dict)
            and not getattr(effect, '_stats_reversed', False)
        )
        if needs_reversal:
            for target in effect.target_list:
                effect.effect_stat_modifier("remove", target)
        for target in effect.target_list:
            if effect in target.target_Ability_queue:
                # print(f"Removing effect {effect.ABILITY_NAME} from target {target.name}'s queue")  # debug
                target.target_Ability_queue.remove(effect)
            if effect_status:
                target.modify_effect_stack_dict("remove", effect_status)
            if effect_status == "STUN" and target.alive:
                print("{} recovered from being stunned!".format(str(target)))

    def remove_target_effects(self, target):
        for effect in list(self.active_effects):
            if target in effect.target_list:
                self.remove_effect(effect)

    def remove_caster_effects(self, caster):
        """Called when a caster is downed. Handles EFFECT_CASTER_DEATH for all caster effects.
        0 = remove instantly on down, 1 = continue ghost ticking (TICK_OWNER=1 only),
        2 = immortal, leave untouched."""
        for effect in list(self.active_effects):
            if effect.caster != caster:
                continue
            death_behavior = effect.AttrValDict.get("EFFECT_CASTER_DEATH", 0)
            if death_behavior == 0:
                self.remove_effect(effect)
            # death_behavior == 1: ghost ticking — resolved via resolve_ghost_caster_turns (TICK_OWNER=1 only)
            # death_behavior == 2: immortal, leave untouched

    def handle_unit_downed(self, unit):
        """Called when a unit transitions to downed state (0 HP, revivable).
        Removes effects based on EFFECT_TARGET_DEATH and EFFECT_CASTER_DEATH."""
        # Handle effects where this unit is the target
        for effect in list(self.active_effects):
            if unit not in effect.target_list:
                continue
            target_death = effect.AttrValDict.get("EFFECT_TARGET_DEATH", 0)
            # print(f"Handling downed unit {unit.name} for effect {effect.ABILITY_NAME}, target_death={target_death}")  # debug
            if target_death == 0:
                self.remove_effect(effect)
            # target_death == 1: keep effect, expires on permanent death
        # Handle effects where this unit is the caster
        self.remove_caster_effects(unit)
        # Fire passives that trigger on a teammate going down
        self._fire_ally_death_passives(unit)

    def _fire_ally_death_passives(self, fallen_unit):
        """Casts each surviving teammate's ALLY_DEATH-triggered passives on
        themselves (self-buffs like Uproar). Enemy passives are unaffected.
        Emits a cast_sound combat event so the GUI can play CAST_SOUND without
        this module needing to touch pygame."""
        from Abilities import Ability
        from Units import Unit
        for ally in Unit.get_units("alive", fallen_unit.team):
            if ally is fallen_unit:
                continue
            for passive_name in getattr(ally, 'passives', []):
                attrs = Ability.AbilitiesDict.get(passive_name)
                if not attrs or attrs.get("TRIGGER_ON") != "ALLY_DEATH":
                    continue
                if attrs.get("CAST_SOUND"):
                    Ability._combat_events.append({"kind": "cast_sound", "ability": passive_name})
                passive = Ability(passive_name, Ability.ability_ID_counter)
                passive.initial_cast([ally], ally, self)

    def handle_unit_dead(self, unit):
        """Called on permanent death. Removes all remaining effects on or cast by the unit."""
        for effect in list(self.active_effects):
            if unit in effect.target_list or effect.caster == unit:
                self.remove_effect(effect)

    def resolve_ghost_caster_turns(self, caster):
        """Fires EFFECT_CASTER_DEATH=1 effects for a specific downed caster,
        at the point in the turn order where they would have acted."""
        self.cleanup_expired_effects()
        for effect in list(self.active_effects):
            if effect.caster != caster:
                continue
            if effect.AttrValDict.get("EFFECT_TICKS_ON", 0) not in _TICKS_ON_TURN_TICK:
                continue
            if effect.AttrValDict.get("EFFECT_TICK_OWNER", 0) != 1:
                continue
            if effect.AttrValDict.get("EFFECT_CASTER_DEATH", 0) != 1:
                continue
            effect.turns_left -= 1
            for target in list(effect.target_list):
                effect.cast_on_target(target, caster)
            if effect.turns_left == 0:
                self.remove_effect(effect)

    def resolve_turn_start(self, unit):
        """TICK_OWNER=0, TICK_PHASE=0 — fires at the start of the target's turn."""
        self.cleanup_expired_effects()
        for effect in list(self.active_effects):
            if effect.AttrValDict.get("EFFECT_TICKS_ON", 0) not in _TICKS_ON_TURN_TICK or effect.AttrValDict.get("EFFECT_TICK_OWNER", 0) != 0:
                continue
            if effect.AttrValDict.get("EFFECT_TICK_PHASE", 0) != 0:
                continue
            if unit not in effect.target_list:
                continue
            effect.turns_left -= 1
            effect.cast_on_target(unit, effect.caster)
            if effect.turns_left == 0:
                self.remove_effect(effect)

    def resolve_before_action(self, caster):
        """TICK_OWNER=1, TICK_PHASE=0 — fires at the start of the caster's turn."""
        self.cleanup_expired_effects()
        for effect in list(self.active_effects):
            if effect.AttrValDict.get("EFFECT_TICKS_ON", 0) not in _TICKS_ON_TURN_TICK or effect.AttrValDict.get("EFFECT_TICK_OWNER", 0) != 1:
                continue
            if effect.AttrValDict.get("EFFECT_TICK_PHASE", 0) != 0:
                continue
            if effect.caster != caster:
                continue
            effect.turns_left -= 1
            for target in list(effect.target_list):
                effect.cast_on_target(target, caster)
            if effect.turns_left == 0:
                self.remove_effect(effect)

    def resolve_after_action(self, caster):
        """TICK_OWNER=1, TICK_PHASE=1 — fires at the end of the caster's action."""
        self.cleanup_expired_effects()
        for effect in list(self.active_effects):
            if effect.AttrValDict.get("EFFECT_TICKS_ON", 0) not in _TICKS_ON_TURN_TICK or effect.AttrValDict.get("EFFECT_TICK_OWNER", 0) != 1:
                continue
            if effect.AttrValDict.get("EFFECT_TICK_PHASE", 0) != 1:
                continue
            if effect.caster != caster:
                continue
            if getattr(effect, "skip_first_after_action_tick", False):
                effect.skip_first_after_action_tick = False
                continue
            effect.turns_left -= 1
            for target in list(effect.target_list):
                effect.cast_on_target(target, caster)
            if effect.turns_left == 0:
                self.remove_effect(effect)

    def resolve_turn_end(self, unit):
        """TICK_OWNER=0, TICK_PHASE=1 — fires at the end of the target's turn."""
        self.cleanup_expired_effects()
        for effect in list(self.active_effects):
            if effect.AttrValDict.get("EFFECT_TICKS_ON", 0) not in _TICKS_ON_TURN_TICK or effect.AttrValDict.get("EFFECT_TICK_OWNER", 0) != 0:
                continue
            if effect.AttrValDict.get("EFFECT_TICK_PHASE", 0) != 1:
                continue
            if unit not in effect.target_list:
                continue
            effect.turns_left -= 1
            effect.cast_on_target(unit, effect.caster)
            if effect.turns_left == 0:
                self.remove_effect(effect)

    def cleanup_expired_effects(self):
        for effect in list(self.active_effects):
            if effect.turns_left <= 0:
                self.remove_effect(effect)

    def get_targets_effects(self, unit):
        return [effect for effect in self.active_effects if unit in effect.target_list]

    #if the target is at the EFFECT_STACKS limit, expire and remove the oldest instance of the same effect on that target
    def enforce_stack_limit(self, ability, target):
        times_stackable = ability.AttrValDict["EFFECT_STACKS"]
        effect_status = ability.AttrValDict["EFFECT_STATUS"]
        current_stacks = target.effect_stacks_dict.get(effect_status, 0)
        if current_stacks >= times_stackable:
            for old_effect in self.active_effects:
                if (old_effect.AttrValDict.get("EFFECT_STATUS") == effect_status
                        and target in old_effect.target_list):
                    old_effect.turns_left = 0
                    old_effect.cast_on_target(target, old_effect.caster)
                    self.remove_effect(old_effect)
                    break

    def resolve_on_attacked(self, target, was_hit):
        self.cleanup_expired_effects()
        for effect in list(self.active_effects):
            triggers_on = effect.AttrValDict.get("EFFECT_TICKS_ON", 0)
            if triggers_on not in _TICKS_ON_ATTACKED:
                continue
            if target not in effect.target_list:
                continue
            if effect.AttrValDict.get("EFFECT_TICK_ON_HIT_ONLY", False) and not was_hit:
                continue
            effect.turns_left -= 1
            effect.cast_on_target(target, effect.caster)
            if effect.turns_left == 0:
                self.remove_effect(effect)

    def resolve_on_attacking(self, attacker, hit_any):
        self.cleanup_expired_effects()
        for effect in list(self.active_effects):
            triggers_on = effect.AttrValDict.get("EFFECT_TICKS_ON", 0)
            if triggers_on not in _TICKS_ON_ATTACKING:
                continue
            if attacker not in effect.target_list:
                continue
            if effect.AttrValDict.get("EFFECT_TICK_ON_HIT_ONLY", False) and not hit_any:
                continue
            effect.turns_left -= 1
            effect.cast_on_target(attacker, effect.caster)
            if effect.turns_left == 0:
                self.remove_effect(effect)

    def is_battle_over(self):
        from Units import Unit
        return Unit.num_units(0, "alive") == 0 or Unit.num_units(1, "alive") == 0
