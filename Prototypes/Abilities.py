"""
All ability effects (except initial mana cost) will be handled here.
Entering point into this class is through Unit.choose_move(), where an Abilityobject is created, and then its determine_targets() method is called
"""

import time
import random
from random import randint
import math
import json
from Units import Unit

# Load ability data from JSON file
with open('abilities.json', 'r') as f:
    ability_data = json.load(f)
AbilitiesDict = ability_data['AbilitiesDict']

class Ability():
    AbilitiesDict = AbilitiesDict  # Loaded from JSON
    ability_ID_counter = 0

    @classmethod
    def _normalize_ability_entry(cls, ability_definition):
        return ability_definition.copy()

    def __init__(self, ability_name, ability_ID):       

        self.ability_ID = ability_ID    #is this needed? The only reference to an ability after its turn is over is through the Ability_queue, is that enough?
        Ability.ability_ID_counter += 1       #for ability_ID during creating... is this needed?

        self.ABILITY_NAME = ability_name                                                        #used to match to special method if needed
        self.target_list = None                                                                      #the target of this ability
        self.caster = None                                                                      #the one using this ability, used in helping determine if it's a players turn
        self.AttrValDict = self.build_AttrValDict()
        self.turns_left = self.AttrValDict["TICKS"]

        self.sp_val = None              #a place to store a value for this particular ability, e.g. target's DEF at time of casting

#========================================Class methods===========================================================================================
    #Uses AbilitiesDict to get an attribute value for a named ability.
    #This is used when an Ability object is not referred to directly, e.g. getting MP for Unit.display_moves()
    @classmethod
    def get_attr(cls, skill_name, ATTRIBUTE_NAME):
        try:
            ability_definition = Ability.AbilitiesDict[skill_name]
        except KeyError:
            raise ValueError('Ability does not exist!')
        normalized = Ability._normalize_ability_entry(ability_definition)
        if ATTRIBUTE_NAME not in normalized:
            raise ValueError('Attribute does not exist!')
        return normalized[ATTRIBUTE_NAME]

    #generic damage (no calculations) with message outputs and minimum damage of 0
    @classmethod
    def damage_target(cls, final_damage, target, dmg_type, is_crit=False):
        if dmg_type == "NORMAL":
            damage_message = "physical"
            blocked_message = "Their defence is too high!"
        elif dmg_type == "MAGIC":
            damage_message = "magic"
            blocked_message = "Their magic is too strong!"
        if final_damage > 0:                                #if there is damage,
            target.hp -= final_damage                             #target loses HP
            if is_crit:
                print("Critical hit! {} took {} {} damage!".format(str(target), final_damage, damage_message))
            else:
                print("{} took {} {} damage!".format(str(target), final_damage, damage_message))       
        else:
            print("{} took no damage... {}".format(str(target), blocked_message))

    #abilities that are 'heals' should use this
    @classmethod
    def heal_target(cls,target, hp_gain, mp_gain):

        if hp_gain > 0:
            healed_to_max = (hp_gain + target.hp) >= target.max_hp
            if healed_to_max:
                print("{} was fully healed!".format(target))
            else:
                print("{} was healed for {} health!".format(target, hp_gain))
            target.hp += hp_gain
        if mp_gain > 0:
            mp_to_max = (mp_gain + target.mp) >= target.max_mp
            if mp_to_max:
                print("{}'s mana was fully restored!".format(target))
            else:
                print("{} recovered {} mana!".format(target, mp_gain))
            target.mp += mp_gain

