"""Construction: x = Unit(name (str), team (int))

Class methods
    - Unit.create_units(player_name, num_allies, num_enemies): called by main() to create units at the start of the game
    - Unit.num_units(team, all_or_alive): returns the len() of one of four team lists (team zero/one, all/alive)
    - Unit.get_units(all_or_alive, team): returns one of four team lists (team zero/one, all/alive)
    - Unit.remove(unit): removes unit from its respective team list
    - Unit.display_health(): Prints HP of all currently alive Units in a formatted manner.
    - Unit.remove_all(): clears all unit lists of units, called at end of game in main()
    - Unit.downed(): checks all units for dead units and calls unit.kill() on them

Instance methods
    - x.choose_move(calling_ability=None, is_multiplayer = True): get a valid move from user input, or generate move for computer
    - x.display_moves(movesList): display the unit's list of moves, their MP cost, and info about their moves
    - x.mp_check(mp_required): checks if enough mana, if enough return True, else False
    - x.is_dead(): returns True if Unit has <0HP and changes x.alive = False. Else returns False
    - x.display_buff_prompts(): displays prompts for buffs in buff_stacks_dict                              #needs work
    - x.modify_buff_stack_dict(add_or_remove, buff_name): simple dict entry adder/remover used by ability.check_stacks and special methods (for removing buff on expiration)
"""
import os
import copy
import time
from collections import OrderedDict
import random
from random import randint


class Unit:

    className = "Thug"
    player_name = "Player"
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
        self.buff_stacks_dict = {}        #can only be modified by modify_buff_stack_dict, which is called at two points: in check_stack() and at ability expiration (in special method)

        self._hp = 100                    #cannot surpass max_hp (stops at max in setter method)
        self._mp = 25                    #cannot surpass max_mp (stops at max in setter method)

        self._max_hp = 100
        self._max_mp = 25
        self._ATK = 10
        self._DEF = 3            # dmg - defense = final dmg
        self._MAGIC = 0                                                                 #just magic and no magic_def? so high magic is ineffective against high magic
        self._MAGIC_DEF = 0            # magic dmg - magic defense = final dmg
        self._CRIT = 10          # /100%
        self._DODGE = 5          # /100%
        self._SPEED = 12         # max speed is 20

        self.movesList = ["Rest", "Punch", 'First aid']

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
        return self.name + " the " + Unit.className

