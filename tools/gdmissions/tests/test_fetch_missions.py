import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fetch_missions import Mission, MissionSection, MissionTier, extract_links, parse_mission_page

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_mission_page_extracts_name_deck_vs_and_sections():
    html = (FIXTURES / "battlefield-dominance.html").read_text(encoding="utf-8")

    mission = parse_mission_page(html)

    assert mission == Mission(
        name="Battlefield Dominance",
        deck="take-and-hold",
        vs="take-and-hold",
        sections=[
            MissionSection(
                when="FIRST & SECOND BATTLE ROUND",
                trigger="End of your turn",
                tiers=[MissionTier(text="You control more **objectives** than your opponent.", vp=2)],
            ),
            MissionSection(
                when="SECOND BATTLE ROUND ONWARDS",
                trigger="End of your Command phase (or the end of your turn in the fifth battle round)",
                tiers=[
                    MissionTier(text="For each **objective** you control.", vp=3, per_unit=True),
                    MissionTier(
                        text="For each of those objectives (excluding home) if you control your home objective.",
                        vp=2,
                        per_unit=True,
                        cumulative=True,
                    ),
                ],
            ),
        ],
    )


def test_parse_mission_page_handles_end_of_battle_sections_with_no_trigger():
    """Real data (Inescapable Dominion) has a section with no "trigger" at all -- just a
    "headerKind" -- which used to crash the parser with a KeyError."""
    html = (FIXTURES / "inescapable-dominion.html").read_text(encoding="utf-8")

    mission = parse_mission_page(html)

    assert mission is not None
    eob_section = mission.sections[1]
    assert eob_section.when == "END OF BATTLE"
    assert eob_section.trigger is None
    assert eob_section.header_kind == "eob"
    assert eob_section.tiers[0].kind == "eob"


def test_parse_mission_page_returns_none_for_a_non_mission_page():
    html = (FIXTURES / "deck-listing.html").read_text(encoding="utf-8")
    assert parse_mission_page(html) is None


def test_extract_links_finds_and_dedupes_card_links_in_document_order():
    html = (FIXTURES / "deck-listing.html").read_text(encoding="utf-8")

    result = extract_links(html, "/11th/primary-missions/take-and-hold/")

    assert result == [
        "/11th/primary-missions/take-and-hold/battlefield-dominance",
        "/11th/primary-missions/take-and-hold/determined-acquisition",
        "/11th/primary-missions/take-and-hold/immovable-object",
        "/11th/primary-missions/take-and-hold/inescapable-dominion",
        "/11th/primary-missions/take-and-hold/purge-and-secure",
    ]


def test_extract_links_does_not_match_the_bare_index_link():
    html = (FIXTURES / "deck-listing.html").read_text(encoding="utf-8")
    result = extract_links(html, "/11th/primary-missions/")
    assert "/11th/primary-missions" not in result
