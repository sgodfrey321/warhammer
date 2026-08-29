from __future__ import annotations

import re

from .models import SynergyCandidate, hash_text

# Battle Focus-style abilities spell out their own trigger/effect split verbatim.
_TEMPLATE_RE = re.compile(r"■\s*Trigger:\s*(.+?)\s*■\s*Effect:\s*(.+)", re.DOTALL)

# Keywords are marked ^^Like This^^ in the source text (see catalogue._abilities), independent
# of casing -- the reliable signal is the marker, not upper-case. An unmarked, all-caps-only
# fallback covers SPEC.md-style phrasing ("friendly WORLD EATERS CHARACTER unit") that isn't
# caret-marked in every source. Ordinary mixed-case prose ("friendly Aeldari model" with no
# marker) is deliberately NOT matched -- too ambiguous with plain English to regex reliably.
_KEYWORD_MARKED_RE = re.compile(r"friendly\s+\^\^([^^]+)\^\^\s+(?:unit|units|model|models)\b", re.IGNORECASE)
_KEYWORD_UNMARKED_RE = re.compile(r"friendly\s+([A-Z][A-Z\s]{2,}?)\s+(?:unit|units|model|models)\b")
_EXCLUDING_MARKED_RE = re.compile(r"excluding\s+\^\^([^^]+)\^\^", re.IGNORECASE)
_EXCLUDING_UNMARKED_RE = re.compile(r"excluding\s+([A-Z][A-Z\s]{2,}?)\s+(?:unit|units|model|models)\b")

_PHASE_RE = re.compile(r"\b(?:your opponent'?s|your|opponent'?s)\s+(Command|Movement|Shooting|Charge|Fight)\s+phase\b", re.IGNORECASE)

_DURATION_PATTERNS = [
    (re.compile(r"until the start of your next Command phase", re.IGNORECASE), "until_next_command_phase"),
    (re.compile(r"until the end of the battle round", re.IGNORECASE), "end_of_battle_round"),
    (re.compile(r"until the end of the turn", re.IGNORECASE), "end_of_turn"),
    (re.compile(r"until the end of the phase", re.IGNORECASE), "end_of_phase"),
]


def _strip_markup(text: str) -> str:
    text = text.replace("^^", "").replace("**", "")
    return " ".join(text.split())


def _to_keyword_token(raw: str) -> str:
    return raw.strip().upper().replace(" ", "_")


def _extract_keyword(text: str) -> tuple[str | None, list[str]]:
    """Returns (keyword, exclusions). Two or more DISTINCT keyword mentions in one ability
    (e.g. "friendly ^^Wraith Construct^^ or ^^Asuryani Vehicle^^ units") is genuinely
    ambiguous for a single affects_keyword field -- decline rather than pick one at random."""
    marked = [m.group(1).strip() for m in _KEYWORD_MARKED_RE.finditer(text)]
    candidates = marked or [m.group(1).strip() for m in _KEYWORD_UNMARKED_RE.finditer(text)]
    distinct = {c.upper() for c in candidates}
    if len(distinct) != 1:
        return None, []

    exclusions: list[str] = []
    for rx in (_EXCLUDING_MARKED_RE, _EXCLUDING_UNMARKED_RE):
        exclusions.extend(_to_keyword_token(m.group(1)) for m in rx.finditer(text))

    return _to_keyword_token(candidates[0]), exclusions


def _extract_trigger_phase(text: str) -> str | None:
    phases = {m.group(1).lower() for m in _PHASE_RE.finditer(text)}
    return next(iter(phases)) if len(phases) == 1 else None


def _extract_duration(text: str) -> str | None:
    for pattern, value in _DURATION_PATTERNS:
        if pattern.search(text):
            return value
    return None


def extract(source_entry_id: str, unit_name: str, ability_name: str, text: str) -> SynergyCandidate | None:
    """Deterministic extraction. Returns None (defer to Tier 2) unless at least one field was
    confidently, unambiguously extracted -- never guesses to fill a field."""
    if not text or not text.strip():
        return None

    template_match = _TEMPLATE_RE.search(text)
    trigger_detail = _strip_markup(template_match.group(1))[:300] if template_match else None

    keyword, exclusions = _extract_keyword(text)
    phase = _extract_trigger_phase(text)
    duration = _extract_duration(text)

    if keyword is None and phase is None and duration is None and trigger_detail is None:
        return None

    return SynergyCandidate(
        source_entry_id=source_entry_id,
        unit_name=unit_name,
        ability_name=ability_name,
        text_hash=hash_text(text),
        tier="tier1",
        confidence="high",
        affects_keyword=keyword,
        affects_exclusions=exclusions,
        trigger_phase=phase,
        trigger_detail=trigger_detail,
        duration_type=duration,
    )
