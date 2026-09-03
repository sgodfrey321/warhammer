"""Best-effort extraction of attack-sequence modifiers from a unit's free-text
abilities, so the simulator can surface them as conditional, player-toggled
buffs (e.g. Wraithguard's Psychic Guidance -> "+1 to Hit").

This is a heuristic assist over GW's fairly formulaic wording -- it is NOT
authoritative. GW datasheets phrase the common effects almost verbatim across
hundreds of units ("add 1 to the Hit roll", "Feel No Pain 5+"), which is what
makes this tractable; but oddly-worded or highly conditional abilities will be
missed. The caller therefore always shows the raw ability text too and keeps the
manual option controls, so a missed/misread ability is never silently applied.

Each detected effect is classified by which side it helps:
  - "attacker": modifies attacks THIS unit makes (e.g. "each time a model in
    this unit makes an attack, add 1 to the Hit roll").
  - "defender": modifies attacks that TARGET this unit (e.g. Feel No Pain, or
    "subtract 1 from Hit rolls that target this unit").
The condition clause (usually a leading "While ...,") is kept verbatim as the
toggle's label so the player -- who alone knows the board state -- decides
whether it is live. `option_patch` is a partial SimulateOptions the caller
merges into its options when the toggle is on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Phrases that mean the effect applies to attacks made AGAINST this unit, i.e. it
# is a defensive (defender-side) modifier rather than one this unit's own attacks get.
_DEFENDER_HINTS = (
    "targets this unit",
    "target this unit",
    "against this unit",
    "attacking this unit",
    "that target this unit",
)


@dataclass
class DetectedEffect:
    ability_name: str
    summary: str  # short label, e.g. "+1 to Hit"
    condition: str  # verbatim condition clause ("While ..."), or "" if unconditional
    side: str  # "attacker" | "defender"
    option_patch: dict = field(default_factory=dict)  # partial SimulateOptions


def _condition_of(text: str) -> str:
    """Pulls a leading 'While ...,' condition clause out of the ability text, so
    the toggle can be labelled with the circumstance the player must confirm."""

    m = re.search(r"\bwhile\b(.+?),", text, flags=re.IGNORECASE)
    if m:
        return ("While" + m.group(1)).strip()
    return ""


def _side_for_roll(lowered: str) -> str:
    return "defender" if any(h in lowered for h in _DEFENDER_HINTS) else "attacker"


def _reroll_kind(lowered: str, roll_word: str) -> str | None:
    """Classifies a re-roll: 'ones' (only results of 1), 'all' (any/all failed),
    or None for a LIMITED single re-roll ("re-roll one Hit roll" / "a single")
    -- the sim has no per-activation single-re-roll option and auto-applying
    'all' would grossly overstate it, so we decline to model it (it still shows
    to the player as an un-modelled ability)."""

    if re.search(rf"re-?roll (a single|one) [^.]*{roll_word} roll", lowered):
        return None
    # e.g. "re-roll a hit roll of 1" / "re-roll hit rolls of 1"
    if re.search(rf"{roll_word} rolls? of (a )?1\b", lowered) or f"{roll_word} roll of 1" in lowered:
        return "ones"
    return "all"


def extract_effects(abilities: list[dict]) -> list[DetectedEffect]:
    """Scans each ability's text for the recognised vocabulary and returns one
    DetectedEffect per match. An ability can yield several effects."""

    effects: list[DetectedEffect] = []

    for ability in abilities:
        name = (ability.get("name") or "").strip()
        # Source data sprinkles non-breaking spaces (\xa0) between words; normalise them
        # so the regexes below see ordinary spaces.
        text = (ability.get("text") or "").replace("\xa0", " ").strip()
        if not text:
            continue
        low = text.lower()
        condition = _condition_of(text)

        # --- Hit roll modifier ---
        if re.search(r"add 1 to (the |your |their )?hit roll", low):
            side = _side_for_roll(low)
            # "add 1 to the hit roll" targeting this unit means the ENEMY hits it
            # better -- that's bad for the defender, so flip the sign for that side.
            value = 1 if side == "attacker" else -1
            effects.append(
                DetectedEffect(name, f"{'+' if value > 0 else ''}{value} to Hit", condition, side, {"hit_modifier": value})
            )
        if re.search(r"subtract 1 from (the |your |their )?hit roll", low):
            # "subtract 1 from hit rolls that target this unit" is a DEFENDER buff
            # (attacks against it are worse); otherwise it's a self-penalty (rare).
            side = _side_for_roll(low)
            effects.append(
                DetectedEffect(name, "-1 to Hit (against this unit)" if side == "defender" else "-1 to Hit", condition, side, {"hit_modifier": -1})
            )

        # --- Wound roll modifier ---
        if re.search(r"add 1 to (the |your |their )?wound roll", low):
            side = _side_for_roll(low)
            value = 1 if side == "attacker" else -1
            effects.append(
                DetectedEffect(name, f"{'+' if value > 0 else ''}{value} to Wound", condition, side, {"wound_modifier": value})
            )
        if re.search(r"subtract 1 from (the |your |their )?wound roll", low):
            side = _side_for_roll(low)
            effects.append(
                DetectedEffect(name, "-1 to Wound (against this unit)" if side == "defender" else "-1 to Wound", condition, side, {"wound_modifier": -1})
            )

        # --- Re-rolls (skip limited single-die re-rolls we can't model, see _reroll_kind) ---
        if re.search(r"re-?roll [^.]*hit roll", low):
            kind = _reroll_kind(low, "hit")
            if kind is not None:
                effects.append(
                    DetectedEffect(name, f"Re-roll {'1s to' if kind == 'ones' else 'all'} Hit", condition, "attacker", {"reroll_hits": kind})
                )
        if re.search(r"re-?roll [^.]*wound roll", low):
            kind = _reroll_kind(low, "wound")
            if kind is not None:
                effects.append(
                    DetectedEffect(name, f"Re-roll {'1s to' if kind == 'ones' else 'all'} Wound", condition, "attacker", {"reroll_wounds": kind})
                )

        # --- Feel No Pain (always a defender-side ability) ---
        m = re.search(r"feel no pain (\d)\+", low)
        if m:
            fnp = int(m.group(1))
            effects.append(DetectedEffect(name, f"Feel No Pain {fnp}+", condition, "defender", {"fnp": fnp}))

    return effects
