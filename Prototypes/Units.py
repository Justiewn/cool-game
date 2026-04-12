"""Construction: x = Unit(name (str), team (int))

Class methods
    - Unit.num_units(team, all_or_alive): returns the len() of one of four team lists (team zero/one, all/alive)
    - Unit.get_units(all_or_alive, team): returns one of four team lists (team zero/one, all/alive)
    - Unit.kill_unit(unit): removes unit from its respective team alive list
    - Unit.remove_all(): clears all unit lists of units, called at end of game in main()
    - Unit.downed(): checks all units for dead units and calls unit.kill() on them

Instance methods
    - x.is_dead(): returns True if Unit has <0HP and changes x.alive = False. Else returns False
    - x.choose_ai_move(): returns a valid move name string for an AI-controlled unit
    - x.modify_effect_stack_dict(add_or_remove, effect_name): simple dict entry adder/remover used by ability.check_stacks and special methods (for removing effect on expiration)
"""
import os
import copy
import time
import random
from random import randint


class Unit:

    className = "Thug"
    player_name = "Player"
    name_pool = ["Brutus", "Rex", "Knuckles", "Mack", "Biff", "Sledge", "Dirk", "Crank"]
    team_zero_list = []
    team_zero_alive_list = []
    team_one_list = []
    team_one_alive_list = []
    all_units_list = [team_zero_list, team_one_list]
    all_alive_units_list = [team_zero_alive_list, team_one_alive_list]

    def __init__(self, name, team):
        self.name = name
        self.team = team            #0= player , 1 = enemy
        self.alive = True       #use to determine if unit is allowed a move and is targetable
        self.effect_stacks_dict = {}        #can only be modified by modify_effect_stack_dict, which is called at two points: in check_stack() and at ability expiration (in special method)

        self._hp = 100                    #cannot surpass max_hp (stops at max in setter method)
        self._mp = 15                    #cannot surpass max_mp (stops at max in setter method)

        self._max_hp = 100
        self._max_mp = 15
        self._ATK = 10
        self._DEF = 2            # dmg - defense = final dmg
        self._MAGIC = 0                                                                 #just magic and no magic_def? so high magic is ineffective against high magic
        self._MAGIC_DEF = 0            # magic dmg - magic defense = final dmg
        self._CRIT = 5          # /100%
        self._DODGE = 5          # /100%
        self._SPEED = 10         # max speed is 20

        self.movesList = ["Rest", "Punch", "Bandage", "Uproar"]

        self.target_Ability_queue = []                   #a list that contains all current abilities this unit is a target of

        ##ability specific attributes
        self.PSN_dmg = 0
        self.PSN_count = 0

        if self.team == 0:
            Unit.team_zero_list.append(self)
            Unit.team_zero_alive_list.append(self)
        elif self.team == 1:
            Unit.team_one_list.append(self)
            Unit.team_one_alive_list.append(self)

    def __str__(self):
        return Unit.className + " | " + self.name

