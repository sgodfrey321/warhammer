from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Ability:
    name: str
    text: str


@dataclass(frozen=True)
class Weapon:
    name: str
    range_type: str  # "Ranged Weapons" | "Melee Weapons"
    characteristics: dict[str, str]  # Range/A/BS-or-WS/S/AP/D/Keywords


@dataclass(frozen=True)
class PointsTier:
    """One row of MFM pricing. `range` is the raw MFM range string (e.g. "[1,3]" means
    "your 1st to 3rd copies of this unit"; "[1,)" means "every copy costs the same")."""

    range: str
    models: int
    points: int
    label: str | None = None


@dataclass
class UnitDefinition:
    id: str  # slug(faction) + "/" + slug(name) -- stable across runs
    faction: str  # catalogue file stem, e.g. "Aeldari - Craftworlds"
    name: str
    keywords: list[str] = field(default_factory=list)
    is_legends: bool = False
    stats: dict[str, str] = field(default_factory=dict)  # M/T/Sv/W/LD/OC from the "Unit" profile
    abilities: list[Ability] = field(default_factory=list)  # from "Abilities"-typed profiles
    weapons: list[Weapon] = field(default_factory=list)  # from "Ranged/Melee Weapons"-typed profiles
    points: list[PointsTier] = field(default_factory=list)  # empty -> mfm_matched is False
    mfm_matched: bool = False
    source_catalogue_id: str = ""
    source_entry_id: str | None = None
