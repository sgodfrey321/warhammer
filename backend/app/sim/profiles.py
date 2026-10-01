"""Typed attacker/defender profiles, parsed from the raw string-valued dicts
the rest of the app already stores (`UnitDefinition.weapons[i].characteristics`
and `UnitDefinition.stats` -- see backend/app/models.py). Parsing here is
deliberately forgiving: fields we don't understand fall back to a sane default
rather than raising, since indexed data is occasionally incomplete ("N/A", "-",
or a missing key).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .dice import DiceNotation, parse_dice
from .keywords import WeaponKeywords, parse_keywords


def _clean(value: str | None) -> str:
    return (value or "").strip()


_SKILL_RE = re.compile(r"(\d)\s*\+")


def _parse_skill(value: str | None) -> int | None:
    """"3+" -> 3, also tolerating annotated values ("4+*", "5+ (Ranged)", "4+* / 5+" -> first).
    Missing/"-"/"N/A" (e.g. a Torrent weapon with no BS) -> None."""

    text = _clean(value)
    if text in ("", "-", "N/A"):
        return None
    m = _SKILL_RE.search(text)
    if m:
        return int(m.group(1))
    try:
        return int(text)
    except ValueError:
        return None


def _parse_int(value: str | None, default: int = 0) -> int:
    text = _clean(value)
    if text in ("", "-", "N/A"):
        return default
    try:
        return int(text)
    except ValueError:
        return default


def _parse_ap(value: str | None) -> int:
    """AP is stored as a string like "0", "-1", "-2" -- already negative, so a
    plain int() parse is correct. Missing/garbage -> 0 (no penetration)."""

    return _parse_int(value, default=0)


@dataclass(frozen=True)
class AttackerProfile:
    name: str
    is_melee: bool
    attacks: DiceNotation
    skill: int | None  # BS (ranged) or WS (melee), as the target number (e.g. 3 for "3+")
    strength: int
    ap: int  # negative or zero
    damage: DiceNotation
    keywords: WeaponKeywords

    @classmethod
    def from_characteristics(cls, weapon: dict) -> "AttackerProfile":
        chars = weapon.get("characteristics", {}) or {}
        is_melee = weapon.get("range_type") == "Melee Weapons"
        skill_raw = chars.get("WS") if is_melee else chars.get("BS")
        return cls(
            name=weapon.get("name", ""),
            is_melee=is_melee,
            attacks=parse_dice(chars.get("A")),
            skill=_parse_skill(skill_raw),
            strength=_parse_int(chars.get("S"), default=0),
            ap=_parse_ap(chars.get("AP")),
            damage=parse_dice(chars.get("D")),
            keywords=parse_keywords(chars.get("Keywords")),
        )


@dataclass(frozen=True)
class DefenderProfile:
    toughness: int
    save: int  # e.g. 3 for "3+"
    invuln: int | None  # e.g. 4 for "4+"; None if the unit has no invulnerable save
    wounds_per_model: int
    model_count: int
    defender_keywords: tuple[str, ...] = ()  # lowercased; what Anti-X is matched against

    @classmethod
    def from_stats(cls, stats: dict, model_count: int, keywords: list[str] | tuple[str, ...] | None = None) -> "DefenderProfile":
        save = _parse_skill(stats.get("Sv"))
        return cls(
            toughness=_parse_int(stats.get("T"), default=1),
            save=save if save is not None else 7,  # 7+ == "no armour save"
            invuln=_parse_skill(stats.get("InSv")),
            wounds_per_model=_parse_int(stats.get("W"), default=1),
            model_count=max(1, model_count),
            defender_keywords=tuple(" ".join(k.lower().split()) for k in (keywords or ()) if k.strip()),
        )
