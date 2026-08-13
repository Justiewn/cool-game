"""Position-aware Unit subclasses for the hex prototype.

Wraps each FRAY class (Knight, Priestess, etc.) with a `.hex` attribute
and a `MOVE` stat. Everything else — HP/MP/ATK/DEF, effect_stacks_dict,
target_Ability_queue, subclass movesList and passives — is inherited.

Kept small on purpose: the hex layer is composition over FRAY units, not
a fork.
"""

import _bootstrap  # noqa: F401 — puts Prototypes/ on sys.path

from Units import (
    Unit, Unit_Knight, Unit_Priestess, Unit_Thief,
    Unit_Berserker, Unit_Assassin, Unit_Thug, Unit_Hunter, Unit_Spellblade,
)


DEFAULT_MOVE = 3   # baseline movement in hexes per turn


def _mixin_hex(base_cls, move=DEFAULT_MOVE):
    """Returns a subclass of `base_cls` that also carries .hex and .MOVE."""
    class _Hex(base_cls):
        MOVE = move

        def __init__(self, name, team):
            super().__init__(name, team)
            self.hex = None
    _Hex.__name__ = f"Hex{base_cls.__name__}"
    _Hex.__qualname__ = _Hex.__name__
    return _Hex


HexKnight    = _mixin_hex(Unit_Knight,    move=2)
HexPriestess = _mixin_hex(Unit_Priestess, move=2)
HexThief     = _mixin_hex(Unit_Thief,     move=3)
HexBerserker = _mixin_hex(Unit_Berserker, move=2)
HexAssassin  = _mixin_hex(Unit_Assassin,  move=3)
HexThug      = _mixin_hex(Unit_Thug,      move=2)
HexHunter    = _mixin_hex(Unit_Hunter,    move=2)
HexSpellblade = _mixin_hex(Unit_Spellblade, move=3)


HEX_CLASS_MAP = {
    "K":  HexKnight,
    "P":  HexPriestess,
    "TH": HexThief,
    "B":  HexBerserker,
    "A":  HexAssassin,
    "T":  HexThug,
    "H":  HexHunter,
    "SB": HexSpellblade,
}


if __name__ == "__main__":
    u = HexKnight("Aldric", 0)
    assert u.hex is None
    assert u.MOVE == 2
    assert u.ATK == Unit_Knight("_", 0).ATK  # inherited
    u.hex = (2, 1)
    assert u.hex == (2, 1)
    Unit.remove_all()
    print("hex_unit.py self-check OK")
