"""Maps a catalogue faction file (stem, no extension) to the MFM yaml slug that carries its
points. Not 1:1 -- several catalogue factions share one MFM file (e.g. most Space Marine
successor chapters use the generic "space-marines" points, since they don't have enough
unique units to warrant their own points file).

Honesty note: only "Aeldari - Craftworlds" (-> aeldari) and "Chaos - World Eaters"
(-> world-eaters) were cross-checked point-by-point against real data during planning (see
app-plan.md's Wraithlord/Wave Serpent/Khorne Daemonkin examples). The rest of KNOWN is
inferred from name correspondence against the real repo listings, not independently verified
unit-by-unit. This is a soft safety net either way: if a faction's slug is wrong, most/all of
its units will simply fail to match in mfm.index_units() and come out `mfm_matched=False`
rather than silently getting some other faction's points -- so a bad mapping is loud, not
silent. Re-check a faction here before trusting its output if its unmatched-unit count looks
high.
"""
from __future__ import annotations

from .util import slugify

KNOWN: dict[str, str] = {
    # Verified point-by-point during planning
    "Aeldari - Craftworlds": "aeldari",
    "Chaos - World Eaters": "world-eaters",
    # Inferred from name correspondence against the repo listings -- not unit-checked
    "Aeldari - Drukhari": "drukhari",
    "Chaos - Chaos Daemons": "chaos-daemons",
    "Chaos - Chaos Knights": "chaos-knights",
    "Chaos - Chaos Space Marines": "chaos-space-marines",
    "Chaos - Death Guard": "death-guard",
    "Chaos - Emperor's Children": "emperors-children",
    "Chaos - Thousand Sons": "thousand-sons",
    "Chaos - Titanicus Traitoris": "titan-legions",
    "Imperium - Adepta Sororitas": "adepta-sororitas",
    "Imperium - Adeptus Custodes": "adeptus-custodes",
    "Imperium - Adeptus Mechanicus": "adeptus-mechanicus",
    "Imperium - Agents of the Imperium": "imperial-agents",
    "Imperium - Astra Militarum": "astra-militarum",
    "Imperium - Black Templars": "black-templars",
    "Imperium - Blood Angels": "blood-angels",
    "Imperium - Dark Angels": "dark-angels",
    "Imperium - Deathwatch": "deathwatch",
    "Imperium - Grey Knights": "grey-knights",
    "Imperium - Imperial Knights": "imperial-knights",
    "Imperium - Space Marines": "space-marines",
    "Imperium - Space Wolves": "space-wolves",
    "Genestealer Cults": "genestealer-cults",
    "Leagues of Votann": "leagues-of-votann",
    "Necrons": "necrons",
    "Orks": "orks",
    "T'au Empire": "tau-empire",
    "Tyranids": "tyranids",
    # Successor chapters -- no chapter-specific MFM file, they use generic Space Marines points
    "Imperium - Imperial Fists": "space-marines",
    "Imperium - Iron Hands": "space-marines",
    "Imperium - Raven Guard": "space-marines",
    "Imperium - Salamanders": "space-marines",
    "Imperium - Ultramarines": "space-marines",
    "Imperium - White Scars": "space-marines",
}

# Library/index-only catalogue files -- not real armies, never expected to map to an MFM slug.
# "Aeldari - Ynnari" is deliberately absent from KNOWN (not NOT_APPLICABLE): it's a real,
# playable faction but a "soup" of Craftworlds/Drukhari units with no MFM file of its own, so
# it should resolve to unmapped/flagged rather than get a guessed-wrong slug.
NOT_APPLICABLE = {
    "Aeldari - Aeldari Library",
    "Chaos - Chaos Daemons Library",
    "Chaos - Chaos Knights Library",
    "Imperium - Astra Militarum - Library",
    "Imperium - Imperial Knights - Library",
    "Library - Astartes Heresy Legends",
    "Library - Titans",
    "Library - Tyranids",
    "Unaligned Forces",
    "Warhammer 40,000",
}


def resolve(faction_file_stem: str, available_slugs: set[str]) -> tuple[str | None, bool]:
    """Returns (mfm_slug_or_None, was_guessed).

    None means unmapped -- the caller should flag it, not silently skip. Never returns a
    guessed slug that isn't actually present in `available_slugs`.
    """
    if faction_file_stem in NOT_APPLICABLE:
        return None, False
    if faction_file_stem in KNOWN:
        slug = KNOWN[faction_file_stem]
        return (slug, False) if slug in available_slugs else (None, False)
    guess = slugify(faction_file_stem.split(" - ", 1)[-1])
    if guess in available_slugs:
        return guess, True
    return None, False
