import time


class Battle:
    """Encapsulates active effects and turn-based timing."""

    def __init__(self):
        self.active_effects = []

    def register_effect(self, effect):
        if effect.turns_left <= 0:
            return
        # BUFF_ENDS == 1 means duration should start after the current action finishes.
        # Mark to skip the first post-cast decrement so LASTS counts future turns.
        effect.skip_first_after_action_tick = effect.AttrValDict.get("BUFF_ENDS") == 1
        if effect not in self.active_effects:
            self.active_effects.append(effect)
        for target in effect.target_list:
            if effect not in target.target_Ability_queue:
                target.target_Ability_queue.append(effect)

    def remove_effect(self, effect):
        if effect in self.active_effects:
            self.active_effects.remove(effect)
        for target in effect.target_list:
            if effect in target.target_Ability_queue:
                target.target_Ability_queue.remove(effect)

    def remove_target_effects(self, target):
        for effect in list(self.active_effects):
            if target in effect.target_list:
                self.remove_effect(effect)

    def resolve_turn_start(self, unit):
        self.cleanup_expired_effects()
        for effect in list(self.active_effects):
            if effect.AttrValDict["BUFF_ENDS"] != 0:
                continue
            if unit not in effect.target_list:
                continue
            effect.turns_left -= 1
            effect.cast_on_target(unit, effect.caster)
            if effect.turns_left == 0:
                self.remove_effect(effect)

    def resolve_after_action(self, caster):
        self.cleanup_expired_effects()
        for effect in list(self.active_effects):
            if effect.AttrValDict["BUFF_ENDS"] != 1:
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

    def cleanup_expired_effects(self):
        for effect in list(self.active_effects):
            if effect.turns_left <= 0:
                self.remove_effect(effect)

    def get_targets_effects(self, unit):
        return [effect for effect in self.active_effects if unit in effect.target_list]
