from __future__ import annotations

import re


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def normalize_name(name: str) -> str:
    """Join key for matching a catalogue unit name against an MFM unit name. MFM title-cases
    every word ("Daemon Prince Of Khorne With Wings"); catalogues use natural sentence case
    ("Daemon Prince of Khorne with wings") -- confirmed on World Eaters, where this silently
    broke matching for Khârn the Betrayer and both Daemon Prince variants (an accent in
    "Khârn" looked like the likely culprit at first; it wasn't -- both sides had it correctly,
    only the "the"/"of"/"with" casing differed). Whitespace is also collapsed defensively."""
    return " ".join(name.split()).casefold()
