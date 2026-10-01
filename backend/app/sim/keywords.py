"""Parses a weapon's comma-separated `Keywords` characteristic string into a
typed, easy-to-query structure.

Source data (see `tools/bsdata-indexer`) writes keywords in GW's rules-text
casing with hyphens, e.g. "Twin-linked, Sustained Hits 1, Anti-Vehicle 4+".
We're tolerant of case and of hyphen-vs-space variants ("Twin-linked" /
"Twin linked" / "TWIN-LINKED") since the indexer/import scripts aren't a
contract this module controls. Anything we don't recognise is a silent no-op
-- v1 only needs the keywords enumerated in the task, not the full keyword
list from the rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .dice import DiceNotation, parse_dice


AntiEntry = tuple[tuple[str, ...], int]  # (target keywords any-of, threshold); "non-X" entries mean "has none of X"


@dataclass(frozen=True)
class WeaponKeywords:
    rapid_fire: DiceNotation | None = None
    blast: bool = False
    torrent: bool = False
    sustained_hits: DiceNotation | None = None
    lethal_hits: bool = False
    devastating_wounds: bool = False
    twin_linked: bool = False
    lance: bool = False
    melta: DiceNotation | None = None
    ignores_cover: bool = False
    heavy: bool = False
    indirect_fire: bool = False
    # Every "Anti-X Y+" on the weapon, matched against the defender's keywords in sequence.py.
    # A negated target ("Anti-non-Monster/Vehicle") is stored as "non-monster", "non-vehicle".
    anti: tuple[AntiEntry, ...] = ()

    def __post_init__(self) -> None:
        # Tests/callers may pass plain ints for the dice-valued keywords.
        for name in ("rapid_fire", "sustained_hits", "melta"):
            value = getattr(self, name)
            if isinstance(value, int):
                object.__setattr__(self, name, parse_dice(value))

    @property
    def anti_threshold(self) -> int | None:
        """Lowest threshold across all Anti entries, ignoring what they target."""

        return min((t for _, t in self.anti), default=None)


def _normalise(token: str) -> str:
    # U+2010/2011/2013 are hyphen lookalikes that show up in copy-pasted rules text.
    token = token.translate({0x2010: "-", 0x2011: "-", 0x2013: "-"})
    return re.sub(r"[\s-]+", " ", token.strip().lower())


_DICE = r"(\d*d\d+(?: ?\+ ?\d+)?|\d+)"
_RAPID_FIRE_RE = re.compile(rf"^rapid fire {_DICE}$")
_SUSTAINED_HITS_RE = re.compile(rf"^sustained hits {_DICE}")
_MELTA_RE = re.compile(rf"^melta {_DICE}$")
_ANTI_RE = re.compile(r"^anti (.+?) (\d)\+")


def _parse_anti(target: str, threshold: int) -> AntiEntry:
    negated = target.startswith("non ")
    if negated:
        target = target[4:]
    kws = tuple(k.strip() for k in target.split("/") if k.strip())
    return (tuple(f"non-{k}" for k in kws) if negated else kws), threshold


def parse_keywords(raw: str | None) -> WeaponKeywords:
    """Parse a "Keywords" characteristic string. `None`/empty -> all-default
    (no keywords) instance."""

    if not raw:
        return WeaponKeywords()

    kwargs: dict[str, object] = {}
    anti: list[AntiEntry] = []
    for token in raw.split(","):
        norm = _normalise(token)
        if not norm:
            continue

        if norm == "torrent":
            kwargs["torrent"] = True
        elif norm == "blast":
            kwargs["blast"] = True
        elif norm == "lethal hits":
            kwargs["lethal_hits"] = True
        elif norm == "devastating wounds":
            kwargs["devastating_wounds"] = True
        elif norm in ("twin linked", "twin-linked"):
            kwargs["twin_linked"] = True
        elif norm == "lance":
            kwargs["lance"] = True
        elif norm == "heavy":
            kwargs["heavy"] = True
        elif norm == "indirect fire":
            kwargs["indirect_fire"] = True
        elif norm == "ignores cover":
            kwargs["ignores_cover"] = True
        elif (m := _RAPID_FIRE_RE.match(norm)):
            kwargs["rapid_fire"] = parse_dice(m.group(1))
        elif (m := _SUSTAINED_HITS_RE.match(norm)):
            kwargs["sustained_hits"] = parse_dice(m.group(1))
        elif (m := _MELTA_RE.match(norm)):
            kwargs["melta"] = parse_dice(m.group(1))
        elif (m := _ANTI_RE.match(norm)):
            anti.append(_parse_anti(m.group(1), int(m.group(2))))
        # else: unrecognised keyword, ignored by design (recognized no-op).

    return WeaponKeywords(anti=tuple(anti), **kwargs)