#~~~~~~~~~~~~Class methods~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #returns len() of a team_list or team_alive_list using parameters team = 0, 1, all_alive = "all", "alive"
    @classmethod
    def num_units(cls, team, all_or_alive):
        if team == 0:
            if all_or_alive == "all":
                return len(Unit.team_zero_list)
            elif all_or_alive == "alive":
                return len(Unit.team_zero_alive_list)
        if team == 1:
            if all_or_alive == "all":
                return len(Unit.team_one_list)
            elif all_or_alive == "alive":
                return len(Unit.team_one_alive_list)

    #returns a list of currently alive units in chosen team
    @classmethod
    def get_units(cls, all_or_alive,  team):
        if team == 0:
            if all_or_alive == "all":
                return Unit.team_zero_list
            elif all_or_alive == "alive":
                return Unit.team_zero_alive_list
        if team == 1:
            if all_or_alive == "all":
                return Unit.team_one_list
            elif all_or_alive == "alive":
                return Unit.team_one_alive_list

    #removes unit from its team alive_list (use after checking is_dead())
    @classmethod
    def kill_unit(cls, unit):
        if unit.team == 0:
            Unit.team_zero_alive_list.remove(unit)
        if unit.team == 1:
            Unit.team_one_alive_list.remove(unit)

    @classmethod
    def remove_all(cls):
        for l in [Unit.team_zero_list, Unit.team_zero_alive_list, Unit.team_one_list, Unit.team_one_alive_list]:
            l.clear()

    # checks all units, if unit is_dead(), call kill_unit() and remove effects targeting them
    @classmethod
    def downed(cls, battle=None):
        for team in [Unit.team_zero_list, Unit.team_one_list]:
            for unit in team[:]:
                if unit.is_dead():
                    if unit in Unit.team_zero_alive_list or unit in Unit.team_one_alive_list:
                        Unit.kill_unit(unit)
                        time.sleep(0.4)
                        print("{} is down!\n".format(str(unit)))
                        if battle is not None:
                            battle.remove_target_effects(unit)

#~~~~~~~~~~~~Instance methods~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    #checks if hp of a unit is <= 0, if True, self.alive = False and return True
    def is_dead(self):
        if self.hp <= 0:
            self.alive = False
            return True
        return False

    def choose_ai_move(self):
        from Abilities import Ability
        def can_use_move(move_name):
            mp_cost = Ability.get_attr(move_name, "MP_COST")
            if mp_cost > self.mp:
                return False
            target_type = Ability.get_attr(move_name, "TARGET_TYPE")
            target_enemy = Ability.get_attr(move_name, "TARGET_ENEMY")
            if target_type == 0:
                return True
            if target_enemy:
                targets = Unit.get_units("alive", 1 - self.team)
            else:
                targets = Unit.get_units("alive", self.team)
            return bool(targets)

        hp_ratio = (self.hp / self.max_hp) if self.max_hp else 0
        if hp_ratio >= 0.15 and len(self.movesList) > 1:
            second_move = self.movesList[1]
            if can_use_move(second_move):
                return second_move

        valid_moves = []
        for move in self.movesList:
            if can_use_move(move):
                valid_moves.append(move)

        if hp_ratio < 0.15 and "Rest" in valid_moves:
            return "Rest"

        return random.choice(valid_moves) if valid_moves else None

    def modify_effect_stack_dict(self, add_or_remove, effect_name):
        if add_or_remove == "add":                                      #if an effect needs to be added
            if effect_name in self.effect_stacks_dict:                          #if effect entry exists, just add 1 to stack
                self.effect_stacks_dict[effect_name] += 1
            else:                                                           #else create entry with 1 stack
                self.effect_stacks_dict[effect_name] = 1
        elif add_or_remove == "remove":                                 #if an effect needs to be removed
            if effect_name in self.effect_stacks_dict:                          #if effect exists (double checking so no errors happen)
                if self.effect_stacks_dict[effect_name] >= 2:                        #if there are at least 2 stacks remaining then remove one stack
                    self.effect_stacks_dict[effect_name] -= 1
                else:                                                           #else there is only one, so remove the entry
                    del self.effect_stacks_dict[effect_name]
            else:
                pass
                #print("no {} to delete in {}'s effect_stack_dict".format(effect_name, str(self)))               #for debugging

