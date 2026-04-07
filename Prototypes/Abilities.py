"""
All ability effects (except initial mana cost) will be handled here.
Entering point into this class is through Unit.choose_move(), where an Abilityobject is created, and then its determine_targets() method is called

Class methods:

    - get_attr(skill_name, ATTRIBUTE_NAME): gets the index and returns the value of a skill's attribute
    - check_Ability_queue(current_ability): removes expired abilities and procs active ones in the ability queue

    ----unit stat-modifying class methods------------
    - damage_target(damage_amount, target, dmg_type): damage (no calculations) with generic message outputs and minimum damage of 0
    - heal_target(target, hp_gain, mp_gain): healing (no calculations) with generic message outputs with cap at target's max hp/mp


Instance methods:

    - y.build_AttrValDict(): populates this ability object's AttrValDict with its stats as key:value pairs
    - y.determine_targets(caster): determines this ability's available targets to fill target_list (using select_target(target_team) if needed)
    - y.initial_cast(target_list, caster): use cast_on_target(target, caster) for targets in target_list (also check_stacks(target) if ability is a buff), 
                                            then check_Ability_queue(self) if there are any other abilites in queue
    - y.check_stacks(target): checks the stacks of the ability on the target, makes sure stack limit is not breached (this is only called by cast_on_target() if ability was successful)
    - y.select_target(target_team, caster):
    - y.cast_on_target(target, caster): Actions the ability's effects on the target 

    Instance (calculation) methods:
        - y.calculate_dmg(caster): calculates damage range from DMG_BASE and DMG_ROLL, gets random damage from that range and calls damage_target()
        - y.calculate_heals(target, caster)
        - y.calculate_def(raw_damage, target)
        - y.ability_dodged(target)

All abilities should be declared in Ability_dict and should follow this format:
    ( "NAME", [ ["TARGET_TYPE", "TARGET_ENEMY", "TARGET_NUM"], ["SPECIAL", "LASTS"], ["MP_COST"], ["DMG_TYPE", "DMG_IS_PERCENT", "DMG_BASE", "DMG_ROLL"], ["IS_HEAL", "HP_GAIN", "MP_GAIN"] ] )     #SUBJECT TO CHANGE ACCORDING TO THE NEEDS OF CREATED ABILITIES

    TARGET [0]:
        TARGET_TYPE [0]     - (int) 0 = self,       1 = single,     2 = multiple,   3 = team (units in the team will no be differentiated),   4 =  all (units will not be differentiated)
        TARGET_ENEMY [1]    - (boolean) True if targets enemies, False if it targets allies (use x if TARGET_TYPE = self, all )
        TARGET_NUM [2]      - (int) Number of targets to target if TARGET_TYPE = multiple (use x if otherwise)
    OTHER [1]:      
        SPECIAL [0]     - (int) 0 if only initial methods should be used, 1 if only a special method should be used, 2 if both initial and special methods should be used
        LASTS [1]       - (int) Number of (caster) moves this ability will last for (0 for immediate expiration)
        CAN_DODGE [2]   - (boolean) If ability can be dodged, True, else False
    MP_COST [2]
    DAMAGE [3]:           
        DMG_TYPE [0]        - (boolean) "NORMAL" or "MAGIC" if move does initial damage, False otherwise and ignore rest of section
        DMG_IS_PERCENT [2]  - (boolean)
        DMG_BASE [1]        - (int) base damage of this ability. This is added onto the ATK of the unit
        DMG_ROLL [2]        - (int) amount by which base damage may deviate each way, i.e. DMG_BASE ± DMG ROLL = Damage range (0 for no deviation) 
    REGEN [4]:           
        IS_HEAL [0]         - (bool) Uses any of this section means True, else False and ignore rest of section
        HP_GAIN [1]         - (int) HP healed (0 for none)
        MP_GAIN [2]         - (int) MP gained (0 for none)
    BUFF [5]:
        IS_BUFF [0]         - (bool) True if ability should be considered a buff, i.e. will be changing a unit's stats, False otherwise and ignore rest of section
        BUFF_TRIGGER_ON [1] - (int) buff loses duration: 0 = per turn, 1 =  when attacked, 2=  when attacking 
        BUFF_ENDS [ 2]      - (int) buff ends before or after caster move,  0 = before, 1 = after
        BUFF_STACKS [3]     - (int) How many instances of this buff can exist on a target, (1 for no stacking, i.e. only one instance) 
        BUFF_STATUS [4]     - (str) the string that is displayed to represent this buff
        


    If an abiltiy also has a buff/debuff effect which affects units' stats (TO ADD: or other mechanics that are popular), they should be put into specialDict:

    ( "NAME",  [ {BUFFS} ] )

    BUFFS [0]   - (dict of (stat(str):value(int))) A dict of all unit stat-modifying, with key being the stat, and value being the amount by which it changes
"""

