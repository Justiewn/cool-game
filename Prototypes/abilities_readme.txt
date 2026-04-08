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