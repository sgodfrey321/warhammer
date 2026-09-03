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
class ModelProfile:
    """One distinct model-type within a unit (e.g. Guardian Defenders has two: "Guardian
    Defender" and "Heavy Weapon Platform", each with its own stat line and weapon options).
    A single-model unit (Character, vehicle) still gets exactly one of these, scoped to its
    whole entry -- same weapons the flat `UnitDefinition.weapons` already has."""

    name: str
    stats: dict[str, str]
    ranged_weapons: list[Weapon] = field(default_factory=list)
    melee_weapons: list[Weapon] = field(default_factory=list)


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
    # GW's "Battlefield Role" badge (Character, Battleline, Infantry, Vehicle, Epic Hero, ...) --
    # the one categoryLink BSData marks primary. None for an entry with no primary category.
    role: str | None = None
    is_legends: bool = False
    stats: dict[str, str] = field(default_factory=dict)  # M/T/Sv/W/LD/OC from the "Unit" profile
    abilities: list[Ability] = field(default_factory=list)  # from "Abilities"-typed profiles
    rules: list[str] = field(default_factory=list)  # names linked via infoLinks[type=="rule"]
    weapons: list[Weapon] = field(default_factory=list)  # from "Ranged/Melee Weapons"-typed profiles
    model_profiles: list[ModelProfile] = field(default_factory=list)  # per-model-type stats/weapons
    points: list[PointsTier] = field(default_factory=list)  # empty -> mfm_matched is False
    mfm_matched: bool = False
    source_catalogue_id: str = ""
    source_entry_id: str | None = None
