"""
TO DO:
        - is SPEED needed?
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
