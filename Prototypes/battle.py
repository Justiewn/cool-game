import time


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
            effect.AttrValDict.get("EFFECT_TRIGGERS_ON", 0) == 0
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
            self.active_effects.remove(effect)
        for target in effect.target_list:
            if effect in target.target_Ability_queue:
                target.target_Ability_queue.remove(effect)

    def remove_target_effects(self, target):
        for effect in list(self.active_effects):
            if target in effect.target_list:
                self.remove_effect(effect)

    def resolve_turn_start(self, unit):
        """TICK_OWNER=0, TICK_PHASE=0 — fires at the start of the target's turn."""
        self.cleanup_expired_effects()
        for effect in list(self.active_effects):
            if effect.AttrValDict.get("EFFECT_TRIGGERS_ON", 0) != 0 or effect.AttrValDict.get("EFFECT_TICK_OWNER", 0) != 0:
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
            if effect.AttrValDict.get("EFFECT_TRIGGERS_ON", 0) != 0 or effect.AttrValDict.get("EFFECT_TICK_OWNER", 0) != 1:
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
            if effect.AttrValDict.get("EFFECT_TRIGGERS_ON", 0) != 0 or effect.AttrValDict.get("EFFECT_TICK_OWNER", 0) != 1:
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
            if effect.AttrValDict.get("EFFECT_TRIGGERS_ON", 0) != 0 or effect.AttrValDict.get("EFFECT_TICK_OWNER", 0) != 0:
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

    def resolve_on_attacked(self, target, was_hit):
        self.cleanup_expired_effects()
        for effect in list(self.active_effects):
            triggers_on = effect.AttrValDict.get("EFFECT_TRIGGERS_ON", 0)
            if triggers_on not in (1, 3):
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
            triggers_on = effect.AttrValDict.get("EFFECT_TRIGGERS_ON", 0)
            if triggers_on not in (2, 3):
                continue
            if attacker not in effect.target_list:
                continue
            if effect.AttrValDict.get("EFFECT_TICK_ON_HIT_ONLY", False) and not hit_any:
                continue
            effect.turns_left -= 1
            effect.cast_on_target(attacker, effect.caster)
            if effect.turns_left == 0:
                self.remove_effect(effect)