#=================================Instance methods=========================================================================================
    #populates this ability object's AttrValDict with its stats as key:value pairs
    def build_AttrValDict(self):
        return Ability._normalize_ability_entry(Ability.AbilitiesDict[self.ABILITY_NAME])

    #determines this ability's available targets and gets targets (using select_target() if needed) to get a target_list
    def determine_targets(self, caster, battle, is_multiplayer = False):
        target_type = self.AttrValDict["TARGET_TYPE"]
        target_is_enemy = self.AttrValDict["TARGET_ENEMY"]

        if target_type == 0:
            target_list = [caster]
        else:
            if target_is_enemy:
                target_team = Unit.get_units("alive", 1 - caster.team)
            else:
                target_team = Unit.get_units("alive", caster.team)

            if target_type == 1:
                if len(target_team) == 1:
                    target_list = [target_team[0]]
                else:
                    target = self.select_target(target_team, caster, battle, is_multiplayer)
                    if target is None:
                        return None
                    target_list = [target]

            elif target_type == 2:
                target_list = target_team
                if not target_list:
                    print("No valid targets available.")
                    return None

            elif target_type == 3:
                target_list = target_team

            elif target_type == 4:
                target_list = Unit.get_units("alive", 0) + Unit.get_units("alive", 1)

        self.initial_cast(target_list, caster, battle)
        return target_list

    #sets the target_list and caster for this ability, takes MP_COST, displays 'used' output, and for every target in target_list, check effect_stacks if is a effect and cast_on_target(), then check_Ability_queue() if needed
    def initial_cast(self, target_list, caster, battle):
        self.target_list = target_list                            #store target_list and caster in ability instance
        self.caster = caster
        self.last_damage_dealt = 0
        if self.AttrValDict["TARGET_TYPE"] == 1:
            print("{} used {} on {}!".format(caster.name, self.ABILITY_NAME, str(self.target_list[0])))
        else:
            print("{} used {}!".format(caster.name, self.ABILITY_NAME))

        success = True
        effect_applied_to_any = False
        target_sp_vals = {}
        target_results = {}
        for target in target_list:                      #for every target unit
            if self.AttrValDict["IS_EFFECT"] and not self.check_stacks(target, battle):
                continue
            target_success = self.cast_on_target(target, caster)
            target_results[id(target)] = target_success
            if isinstance(self.sp_val, dict):           # capture actual stat changes per target
                target_sp_vals[id(target)] = dict(self.sp_val)
            if self.AttrValDict["IS_EFFECT"] and target_success is None:
                target.modify_effect_stack_dict("add", self.AttrValDict["EFFECT_STATUS"])
                effect_applied_to_any = True
            if target_success is False:
                success = False

        if self.AttrValDict["IS_EFFECT"]:
            success = success and effect_applied_to_any

        if self.AttrValDict.get("DMG_TYPE") in ("NORMAL", "MAGIC"):
            hit_any = any(v is not False for v in target_results.values())
            battle.resolve_on_attacking(caster, hit_any)
            for target in target_list:
                was_hit = target_results.get(id(target)) is not False
                battle.resolve_on_attacked(target, was_hit)

        if success:
            caster.mp -= self.AttrValDict["MP_COST"]

        if self.turns_left > 0 and success:
            if self.AttrValDict["IS_EFFECT"] and len(target_list) > 1:
                # Multi-target buffs/debuffs use one effect instance per target
                # so each unit tracks duration independently.
                for target in target_list:
                    per_target_effect = Ability(self.ABILITY_NAME, Ability.ability_ID_counter)
                    per_target_effect.caster = caster
                    per_target_effect.target_list = [target]
                    per_target_effect.turns_left = self.turns_left
                    per_target_effect.sp_val = target_sp_vals.get(id(target))  # copy actual changes
                    battle.register_effect(per_target_effect)
            else:
                battle.register_effect(self)

        # for compatibility, support effect expiry after caster action if the ability has a delayed end
        if self.turns_left == 0 and self.AttrValDict["IS_EFFECT"] and success:
            for target in self.target_list:
                target.modify_effect_stack_dict("remove", self.AttrValDict["EFFECT_STATUS"])
        return success

    #if the ability is past its EFFECT_STACKS limit, expire and remove the oldest instance of the same effect on the target
    def check_stacks(self, target, battle):
        times_stackable = self.AttrValDict["EFFECT_STACKS"]
        effect_status = self.AttrValDict["EFFECT_STATUS"]
        current_stacks = target.effect_stacks_dict.get(effect_status, 0)
        if current_stacks >= times_stackable:
            # Remove the oldest active effect with the same status on this target
            for old_effect in battle.active_effects:
                if (old_effect.AttrValDict.get("EFFECT_STATUS") == effect_status
                        and target in old_effect.target_list):
                    old_effect.turns_left = 0
                    old_effect.cast_on_target(target, old_effect.caster)
                    battle.active_effects.remove(old_effect)
                    break
        return True

    #displays available targets (in targeted team and alive) and returns a unit from user input
    def select_target(self, target_team, caster, battle, is_multiplayer = True):
        targets_alive = target_team
        if not targets_alive:
            print("No valid targets available.")
            return None

        if is_multiplayer:
            print("Who would you like to use {} on?".format(self.ABILITY_NAME))
            for index, target in enumerate(targets_alive, start=1):
                print("{}. {}".format(index, str(target)))
            while True:
                try:
                    select_who = input("> ")
                    if select_who == "b":
                        caster.choose_move(battle, self)
                        return None
                    selected_index = int(select_who)
                    if 1 <= selected_index <= len(targets_alive):
                        target = targets_alive[selected_index - 1]
                        if self.AttrValDict["IS_HEAL"]:
                            if self.AttrValDict["HP_GAIN"] != 0 and target.hp >= target.max_hp:
                                print("Already at full health!")
                                continue
                            if self.AttrValDict["MP_GAIN"] != 0 and target.mp >= target.max_mp:
                                print("Already at full mana!")
                                continue
                        break
                    print("Please enter a valid number or enter 'b' to go back.")
                except ValueError:
                    print("Please enter a number or enter 'b' to go back.")
            print()
        else:
            target = random.choice(targets_alive)
        return target

    #Do basic mechanics using ABILITY_ATTRIBUTES to target
    def cast_on_target(self, target, caster):          
        success = None
        if not self.ability_dodged(target):                                 #if abiltiy hits (i.e. ability_dodged = False)
            if self.AttrValDict["IS_SPECIAL"]:              #put it first in order because ..
                success = self.special_sorter(target, caster)                           
                if success == None:                                                                     #if success == None (i.e. not False)
                    if self.AttrValDict["IS_EFFECT"] and self.turns_left == 0:                                     #if ability was an effect AND ability is expiring
                        target.modify_effect_stack_dict("remove", self.AttrValDict["EFFECT_STATUS"])                    #remove this effect stack
                elif success == False:                                                                  #elif move was unsuccessful
                    self.turns_left = 0     
            dmg_type = self.AttrValDict["DMG_TYPE"]                                                                #set turns_left to 0 to be deleted by check_Ability_queue()
            if success is None and dmg_type in ["NORMAL", "MAGIC"]:
                raw_damage = self.calculate_dmg(caster, dmg_type)
                final_damage = self.calculate_def(raw_damage, target, dmg_type)
                is_crit = random.random() < caster.CRIT / 100
                if is_crit and final_damage > 0:
                    final_damage = math.ceil(final_damage * 1.5)
                Ability.damage_target(final_damage, target, dmg_type, is_crit)
                self.last_damage_dealt = getattr(self, 'last_damage_dealt', 0) + max(0, final_damage)
            if self.AttrValDict["IS_HEAL"]:
                hp_gain, mp_gain = self.calculate_heals(target)
                Ability.heal_target(target, hp_gain, mp_gain)
        else:
            success = False  
            self.turns_left = 0                                                                     #set turns_left to 0 to be deleted by check_Ability_queue()
        if self.AttrValDict["IS_EFFECT"]:                                             #return success to signal if check_stats should be called in initial_cast()
            return success
        return success

    def calculate_dmg(self, caster, dmg_type):        #uses DMG_BASE, DMG_ROLL, and caster.ATK/caster.MAGIC to calculate and return raw_damage
        minDMG, maxDMG = self.calculate_ability_dmg_range()
        if dmg_type == "NORMAL":
            raw_damage = caster.ATK + randint(minDMG,maxDMG)
        elif dmg_type == "MAGIC":
            raw_damage = caster.MAGIC + randint(minDMG,maxDMG)
        return raw_damage

    def calculate_ability_dmg_range(self):
        minDMG, maxDMG = (self.AttrValDict["DMG_BASE"] - self.AttrValDict["DMG_ROLL"],
                            self.AttrValDict["DMG_BASE"] + self.AttrValDict["DMG_ROLL"])
        return minDMG, maxDMG

    def calculate_def(self, raw_damage, target, dmg_type):    #uses a damage value and target.DEF/target.MAGIC to calculate and return final_damage
        if dmg_type == "NORMAL":
            final_damage = raw_damage - target.DEF
        if dmg_type == "MAGIC":
            final_damage = raw_damage - target.MAGIC
        return final_damage

    def calculate_heals(self, target):                  #
        hp_gain = self.AttrValDict["HP_GAIN"]
        mp_gain = self.AttrValDict["MP_GAIN"]
        return hp_gain, mp_gain

    #if CAN_DODGE = True, do dodge calculation and return True if dodged, False if hit, else if CAN_DODGE = False, always return False (ability always hits)
    def ability_dodged(self, target):                       
        if self.AttrValDict["IS_EFFECT"] and self.turns_left != self.AttrValDict["TICKS"]:                #if it is an effect tick, it cannot be dodged
            return False
        if self.AttrValDict["CAN_DODGE"]:
            #print("Dodge is: {}".format(target.DODGE))                                 #for debugging
            if random.random() < target.DODGE/100:
                print("{} dodged the attack!".format(str(target)))
                return True
        return False

    #abilities with IS_SPECIAL look up their method by ability name: strip '/', title-case, remove spaces
    def special_sorter(self, target, caster):
        method_name = self.ABILITY_NAME.replace('/', ' ').title().replace(' ', '')
        method = getattr(self, method_name, None)
        if method is not None:
            return method(target, caster)
        print("special_sorter: no method found for '{}'".format(self.ABILITY_NAME))

    #uses EFFECT_VALUES in AttrValDict to find which unit stats to change. Usually called twice: at initial cast, and revert at expiration
    def effect_stat_modifier(self, add_remove, target):
        effect_values = self.AttrValDict.get("EFFECT_VALUES") or {}
        if add_remove == 'add':
            actual_changes = {}
            for stat, value in effect_values.items():
                if value != 0:
                    before = getattr(target, stat)
                    setattr(target, stat, before + value)
                    after = getattr(target, stat)
                    actual_changes[stat] = after - before   # may differ from value due to clamping
            self.sp_val = actual_changes
        else:
            changes = self.sp_val if isinstance(self.sp_val, dict) else {}
            for stat, value in effect_values.items():
                if value != 0:
                    actual = changes.get(stat, value)
                    setattr(target, stat, getattr(target, stat) - actual)

