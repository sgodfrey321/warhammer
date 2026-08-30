"""Auto-bootstraps whatever roster-level state a roster's declared Army Faction is known to
need on import -- Battle Focus for Asuryani today, more to follow per-faction as they're
built (see asuryani.py). Deliberately not a generic "parse any army rule into state" engine:
the catalogue-level army rules vary too much in shape (dice-roll-and-choose, per-unit status
effects, static once-per-battle choices, plain reference text -- see docs/TODO.md) for one
general mechanism to model them all, so each faction gets its own small handler instead."""

from __future__ import annotations

from collections import Counter
from typing import Callable

from sqlmodel import Session

from ..models import Roster, UnitDefinition
from . import asuryani

Handler = Callable[[Roster, Session], None]

_HANDLERS: dict[str, Handler] = {
    "Asuryani": asuryani.bootstrap,
}


def derive_army_faction(definitions: list[UnitDefinition]) -> str | None:
    """The roster's declared Army Faction (e.g. "Asuryani", "World Eaters") -- the keyword
    every catalogue-level army rule is gated on ("If your Army Faction is X"). Not the same
    string as Roster.faction (the catalogue name, e.g. "Aeldari - Craftworlds") -- read
    instead off the imported units' own "Faction: X" keyword (already indexed per-unit).
    Majority vote across the roster's units, same pattern import_roster() already uses to
    derive Roster.faction itself."""
    labels = [kw.split(":", 1)[1].strip() for d in definitions for kw in d.keywords if kw.startswith("Faction:")]
    if not labels:
        return None
    return Counter(labels).most_common(1)[0][0]


def bootstrap_army_rules(roster: Roster, definitions: list[UnitDefinition], session: Session) -> None:
    faction = derive_army_faction(definitions)
    handler = _HANDLERS.get(faction) if faction else None
    if handler is not None:
        handler(roster, session)