from collections import OrderedDict
import time
import random
from random import randint
import math
import json

# Load ability data from JSON file
with open('abilities.json', 'r') as f:
    ability_data = json.load(f)
AbilitiesDict = ability_data['AbilitiesDict']
buffDict = ability_data['buffDict']

class Ability():
    #ATTR_NAME_LIST and AbilitiesDict store data about abilities and how they work
    ATTR_NAME_LIST = [["TARGET_TYPE", "TARGET_ENEMY", "TARGET_NUM"], ["SPECIAL", "LASTS", "CAN_DODGE"], ["MP_COST"], ["DMG_TYPE", "DMG_IS_PERCENT", "DMG_BASE", "DMG_ROLL"], ["IS_HEAL", "HP_GAIN", "MP_GAIN"], ["IS_BUFF", "BUFF_TRIGGER_ON", "BUFF_ENDS",  "BUFF_STACKS", "BUFF_STATUS"], ["INFO"]] 
    AbilitiesDict = AbilitiesDict  # Loaded from JSON
    buffDict = buffDict  # Loaded from JSON
    x = None
    ability_ID_counter = 0

    @classmethod
    def _normalize_ability_entry(cls, ability_definition):
        if isinstance(ability_definition, dict):
            return ability_definition.copy()

        normalized = {}
        for group_index, attr_names in enumerate(cls.ATTR_NAME_LIST):
            group_values = ability_definition[group_index] if group_index < len(ability_definition) else []
            for attr_index, attr_name in enumerate(attr_names):
                normalized[attr_name] = group_values[attr_index] if attr_index < len(group_values) else None
        return normalized

    def __init__(self, ability_name, ability_ID):       

        self.ability_ID = ability_ID    #is this needed? The only reference to an ability after its turn is over is through the Ability_queue, is that enough?
        Ability.ability_ID_counter += 1       #for ability_ID during creating... is this needed?

        self.ABILITY_NAME = ability_name                                                        #used to match to special method if needed
        self.target_list = None                                                                      #the target of this ability
        self.caster = None                                                                      #the one using this ability, used in helping determine if it's a players turn
        self.AttrValDict = self.build_AttrValDict()
        self.turns_left = self.AttrValDict["LASTS"]

        self.sp_val = None              #a place to store a value for this particular ability, e.g. target's DEF at time of casting
        
        self.special_mapDict = { "Sharpen sword" :  self.IncreaseATK,
            'Raise shield': self.RaiseShield,
            'Feint':  self.Feint, 
            'Taunt' :  self.Taunt,
            'Exhaust' :  self.Exhaust,
            "Poison": self.Poison ,
            "Leech": self.Leech,          
            "Frenzy": self.Frenzy          
            }