#~~~~~~~~~~~~Class methods~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    #initialise all Units that will be present in this game loop
    @classmethod
    def create_units(cls,units_to_create, team):

        team_name = ["your team", "the enemy team"]

        names_list = ["John", "George", "Geoffrey", "Simon", "Gerrard", "Henry", "Tobias", "Dodd", "Norman", "Roland" , 'Amon', 'Daniel', "Richard", "Amos", "Charles",
                        "Cedrick"]

        abb_to_class = {'T': Unit, 'P' : Unit_Priest, 'K' : Unit_Knight, 'TH': Unit_Thief}
        if Unit.player_name == '':
            Unit.player_name = 'Justin'

        #if player_name == 'Knight':
            #player = Unit_Knight(player_name + " the Knight", 0)
        print()
        for i in range(len(units_to_create)):
            if team == 0 and i == 0:
                name = Unit.player_name
            else:
                name = names_list.pop(random.randint(0, len(names_list)-1))
            created_unit = abb_to_class[units_to_create[i]](name, team)
            print("+ {} has joined {}!".format(str(created_unit), team_name[team]))
            time.sleep(0.3)

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

    #returns a list of currently alive units in chosen team, used in AbilityObject.select_target()
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

    #prints hp of all alive Units
    @classmethod
    def display_health(cls):   

        def display(unit):
            status = " DOWN" if not unit.alive else ""
            print("        {:20} HP:{:3}/{:3}    MP:{:3}/{:3}{}  ".format(
                str(unit), unit.hp, unit.max_hp, unit.mp, unit.max_mp, status), end='')
            for buff, stacks in unit.buff_stacks_dict.items():
                print(" " + buff, end='')
                if stacks > 1:
                    print("x" + str(stacks), end='')
            print()

        print("\n       ===============================================")
        for ally in Unit.team_zero_list:
            display(ally)
        print("        -----------------------------------------------")
        for enemy in Unit.team_one_list:
            display(enemy)
        print("       ===============================================\n")


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

    #acquire valid move from user, then create an Ability object and put in Ability.Ability_queue, then call object.determine_targets() through that object
    def choose_move(self, battle, calling_ability=None, is_multiplayer = True):
        move_id_counter = 0
        if calling_ability is not None:
            battle.remove_effect(calling_ability)
        battle.resolve_turn_start(self)
        Unit.display_health()                   #display HP of all alive Units
        Unit.downed(battle)                          #confirm any dead units at this point
        if Unit.num_units(1 - self.team, "alive") <= 0:                 #check win condition for this unit's team,
            return                                                          #if true, return

        print("    -------------- {}'s move --------------".format(str(self)))
        time.sleep(0.8)

        if is_multiplayer:
            self.display_moves(self.movesList)
            # self.display_buff_prompts()
            while True:
                print("> What would you like to do?")
                try:
                    self_move = int(input(">"))
                    if self_move in range(1, len(self.movesList) + 1):
                        move_name = self.movesList[self_move - 1]
                        mana_required = Ability.get_attr(move_name, "MP_COST")
                        if self.mp_check(mana_required):
                            break
                        continue
                    print("Please enter a number between 1-{}\n".format(len(self.movesList)))
                except ValueError:
                    print("Please enter a number between 1-{}\n".format(len(self.movesList)))
        else:
            # self.display_buff_prompts()
            move_name = self.movesList[1]
        current_Ability = Ability(move_name, Ability.ability_ID_counter)    #create Ability object
        target_list = current_Ability.determine_targets(self, battle, is_multiplayer)               #call ability's determine_targets
        if target_list is None:
            return
        battle.resolve_after_action(self)
        Unit.downed(battle)
        time.sleep(0.6)
        Unit.display_health()                  #display HP of all alive Units
        input("Press <ENTER> to continue...\n")
        os.system('cls')

    #Displays a unit's moveList
    def display_moves(self, movesList):
        for index, move in enumerate(movesList, start=1):
            print("{}. {:18}".format(index, move), end='')
            mp_cost = Ability.get_attr(move, "MP_COST")
            if mp_cost != 0:
                print("MP cost: {:<3}  ".format(mp_cost), end='')
            else:
                print("No cost       ", end='')
            print(Ability.get_attr(move, "INFO"))
            time.sleep(0.08)

    #checks if enough mana, if enough then return True, else False
    def mp_check(self, mp_required):
        if mp_required <= self.mp:
            return True
        print("Not enough MP!\n")
        return False

    #checks if hp of a unit is <= 0, if True, self.alive = False and return True
    def is_dead(self):
        if self.hp <= 0:
            self.alive = False
            return True
        return False

    def display_buff_prompts(self):
        if not self.buff_stacks_dict:
            return
        print()
        prompts = []
        for buff_name, stacks in self.buff_stacks_dict.items():
            if stacks > 1:
                prompts.append(f"{buff_name} x{stacks}")
            else:
                prompts.append(buff_name)
        print(f"{str(self)} has active effects: {', '.join(prompts)}")


    def modify_buff_stack_dict(self, add_or_remove, buff_name):
        if add_or_remove == "add":                                      #if a buff needs to be added
            if buff_name in self.buff_stacks_dict:                          #if buff entry exists, just add 1 to stack
                self.buff_stacks_dict[buff_name] += 1
            else:                                                           #else create entry with 1 stack
                self.buff_stacks_dict[buff_name] = 1
        elif add_or_remove == "remove":                                 #if a buff needs to be removed
            if buff_name in self.buff_stacks_dict:                          #if buff exists (double checking so no errors happen)
                if self.buff_stacks_dict[buff_name] >= 2:                        #if there are at least 2 stacks remaining then remove one stack
                    self.buff_stacks_dict[buff_name] -= 1
                else:                                                           #else there is only one, so remove the entry
                    del self.buff_stacks_dict[buff_name]
            else:
                pass
                #print("no {} to delete in {}'s buff_stack_dict".format(buff_name, str(self)))               #for debugging

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

    def __init__(self, name, team):
        super().__init__(name, team)


        self.max_hp = 100
        self.max_mp = 20
        self.hp = 100                    #cannot surpass max_hp (stops at max in setter method)
        self.mp = 20                    #cannot surpass max_mp (stops at max in setter method)

        self.ATK = 18
        self.DEF = 8            # dmg - defense = final dmg
        self.MAGIC = 0
        self.MAGIC_DEF = 0 
        self.CRIT = 10          # /100%
        self.DODGE = 1          # /100%
        self.SPEED = 6         # max speed is 20

        self.movesList = ["Rest", "Sword slash", 'Raise shield', 'Sharpen sword']

    def __str__(self):
        return self.name + " the " + Unit_Knight.className