#----------------------Special instance methods----------------------------------------------------
    #This section contains all methods used by abilities that have unique mechanics not covered by basic ones
    #
    def SharpenSword(self, target, caster=None):             
        if self.turns_left == self.AttrValDict["TICKS"]:
            self.effect_stat_modifier("add", target)
            print("{} whets his sword until it is razor sharp (ATK +10 / CRIT +25)".format(str(target)))
        elif self.turns_left == 0:                                     #reverse effects after last turn
            self.effect_stat_modifier("remove", target)
            print("{}'s sword dulls (ATK -10 / CRIT -25)".format(str(target)))

    #
    def Leech(self, target, caster):
        damage = caster.ATK + 5 - target.DEF + randint(0, 6)
        if damage > 0:
            target.hp -= damage
            caster.hp += damage
            print("{} leeched {} health from {}!".format(str(caster), damage, str(target)))
        else:
            print("{} was unable to leech health from {}!".format(str(caster), str(target)))

    #
    def Poison(self, target, caster=None):
        if self.turns_left == self.AttrValDict["TICKS"]:
            minDMG, maxDMG = self.calculate_ability_dmg_range()
            damage = randint(minDMG,maxDMG) - math.floor(target.DEF)
            if damage <= 0:
                print("The poison dart bounced off {}... their DEF is too high!".format(str(target)))
                return False
            target.hp -= damage
            print("{} took {} damage from a poison dart!".format(str(target), damage))
        else:
            stacks = target.effect_stacks_dict.get(self.AttrValDict["EFFECT_STATUS"], 1)
            tick_damage = max(math.floor(target.hp * 0.15), 1)
            target.hp -= tick_damage
            print("{} took {} damage from poison!".format(str(target), tick_damage))
            if self.turns_left == 0:
                if target.hp > 0:
                    if stacks == 1:
                        print("{} has recovered from poison.".format(str(target)))
                    else:
                        print("{} is slowly recovering from poison.".format(str(target)))

    #
    def RaiseShield(self, target, caster=None):
        if self.turns_left == self.AttrValDict["TICKS"]:
            self.effect_stat_modifier("add", target)
            print("{}'s DEF has increased by 8!".format(str(target)))
        elif self.turns_left == 0:
            self.effect_stat_modifier("remove", target)
            print("{} lowers their shield".format(str(target)))

    #
    def Sneak(self, target, caster=None):                                                                                  # also in future it could mean value could vary with unit stats e.g. MAGIC
        if self.turns_left == self.AttrValDict["TICKS"]:      #if just cast,
            self.effect_stat_modifier("add", target)
            print("{}'s DODGE has increased by 40 and CRIT by 80!".format(str(target)))
        elif self.turns_left == 0:                                                        #reverse effects in last turn
            self.effect_stat_modifier("remove", target)
            print("{} takes a steady stance. Their DODGE and CRIT return to normal.".format(str(target)))
    #
    def Shroud(self, target, caster=None):                                                                                  # also in future it could mean value could vary with unit stats e.g. MAGIC
        if self.turns_left == self.AttrValDict["TICKS"]:      #if just cast,
            self.effect_stat_modifier("add", target)
            print("{}'s DODGE has increased by 60!".format(str(target)))

            mp_gain = self.AttrValDict["MP_GAIN"]
            Ability.heal_target(target, 0, mp_gain)

        elif self.turns_left == 0:                                                        #reverse effects in last turn
            self.effect_stat_modifier("remove", target)
            print("{} takes a steady stance. Their DODGE returns to normal.".format(str(target)))

    #
    def Taunt(self, target, caster=None):                                                                                  
        if self.turns_left == self.AttrValDict["TICKS"]:      #if just cast, 
            self.effect_stat_modifier("add", target)
            print("{}'s DEF has decreased by 6!".format(str(target)))
        elif self.turns_left == 0:                                                           #reverse effects in last turn
            self.effect_stat_modifier("remove", target)
            print("{} regains his composure. His DEF returns to normal".format(str(target)))

    #
    def Uproar(self, target, caster=None):                                                                                  
        if self.turns_left == self.AttrValDict["TICKS"]:      #if just cast, 
            self.effect_stat_modifier("add", target)
            print("{}'s ATK increased by 2 and CRIT has increased by 5!".format(str(target)))
        elif self.turns_left == 0:                                                           #reverse effects in last turn
            self.effect_stat_modifier("remove", target)
            print("{} regains his composure. His ATK and CRIT return to normal.".format(str(target)))
    #
    def Bless(self, target, caster=None):                                                                                  
        if self.turns_left == self.AttrValDict["TICKS"]:      #if just cast, 
            self.effect_stat_modifier("add", target)
            print("{}'s DEF has increased by 4!".format(str(target)))
        elif self.turns_left == 0:                                                           #reverse effects in last turn
            self.effect_stat_modifier("remove", target)
            print("{} regains his composure. His DEF returns to normal.".format(str(target)))

    #
    def Deceive(self, target, caster=None):                                                                                  
        if self.turns_left == self.AttrValDict["TICKS"]:      #if just cast, 
            self.effect_stat_modifier("add", target)
            print("{}'s DEF has decreased by 7 and DODGE by 15!".format(str(target)))
        elif self.turns_left == 0:                                                           #reverse effects in last turn
            self.effect_stat_modifier("remove", target)
            print("{} regains his composure. His DEF and DODGE return to normal.".format(str(target)))

    #
    def Disquiet(self, target, caster=None):                                                                                  
        if self.turns_left == self.AttrValDict["TICKS"]:      #if just cast, 
            self.effect_stat_modifier("add", target)
            print("{}'s ATK and CRIT have decreased by 8 and 15!".format(str(target)))
        elif self.turns_left == 0:                                                           #reverse effects in last turn
            self.effect_stat_modifier("remove", target)
            print("{} regains his composure. His ATK and CRIT return to normal.".format(str(target)))

    #
    def Frenzy(self, target, caster=None):                                                                                  
        if self.turns_left == self.AttrValDict["TICKS"]:      #if just cast, 
            self.effect_stat_modifier("add", target)
            print("{}'s ATK has increased by 6 and CRIT has increased by 15!".format(str(target)))
        elif self.turns_left == 0:                                                           #reverse effects in last turn
            self.effect_stat_modifier("remove", target)
            print("{} calms. His ATK and CRIT return to normal.".format(str(target)))

    #
    def Mark(self, target, caster=None):
        if self.turns_left == self.AttrValDict["TICKS"]:      #if just cast, apply DEF penalty
            before = target.DEF
            target.DEF -= 6
            self.sp_val = before - target.DEF   # actual amount deducted (handles DEF floor at 0)
            print("{} has been Marked! Their DEF has decreased by {}!".format(str(target), self.sp_val))
        elif self.turns_left == 0:                                                        #reverse effect on expiry
            deducted = self.sp_val if self.sp_val is not None else 6
            target.DEF += deducted
            print("{} is no longer Marked. Their DEF returns to normal.".format(str(target)))

    #
    def StabBackstab(self, target, caster):
        raw_damage = self.calculate_dmg(caster, "NORMAL")
        final_damage = self.calculate_def(raw_damage, target, "NORMAL")
        is_crit = random.random() < caster.CRIT / 100
        if is_crit and final_damage > 0:
            final_damage = math.ceil(final_damage * 1.5)

        bonus_damage = 0
        if "MARKED" in target.effect_stacks_dict:                             #can only be used on MARKED targets
            # print("{} is Marked! Sneak behind.".format(str(target)))
            missing_hp = target.max_hp - target.hp
            bonus_damage = math.floor(missing_hp * 0.2)

        Ability.damage_target(final_damage, target, "NORMAL", is_crit)
        self.last_damage_dealt = getattr(self, 'last_damage_dealt', 0) + max(0, final_damage)
        if bonus_damage > 0:
            target.hp -= bonus_damage
            self.last_damage_dealt += bonus_damage
            print("{} takes an additional {} damage from a backstab!".format(str(target), bonus_damage))
        return True