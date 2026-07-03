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

IS_SPECIAL (int) 
0 = only generic methods
1 = only a special method
2 = both generic and special methods should be used

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

TICKS (int) 
Number of (caster) moves this ability will last for (0 for immediate expiration)


EFFECT_TICKS_ON (int)
When the effect loses a tick 
0 = per turn (governed by EFFECT_TICK_OWNER + EFFECT_TICK_PHASE)
1 = per turn OR when the target attacks
2 = per turn OR when the target is attacked
3 = per turn OR when the target is attacked OR attacks
4 = when the target attacks
5 = when the target is attacked
6 = when the target is attacked OR attacks

EFFECT_TICK_OWNER (int)
0 = effect ticks on the target's TEAM turn
1 = effect ticks on the caster's TEAM turn
Only applies when EFFECT_TICKS_ON = 0
Turn order within a team is chosen freely by the player/AI, so we say
"team turn" rather than "unit turn". A tick still only fires for effects
where the relevant unit (target or caster) is on the team whose turn is
starting/ending.

EFFECT_TICK_PHASE (int)
0 = tick fires ONCE at the start of the relevant team's turn (before any
    unit on that team is picked to act). All PHASE=0 ticks for that team
    resolve in one batch — poison damage, buff-duration decrements, etc.
    Incapacitating effects (PREVENTS_ACTION=true, e.g. Stun) are the
    exception: they tick per-unit when the incapacitated unit is picked,
    so their "skip one turn" semantics stay intact.
1 = tick fires at the end of the relevant unit's action (after their cast
    resolves), same as before.

EFFECT_TICK_ON_HIT_ONLY (bool)
Only applies when EFFECT_TICKS_ON >= 1
true = tick only fires if the triggering attack actually lands (not dodged)
false = tick fires regardless of dodge

EFFECT_CASTER_DEATH (int)
What happens to this effect when the caster is downed
0 = effect is immediately removed when the caster is downed
1 = effect continues as a ghost tick — fires at the point in the turn order where the downed caster would have acted, until it expires (only applies to EFFECT_TICK_OWNER = 1 effects)
2 = effect is unaffected (immortal); caster death has no impact

EFFECT_TARGET_DEATH (int)
What happens to this effect when the target is downed
0 = effect is removed when the target is downed
1 = effect persists through downing; only removed when the target is permanently killed

EFFECT_STACKS [3] (int)
How many instances of this effect can exist on a target, (1 for no stacking)

EFFECT_STACK_RENEWS (bool, optional; default false)
Controls what happens to existing stacks when a new one is added:
false = each stack tracks its own turns_left independently, so the oldest
        stack expires first even if a newer one was just applied.
true  = adding a new stack refreshes ALL existing stacks of the same
        EFFECT_STATUS on the target back to full TICKS duration, so the
        effect expires as one bundle rather than in staggered ticks.
Only meaningful for stackable effects (EFFECT_STACKS > 1).

EFFECT_STATUS (str) 
the text displayed on the status pill

EFFECT_TOOLTIP (str)
the text displayed in the tooltip on hover over effect pill

EFFECT_VALUES (str array)
{"max_hp": 0, "max_mp": 0, "ATK": 0, "DEF": 0, "CRIT": 0, "DODGE": 0}
Can have any or null

PREVENTS_ACTION (bool, optional; default false)
If true, the target cannot take an action while any stack of this
effect is on them. When a picked unit has an active PREVENTS_ACTION
status, they auto-skip with a "X is stunned/asleep!" log line and
their per-unit tick cycle fires (all four resolve phases) so the
effect duration counts down normally. Used by Stun and Sleep.

TRIGGER_ON (str, optional)
Marks the ability as a passive that Battle fires automatically when
an event occurs, instead of being chosen from movesList.
"ALLY_DEATH" = fires on every surviving teammate when a teammate is
              downed. Currently used by Thug's Uproar passive.
Passives declared on a unit via Unit.passives = ["<name>", ...].

TOOLTIP_INFO
Text to appear as the first line in the ability tooltip


MISC
HIT_TYPE - SHARP, BLUNT, MAGIC - for hit sounds