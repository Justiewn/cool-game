"""
TO DO:
    - update docstrings......
    - Ability
        - TARGET_TYPE multiple needs to be implemented
        - add new abiltiy attribute BUFF_TRIGGER_ON for buffs, for when a buff should lose duration (turns_left)
            - if loses per caster turn, no changes needed (this is default)
            - if loses when being attacked, when another unit is targeted, 
                - first check if targetting ability is ATTACK_TYPE = "NORMAL" or "MAGIC", 
                - check target ability queue for IS_BUFF = TRUEs, and TRIGGER_ON = 1's then access those abilties, and -1 their turns_left
        - buff prompt dict
        - make abilities that use all ability attributes i.e. DMG_IS_PERCENT and DMG_TYPE
        - how will ability_ID work?
        - adding unit.target_Ability_queue, (to get Poison to show accumulated damage in one line rather than in seperate lines for each stack)
    - Unit
        - display_buff_prompts() should get prompts from a dicitonary rather than if/elifs
        - is SPEED needed?

v0.6.2 
Changes:
    Units:
    - added randomized names for all created units (names_list in Unit.create_units())
    - moved mp usage into unit.initial_cast() so that it is only taken if cast is successful
    Abilities:
    - shortened some variable names in Ability
        - AttributeValueDict > AttrValDict
        - ATTRIBUTE_NAME_LIST > ATTR_NAME_LIST
        - ability_dict > aDict
    - changed check_Ability_queue() so that it procs abilities in reverse (so all buffs proc before the oldest can be removed)
    - ability.check_stacks() is now only called if the ability is successful (this only applies to buffs)
    - unit.modify_buff_stacks_dict is now only used at two points, in check_stacks() (called by inital_cast()), and in cast_on_target() if ability expires
    - added ability attribute CAN_DODGE in 'others' section, which signifies if dodge should be considered (ability_dodged() is called regardless, but will return False if CAN_DODGE = False)
    - ability.special_mapDict now maps abilities to their respective methods
    - added ability.buff_stat_modifier() which takes values from Ability.buffDict to modify unit stats  
    - removed unit.comp_move(), computer will now use choose_move()
        - is_multiplayer will decide whether team 2 is user or computer
        - computer goes through same method calls (with altered blocks)
        - computer will currently always choose moveList's index 1 move and a random enemy
    - changed when display_health() is used (once at beginning of choose_move, once at the end)
    - user is required to press enter after every move (otherwise text moves too fast) 

v0.6.3
Changes:
    - replaced unit creation process
        - removed get_num_allies() and get_num_enemies(), replaced by get_team()
        - get_team gets input string of units (represented by abbreviated class names) to be created and is called once for each team
    - added string representation for units
        - use str(unit) for "(name) the (class)" or unit.name for "(name)" only
    - minor changes to some output text
    - removed limits on some unit stats (via setters)
    - added Ability.clear_target()
        - called in Unit.downed(), finds every ability that targets the downed unit and calls remove_ability() on them
    - added Ability.remove_ability()
        - removes an ability's buff indicator (in unit's stack dict), reverts its effects, and removes the ability from queue 
        - stat-modifying buffs that go over their stack limit will have their effect added, and the oldest in the stack will revert its effect and be removed
    - Poison slightly reworked
        - two instance variables added in Units, PSN_DMG and PSN_count to help keep track of poison damage (still needs to use unit.target_Ability_queue)
    - some abilities are now "MAGIC" damage type, and rather than using target's DEF to lower damage, target's MAGIC is used instead
        - added MAGIC setter/getter

UPTO:  added unit.target_Ability_queue, get Poison to show accumulated damage in one line rather than in seperate lines for each stack
"""
import os
import time
from battle import Battle
from Units import Unit, Unit_Knight, Unit_Thief, Unit_Priest

team_zero_limit = 3         #player included, min should be 1
team_one_limit = 5
is_multiplayer = False      #lets both teams be controlled




def get_yes_no(prompt, default=False):
    while True:
        choice = input(prompt).strip().lower()
        if choice in ("y", "yes"):
            return True
        if choice in ("n", "no"):
            return False
        if choice == "" and default is not None:
            return default
        print("Please enter Y or N.")


def main(team_zero_limit, team_one_limit, is_multiplayer):
    run_game = True
    while run_game:
        battle = Battle()
        #get player name and teams
        Unit.player_name = input("What is your name?\n> ")
        time.sleep(0.2)
        print("------------------------[TEAM CREATION]------------------------")
        is_multiplayer = get_yes_no("Do you want to control the enemy team as well? [Y/N]\n> ")
        get_team(team_zero_limit, 0)
        get_team(team_one_limit, 1)

        input("\n<Press ENTER to start the battle>\n")
        os.system('cls')
        #begin battle while loop, stop loop when all of one team is dead
        while Unit.num_units(0, "alive") > 0 and Unit.num_units(1, "alive") > 0:
            print("-----------------------[Team 1's turn]-----------------------")
            for unit in Unit.get_units("alive", 0):
                unit.choose_move(battle)

                if Unit.num_units(1, "alive") <= 0:
                    break
            if Unit.num_units(1, "alive") <= 0:
                print("\nYou win!\n")
                break

            print("-----------------------[Team 2's turn]-----------------------")
            for unit in Unit.get_units("alive", 1):
                unit.choose_move(battle, is_multiplayer=is_multiplayer)

                if Unit.num_units(0, "alive") <= 0:
                    print("\nYou lose!\n")
                    break
        Unit.remove_all()
        run_game = play_again()
########################################################################################

def get_team(team_limit, team):
    valid_classes = ['T', 'P', 'K', 'TH']
    say = ['YOUR TEAM','ENEMY TEAM']
    print("\n========== {} ==========\n  ====== Team limit: {} ======\n\n\
        Available classes:\n\
  T  = Thug           K  = Knight\n\
  P  = Priest         TH = Thief\n".format(say[team], team_limit))
    print("e.g. To create a team of 2 Knights and 1 Priest, use: P K K\n")

    valid = False
    while not valid:
        created_team = input(">> ").upper().strip()
        units_to_create = created_team.split() if created_team else []
        if len(units_to_create) not in range(0, team_limit + 1):
            print("There may only be {} or less units in this team!".format(team_limit))
            continue

        invalid_unit = next((unit for unit in units_to_create if unit not in valid_classes), None)
        if invalid_unit:
            print("Invalid input \"{}\". Please try again!".format(invalid_unit))
            continue

        valid = True
    Unit.create_units(units_to_create, team)

######################play again input#####################
def play_again():
    if get_yes_no("Would you like to play again? [Y/N]\n> "):
        print("\n\n\n\n\n\n RESTARTING \n")
        time.sleep(1)
        os.system('cls')
        return True
    print("Goodbye")
    time.sleep(1.5)
    return False

if __name__ == "__main__":
    main(team_zero_limit, team_one_limit, is_multiplayer)
