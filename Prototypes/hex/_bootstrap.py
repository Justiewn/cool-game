"""Adds the parent Prototypes/ dir to sys.path so hex/ modules can import
FRAY's Units, Abilities, battle, ai as libraries without renaming or
packaging. Import this at the top of any hex module that reaches into FRAY.
"""
import os
import sys

_PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)