#========================================Class methods===========================================================================================
    #Uses ATTR_NAME_LIST and ability_dict to get an index and then value of (skill_name, ATTRIBUTE_NAME)
    #this is used when an Ability object is not refered to directly, e.g. getting MP for Unit.display_moves()
    
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

    #sets the target_list and caster for this ability, takes MP_COST, displays 'used' output, and for every target in target_list, check buff_stacks if is a buff and cast_on_target(), then check_Ability_queue() if needed
    def initial_cast(self, target_list, caster, battle):
        self.target_list = target_list                            #store target_list and caster in ability instance
        self.caster = caster
        self.last_damage_dealt = 0
        if self.AttrValDict["TARGET_TYPE"] == 1:
            print("{} used {} on {}!".format(caster.name, self.ABILITY_NAME, str(self.target_list[0])))
        else:
            print("{} used {}!".format(caster.name, self.ABILITY_NAME))

        success = True
        buff_applied_to_any = False
        for target in target_list:                      #for every target unit
            if self.AttrValDict["IS_BUFF"] and not self.check_stacks(target, battle):
                continue
            target_success = self.cast_on_target(target, caster)
            if self.AttrValDict["IS_BUFF"] and target_success is None:
                target.modify_buff_stack_dict("add", self.AttrValDict["BUFF_STATUS"])
                buff_applied_to_any = True
            if target_success is False:
                success = False

        if self.AttrValDict["IS_BUFF"]:
            success = success and buff_applied_to_any

        if success:
            caster.mp -= self.AttrValDict["MP_COST"]

        if self.turns_left > 0 and success:
            if self.AttrValDict["IS_BUFF"] and len(target_list) > 1:
                # Multi-target buffs/debuffs use one effect instance per target
                # so each unit tracks duration independently.
                for target in target_list:
                    per_target_effect = Ability(self.ABILITY_NAME, Ability.ability_ID_counter)
                    per_target_effect.caster = caster
                    per_target_effect.target_list = [target]
                    per_target_effect.turns_left = self.turns_left
                    battle.register_effect(per_target_effect)
            else:
                battle.register_effect(self)

        # for compatibility, support buff expiry after caster action if the ability has a delayed end
        if self.turns_left == 0 and self.AttrValDict["IS_BUFF"]:
            for target in self.target_list:
                target.modify_buff_stack_dict("remove", self.AttrValDict["BUFF_STATUS"])
        return success

    #if the ability is past its BUFF_STACKS limit, expire and remove the oldest instance of the same ability on the target
    def check_stacks(self, target, battle):
        times_stackable = self.AttrValDict["BUFF_STACKS"]
        buff_status = self.AttrValDict["BUFF_STATUS"]
        current_stacks = target.buff_stacks_dict.get(buff_status, 0)
        if current_stacks >= times_stackable:
            # Remove the oldest active effect with the same buff on this target
            for old_effect in battle.active_effects:
                if (old_effect.AttrValDict.get("BUFF_STATUS") == buff_status
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
            if self.AttrValDict["SPECIAL"]:              #put it first in order because ..
                success = self.special_sorter(target, caster)                           
                if success == None:                                                                     #if success == None (i.e. not False)
                    if self.AttrValDict["IS_BUFF"] and self.turns_left == 0:                                     #if ability was buff AND ability is expiring,,
                        target.modify_buff_stack_dict("remove", self.AttrValDict["BUFF_STATUS"])                    #remove this buff stack
                elif success == False:                                                                  #elif move was unsuccessful
                    self.turns_left = 0     
            dmg_type = self.AttrValDict["DMG_TYPE"]                                                                #set turns_left to 0 to be deleted by check_Ability_queue()
            if dmg_type in ["NORMAL", "MAGIC"]:
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
        if self.AttrValDict["IS_BUFF"]:                                             #return success to signal if check_stats should be called in initial_cast()
            return success
        return success

    def calculate_dmg(self, caster, dmg_type):        #uses DMG_BASE, DMG_ROLL, and caster.ATK/caster.MAGIC to calculate and return raw_damage
        minDMG, maxDMG = (self.AttrValDict["DMG_BASE"] - self.AttrValDict["DMG_ROLL"],
                            self.AttrValDict["DMG_BASE"] + self.AttrValDict["DMG_ROLL"])
        if dmg_type == "NORMAL":
            raw_damage = caster.ATK + randint(minDMG,maxDMG)
        elif dmg_type == "MAGIC":
            raw_damage = caster.MAGIC + randint(minDMG,maxDMG)
        return raw_damage

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
        if self.AttrValDict["IS_BUFF"] and self.turns_left != self.AttrValDict["LASTS"]:                #if it is a buff stack, it cannot be dodged
            return False
        if self.AttrValDict["CAN_DODGE"]:
            #print("Dodge is: {}".format(target.DODGE))                                 #for debugging
            if random.random() < target.DODGE/100:
                print("{} dodged the attack!".format(str(target)))
                return True
        return False

    #abilities with SPECIAL access this method to get to their special method, using special_mapDict
    def special_sorter(self, target, caster):
        if self.ABILITY_NAME in self.special_mapDict:
            success = self.special_mapDict[self.ABILITY_NAME](target, caster)
            return success
        else:
            print("special_sorter: ABILITY DOES NOT EXIST!!!!!!!!")             #for debugging

    #uses values in buffDict to find which unit stats to change. Usually called twice: at initial buff, and revert at expiration
    def buff_stat_modifier(self, add_remove, target):
        buff_values = Ability.buffDict[self.ABILITY_NAME]
        unit_stats = [target.max_hp, target.max_mp, target.ATK, target.DEF, target.CRIT, target.DODGE]          #HOW TO MAKE THIS WORK>>>>>>
        for index in range(len(buff_values)):
            if buff_values[index] != 0:
                val_to_add = buff_values[index]
                if add_remove == 'remove':
                    val_to_add = -buff_values[index]            #if method was called to remove, make value negative
                #print("This will be added: {}".format(val_to_add))                             #for debugging
                if index == 0:
                    target.max_hp += val_to_add
                elif index == 1:
                    target.max_mp += val_to_add  
                elif index == 2:
                    target.ATK += val_to_add   
                elif index == 3:
                    target.DEF += val_to_add    
                elif index == 4:
                    target.CRIT += val_to_add   
                elif index == 5:
                    target.DODGE += val_to_add       

#----------------------Special instance methods----------------------------------------------------
    #This section contains all methods used by abilities that have unique mechanics not covered by basic ones
    #
    def IncreaseATK(self, target, caster=None):             
        if self.turns_left == self.AttrValDict["LASTS"]:
            self.buff_stat_modifier("add", target)
            print("{} whets his sword until it is razor sharp (ATK +10)".format(str(target)))
        elif self.turns_left > 0:                                       #do nothing if in 2nd turn
            print("{}'s sword is still sharp".format(str(target)))
        elif self.turns_left == 0:                                     #reverse effects after last turn
            if self.AttrValDict["IS_BUFF"]:
                if self.AttrValDict["BUFF_TRIGGER_ON"] == 0:     
                    self.buff_stat_modifier("remove", target)
                    print("{}'s sword dulls (ATK -10)".format(str(target)))

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
        if self.turns_left == self.AttrValDict["LASTS"]:
            self.sp_val = target.DEF
            damage = self.AttrValDict["DMG_BASE"] - math.floor(self.sp_val / 2)
            if damage <= 0:
                print("The poison dart bounced off {}... their DEF is too high!".format(str(target)))
                return False
            target.hp -= damage
            print("{} took {} damage from a poison dart!".format(str(target), damage))
        else:
            stacks = target.buff_stacks_dict.get(self.AttrValDict["BUFF_STATUS"], 1)
            tick_damage = math.floor(2 + 2 * (stacks - 1))
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
        if self.turns_left == self.AttrValDict["LASTS"]:
            self.buff_stat_modifier("add", target)
            print("{}'s DEF has increased by 8!".format(str(target)))
        elif self.turns_left == 0:
            self.buff_stat_modifier("remove", target)
            print("{} lowers their shield".format(str(target)))

    #
    def Feint(self, target, caster=None):                                                                                  # also in future it could mean value could vary with unit stats e.g. MAGIC
        if self.turns_left == self.AttrValDict["LASTS"]:      #if just cast, increase ATK by 10
            self.buff_stat_modifier("add", target)
            print("{}'s DODGE has increased by 60%!".format(str(target)))
        elif self.turns_left == 0:                                                        #reverse effects in last turn
            self.buff_stat_modifier("remove", target)
            print("{} takes a steady stance. Their DODGE returns to normal.".format(str(target)))

    #
    def Taunt(self, target, caster=None):                                                                                  
        if self.turns_left == self.AttrValDict["LASTS"]:      #if just cast, 
            self.buff_stat_modifier("add", target)
            print("{}'s DEF has decreased by 6!".format(str(target)))
        elif self.turns_left == 0:                                                           #reverse effects in last turn
            self.buff_stat_modifier("remove", target)
            print("{} regains his composure. His DEF returns to normal".format(str(target)))
    #
    def Exhaust(self, target, caster=None):                                                                                  
        if self.turns_left == self.AttrValDict["LASTS"]:      #if just cast, 
            self.buff_stat_modifier("add", target)
            print("{}'s ATK and DEF have decreased by 4 and DODGE by 10!".format(str(target)))
        elif self.turns_left == 0:                                                           #reverse effects in last turn
            self.buff_stat_modifier("remove", target)
            print("{} regains his composure. His ATK, DEF, and DODGE return to normal.".format(str(target)))

    #
    def Frenzy(self, target, caster=None):                                                                                  
        if self.turns_left == self.AttrValDict["LASTS"]:      #if just cast, 
            self.buff_stat_modifier("add", target)
            print("{}'s ATK has increased by 6 and CRIT has increased by 15!".format(str(target)))
        elif self.turns_left == 0:                                                           #reverse effects in last turn
            self.buff_stat_modifier("remove", target)
            print("{} calms. His ATK and CRIT return to normal.".format(str(target)))


from Units import Unit, Unit_Knight, Unit_Thief, Unit_Priest