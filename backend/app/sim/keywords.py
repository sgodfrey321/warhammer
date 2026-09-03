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


@dataclass(frozen=True)
class WeaponKeywords:
    rapid_fire: int | None = None
    blast: bool = False
    torrent: bool = False
    sustained_hits: int | None = None
    lethal_hits: bool = False
    devastating_wounds: bool = False
    twin_linked: bool = False
    lance: bool = False
    melta: int | None = None
    ignores_cover: bool = False
    # Best-effort threshold extracted from an "Anti-X Y+" keyword on the weapon
    # itself, e.g. "Anti-Vehicle 4+" -> 4. We don't attempt to match the X
    # against the defender's keyword list (see profiles.py / sequence.py) --
    # whether Anti applies at all is left to the caller-supplied `anti_active`
    # option. This field is only a convenience default for that threshold.
    anti_threshold: int | None = None


def _normalise(token: str) -> str:
    return re.sub(r"[\s-]+", " ", token.strip().lower())


_RAPID_FIRE_RE = re.compile(r"^rapid fire (\d+)$")
_SUSTAINED_HITS_RE = re.compile(r"^sustained hits (\d+)")
_MELTA_RE = re.compile(r"^melta (\d+)$")
_ANTI_RE = re.compile(r"^anti[- ].*?(\d+)\+")


def parse_keywords(raw: str | None) -> WeaponKeywords:
    """Parse a "Keywords" characteristic string. `None`/empty -> all-default
    (no keywords) instance."""

    if not raw:
        return WeaponKeywords()

    kwargs: dict[str, object] = {}
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
        elif norm == "ignores cover":
            kwargs["ignores_cover"] = True
        elif (m := _RAPID_FIRE_RE.match(norm)):
            kwargs["rapid_fire"] = int(m.group(1))
        elif (m := _SUSTAINED_HITS_RE.match(norm)):
            kwargs["sustained_hits"] = int(m.group(1))
        elif (m := _MELTA_RE.match(norm)):
            kwargs["melta"] = int(m.group(1))
        elif (m := _ANTI_RE.match(norm)):
            kwargs["anti_threshold"] = int(m.group(1))
        # else: unrecognised keyword, ignored by design (recognized no-op).

    return WeaponKeywords(**kwargs)
