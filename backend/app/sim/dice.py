"""Dice notation parsing and rolling.

Handles the small vocabulary 40k characteristics use: a flat integer ("3"),
"D6"/"D3" (also written "d6"/"d3"), a multiplier ("2D6"), and a flat add-on
("D3+1", "D6+2"). An injectable `random.Random` is threaded through every roll
so callers (and tests) can seed the RNG for reproducibility.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from random import Random

_NOTATION_RE = re.compile(
    r"^\s*(?:(?P<count>\d+)?D(?P<die>\d+))(?:\s*\+\s*(?P<bonus>\d+))?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DiceNotation:
    """A parsed notation: `count`d`die` + `bonus`. A flat number is `count=0,
    die=0` (bonus holds the flat value) so `roll()`/`average()` stay uniform."""

    count: int
    die: int
    bonus: int

    def roll(self, rng: Random) -> int:
        if self.die == 0:
            return self.bonus
        return sum(rng.randint(1, self.die) for _ in range(self.count)) + self.bonus

    def average(self) -> float:
        if self.die == 0:
            return float(self.bonus)
        return self.count * (self.die + 1) / 2 + self.bonus


def parse_dice(notation: str | int | None) -> DiceNotation:
    """Parse a characteristic string like "3", "D6", "2D6", "D3+1" into a
    DiceNotation. Accepts an int directly (already-resolved values) too."""

    if notation is None:
        return DiceNotation(count=0, die=0, bonus=0)
    if isinstance(notation, int):
        return DiceNotation(count=0, die=0, bonus=notation)

    text = notation.strip()
    if text in ("", "-", "N/A"):
        return DiceNotation(count=0, die=0, bonus=0)

    if text.lstrip("-").isdigit():
        return DiceNotation(count=0, die=0, bonus=int(text))

    match = _NOTATION_RE.match(text)
    if not match:
        raise ValueError(f"Unrecognised dice notation: {notation!r}")

    count = int(match.group("count") or 1)
    die = int(match.group("die"))
    bonus = int(match.group("bonus") or 0)
    return DiceNotation(count=count, die=die, bonus=bonus)


def roll_dice(notation: str | int | None, rng: Random) -> int:
    """Convenience one-shot: parse + roll."""

    return parse_dice(notation).roll(rng)