#===================setters and getters for Unit object stats======================
    @property
    def hp(self):
        return self._hp

    @hp.setter
    def hp(self, val):
        if val < 0:
            self._hp = 0
        elif val > self.max_hp:
            self._hp = self.max_hp
        else:
            self._hp = val
    #--------------------------
    @property
    def mp(self):
        return self._mp

    @mp.setter
    def mp(self, val):
        if val < 0:
            self._mp = 0
        elif val > self.max_mp:
            self._mp = self.max_mp
        else:
            self._mp = val
    #--------------------------
    @property
    def max_hp(self):
        return self._max_hp

    @max_hp.setter
    def max_hp(self, val):
        if val < 1:
            self._max_hp = 1
        elif val > 1000:
            self._max_hp = 1000
        else:
            self._max_hp = val
        #if val < self.hp:                       #add this? if new max_hp is lower than current hp, lower current hp to new max_hp
           # self.hp = val                              #or can just lower both if ability needs to
    #--------------------------
    @property
    def max_mp(self):
        return self._max_mp

    @max_mp.setter
    def max_mp(self, val):
        if val < 0:
            self._max_mp = 0
        elif val > 1000:
            self._max_mp = 1000
        else:
            self._max_mp = val
        #if val < self.mp:                       #add this? if new max_mp is lower than current mp, lower current mp to new max_mp
           # self.mp = val                              #or can just lower both if ability needs to
    #--------------------------
    @property
    def ATK(self):
        return self._ATK

    @ATK.setter
    def ATK(self, val):
        if val < 0:
            self._ATK = 0
        #elif val > 100:
            #self._ATK = 100
        else:
            self._ATK = val
    #--------------------------
    @property
    def DEF(self):
        return self._DEF

    @DEF.setter
    def DEF(self, val):
        if val < 0:
            self._DEF = 0
        #elif val > 100:
            #self._DEF = 100
        else:
            self._DEF = val
    #--------------------------
    @property
    def MAGIC(self):
        return self._MAGIC

    @MAGIC.setter
    def MAGIC(self, val):
        if val < 0:
            self._MAGIC = 0
        #elif val > 100:
            #self._MAGIC = 100
        else:
            self._MAGIC = val
    #--------------------------
    @property
    def MAGIC_DEF(self):
        return self._MAGIC_DEF

    @MAGIC_DEF.setter
    def MAGIC_DEF(self, val):
        if val < 0:
            self._MAGIC_DEF = 0
        #elif val > 100:
            #self._MAGIC_DEF = 100
        else:
            self._MAGIC_DEF = val
    #--------------------------
    @property
    def CRIT(self):
        return self._CRIT

    @CRIT.setter
    def CRIT(self, val):
        if val < 0:
            self._CRIT = 0
        #elif val > 100:
            #self._CRIT = 100
        else:
            self._CRIT = val
    #--------------------------
    @property
    def DODGE(self):
        return self._DODGE

    @DODGE.setter
    def DODGE(self, val):
        if val < 0:
            self._DODGE = 0
        #elif val > 100:
        #    self._DODGE = 100
        else:
            self._DODGE = val
    #--------------------------
    @property
    def SPEED(self):
        return self._SPEED

    @SPEED.setter
    def SPEED(self, val):
        if val < 0:
            self._SPEED = 0
        elif val > 20:
            self._SPEED = 20
        else:
            self._SPEED = val
    #--------------------------
    @property
    def alive(self):
        return self._alive

    @alive.setter
    def alive(self, val):
        self._alive = val
    #--------------------------
    @property
    def PSN_dmg(self):
        return self._PSN_dmg

    @PSN_dmg.setter
    def PSN_dmg(self, val):
        self._PSN_dmg = val
    #--------------------------
    @property
    def PSN_count(self):
        return self._PSN_count

    @PSN_count.setter
    def PSN_count(self, val):
        self._PSN_count = val
    #--------------------------
##################### Unit sub-classes #########################################

class Unit_Knight(Unit):

    className = "Knight"
    name_pool = ["Aldric", "Roland", "Gareth", "Percival", "Baldwin", "Edmund", "Gawain", "Tristan"]

    def __init__(self, name, team):
        super().__init__(name, team)


        self.max_hp = 100
        self.max_mp = 18
        self.hp = 100                    #cannot surpass max_hp (stops at max in setter method)
        self.mp = 18                    #cannot surpass max_mp (stops at max in setter method)

        self.ATK = 18
        self.DEF = 8            # dmg - defense = final dmg
        self.MAGIC = 0
        self.MAGIC_DEF = 0 
        self.CRIT = 15          # /100%
        self.DODGE = 1          # /100%
        self.SPEED = 6         # max speed is 20

        self.movesList = ["Rest", "Sword slash", 'Raise shield', 'Sharpen sword']

    def __str__(self):
        return Unit_Knight.className + " | " + self.name