class Unit_Thief(Unit):

    className = "Thief"

    def __init__(self, name, team):
        super().__init__(name, team)

        self.max_hp = 100
        self.max_mp = 30
        self.hp = 100                    #cannot surpass max_hp (stops at max in setter method)
        self.mp = 30                    #cannot surpass max_mp (stops at max in setter method)

        self.ATK = 12
        self.DEF = 3            # dmg - defense = final dmg
        self.MAGIC = 2
        self.MAGIC_DEF = 2 
        self.CRIT = 20          # /100%
        self.DODGE = 15          # /100%
        self.SPEED = 16         # max speed is 20

        self.movesList = ["Rest", "Dagger Stab", 'Sneak', 'Poison', 'Deceive']

    def __str__(self):
        return self.name + " the " + Unit_Thief.className

class Unit_Priest(Unit):

    className = "Priest"

    def __init__(self, name, team):
        super().__init__(name, team)

        self.max_hp = 100
        self.max_mp = 60
        self.hp = 100                    #cannot surpass max_hp (stops at max in setter method)
        self.mp = 60                    #cannot surpass max_mp (stops at max in setter method)

        self.ATK = 5
        self.DEF = 1            # dmg - defense = final dmg
        self.MAGIC = 14
        self.MAGIC_DEF = 10 
        self.CRIT = 5          # /100%
        self.DODGE = 5          # /100%
        self.SPEED = 10         # max speed is 20

        self.movesList = ["Rest", "Magic bolt", 'Heal', 'Heal team']

    def __str__(self):
        return self.name + " the " + Unit_Priest.className

class Unit_Berserker(Unit):

    className = "Berserker"

    def __init__(self, name, team):
        super().__init__(name, team)


        self.max_hp = 100
        self.max_mp = 20
        self.hp = 100                    #cannot surpass max_hp (stops at max in setter method)
        self.mp = 20                    #cannot surpass max_mp (stops at max in setter method)

        self.ATK = 15
        self.DEF = 3            # dmg - defense = final dmg
        self.MAGIC = 0
        self.MAGIC_DEF = 0 
        self.CRIT = 15          # /100%
        self.DODGE = 5          # /100%
        self.SPEED = 8         # max speed is 20

        self.movesList = ["Rest", "Cleave", "Frenzy", "Taunt"]

    def __str__(self):
        return self.name + " the " + Unit_Berserker.className

class Unit_Assassin(Unit):

    className = "Assassin"

    def __init__(self, name, team):
        super().__init__(name, team)

        self.max_hp = 100
        self.max_mp = 35
        self.hp = 100                    #cannot surpass max_hp (stops at max in setter method)
        self.mp = 35                    #cannot surpass max_mp (stops at max in setter method)

        self.ATK = 14
        self.DEF = 2            # dmg - defense = final dmg
        self.MAGIC = 0
        self.MAGIC_DEF = 0 
        self.CRIT = 25          # /100%
        self.DODGE = 10          # /100%
        self.SPEED = 20         # max speed is 20

        self.movesList = ["Rest", "Dagger Stab", 'Shroud', 'Mark', 'Finish']

    def __str__(self):
        return self.name + " the " + Unit_Assassin.className

from Abilities import Ability