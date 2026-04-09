All abilities should be declared in Ability_dict and should follow this format:

TARGET_TYPE
0 = self,       
1 = single,     
2 = multiple,   
3 = team (units in the team will no be differentiated),   
4 =  all (units will not be differentiated)

TARGET_ENEMY 
True = targets enemies
False = targets allies (use x if TARGET_TYPE = self, all )

TARGET_NUM  (int) 
Number of targets if TARGET_TYPE = multiple

SPECIAL (int) 
0 = only initial methods
1 = only a special method
2 = both initial and special methods should be used

LASTS (int) 
Number of (caster) moves this ability will last for (0 for immediate expiration)

CAN_DODGE (boolean) 
If ability can be dodged, True, else False

MP_COST [2]

DMG_TYPE (string) 
"NORMAL" or "MAGIC" if move does initial damage, 
False otherwise and ignore rest of section

DMG_IS_PERCENT (boolean)

DMG_BASE (int) 
base damage of this ability. This is added onto the ATK of the unit

DMG_ROLL (int) 
amount by which base damage may deviate each way, i.e. DMG_BASE ± DMG ROLL = Damage range (0 for no deviation) 

IS_HEAL (bool) 
Uses any of this section means True, else False and ignore rest of section

HP_GAIN (int) HP healed (0 for none)

MP_GAIN (int) MP gained (0 for none)

IS_EFFECT (bool) 

EFFECT_TICK_OWNER (int) 
0 = effect ticks on the target's turn, 1 = effect ticks on the caster's turn
Only applies when EFFECT_TRIGGERS_ON = 0

EFFECT_TICK_PHASE (int)
0 = tick fires at the start of the relevant turn, 1 = tick fires at the end of the relevant turn

EFFECT_TRIGGERS_ON (int)
0 = effect loses a tick per turn (governed by EFFECT_TICK_OWNER + EFFECT_TICK_PHASE)
1 = effect loses a tick when the target is attacked
2 = effect loses a tick when the target attacks
3 = effect loses a tick when the target is attacked OR attacks

EFFECT_TICK_ON_HIT_ONLY (bool)
Only applies when EFFECT_TRIGGERS_ON >= 1
true = tick only fires if the triggering attack actually lands (not dodged)
false = tick fires regardless of dodge

EFFECT_STACKS [3] (int) 
How many instances of this effect can exist on a target, (1 for no stacking) 

EFFECT_STATUS (str) 
the text displayed on the status pill

EFFECT_TOOLTIP (str)
the text displayed in the tooltip on hover over effect pill

EFFECT_VALUES (str array)
{"max_hp": 0, "max_mp": 0, "ATK": 0, "DEF": 0, "CRIT": 0, "DODGE": 0}
Can have any or null

TOOLTIP_INFO
Text to appear as the first line in the ability tooltip


MISC
HIT_TYPE - SHARP, BLUNT, MAGIC - for hit sounds