class Unit_Thief(Unit):

    className = "Thief"
    name_pool = ["Sly", "Jinx", "Nix", "Flick", "Pip", "Shadow", "Kip"]

    def __init__(self, name, team):
        super().__init__(name, team)

        self.max_hp = 100
        self.max_mp = 25
        self.hp = 100                    #cannot surpass max_hp (stops at max in setter method)
        self.mp = 25                    #cannot surpass max_mp (stops at max in setter method)

        self.ATK = 11
        self.DEF = 3            # dmg - defense = final dmg
        self.MAGIC = 2
        self.MAGIC_DEF = 6 
        self.CRIT = 20          # /100%
        self.DODGE = 10          # /100%
        self.SPEED = 16         # max speed is 20

        self.movesList = ["Rest", "Shiv", 'Sneak', 'Distract']

    def __str__(self):
        return Unit_Thief.className + " | " + self.name

class Unit_Priest(Unit):

    className = "Priest"
    name_pool = ["Ansel", "Caleb", "Dorian", "Elias", "Finn", "Gregory", "Hugh", "Isaiah"]

    def __init__(self, name, team):
        super().__init__(name, team)

        self.max_hp = 100
        self.max_mp = 50
        self.hp = 100                    #cannot surpass max_hp (stops at max in setter method)
        self.mp = 50                    #cannot surpass max_mp (stops at max in setter method)

        self.ATK = 5
        self.DEF = 1            # dmg - defense = final dmg
        self.MAGIC = 14
        self.MAGIC_DEF = 10 
        self.CRIT = 5          # /100%
        self.DODGE = 5          # /100%
        self.SPEED = 10         # max speed is 20

        self.movesList = ["Rest", "Smite", 'Heal', "Bless", 'Rejuvenation']

    def __str__(self):
        return Unit_Priest.className + " | " + self.name

class Unit_Berserker(Unit):

    className = "Berserker"
    name_pool = ["Ragnar", "Bjorn", "Thorvald", "Ulf", "Gunnar", "Havar", "Sigurd", "Ivar"]

    def __init__(self, name, team):
        super().__init__(name, team)


        self.max_hp = 100
        self.max_mp = 20
        self.hp = 100                    #cannot surpass max_hp (stops at max in setter method)
        self.mp = 20                    #cannot surpass max_mp (stops at max in setter method)

        self.ATK = 14
        self.DEF = 5            # dmg - defense = final dmg
        self.MAGIC = 0
        self.MAGIC_DEF = 0 
        self.CRIT = 10          # /100%
        self.DODGE = 5          # /100%
        self.SPEED = 8         # max speed is 20

        self.movesList = ["Rest", "Cleave", "Frenzy", "Taunt"]

    def __str__(self):
        return Unit_Berserker.className + " | " + self.name

class Unit_Assassin(Unit):

    className = "Assassin"
    name_pool = ["Vex", "Cipher", "Dusk", "Wraith", "Null", "Shade", "Ghost", "Zephyr"]

    def __init__(self, name, team):
        super().__init__(name, team)

        self.max_hp = 100
        self.max_mp = 25
        self.hp = 100                    #cannot surpass max_hp (stops at max in setter method)
        self.mp = 25                    #cannot surpass max_mp (stops at max in setter method)

        self.ATK = 12
        self.DEF = 2            # dmg - defense = final dmg
        self.MAGIC = 0
        self.MAGIC_DEF = 0 
        self.CRIT = 25          # /100%
        self.DODGE = 10          # /100%
        self.SPEED = 20         # max speed is 20

        self.movesList = [ 'Shroud', "Stab/Backstab", 'Mark', 'Poison']

    def __str__(self):
        return Unit_Assassin.className + " | " + self.name