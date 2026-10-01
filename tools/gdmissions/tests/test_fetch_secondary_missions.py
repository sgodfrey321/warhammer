import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fetch_secondary_missions import (
    Action,
    ActionRow,
    SecondaryMission,
    SecondaryRow,
    SecondarySection,
    parse_secondary_mission_page,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_secondary_mission_page_handles_a_battlefield_action_card():
    """Real data (Cleanse): has an `action` block, no `whenDrawn`."""
    html = (FIXTURES / "cleanse-defender.html").read_text(encoding="utf-8")

    mission = parse_secondary_mission_page(html, "cleanse-defender")

    assert mission == SecondaryMission(
        name="Cleanse",
        slug="cleanse-defender",
        when_drawn=None,
        action=Action(
            title="CLEANSE",
            rows=[
                ActionRow(k="STARTS", v="Your Shooting phase."),
                ActionRow(k="UNITS", v="One friendly unit within range of one objective."),
                ActionRow(k="USE LIMIT", v="Unlimited."),
                ActionRow(k="COMPLETES", v="End of your turn, if that unit is controlling that objective."),
                ActionRow(k="EFFECT", v="That objective is cleansed by your army."),
            ],
        ),
        sections=[
            SecondarySection(
                when="ANY BATTLE ROUND",
                trigger="End of your turn",
                rows=[
                    SecondaryRow(text="One objective was cleansed by your army this turn.", vp="2"),
                    SecondaryRow(
                        text="Two or more objectives were cleansed by your army this turn.", vp="5", or_=True
                    ),
                ],
            )
        ],
    )


def test_parse_secondary_mission_page_handles_a_when_drawn_card_with_no_action():
    """Real data (Beacon): has `whenDrawn`, no `action` block at all."""
    html = (FIXTURES / "beacon-defender.html").read_text(encoding="utf-8")

    mission = parse_secondary_mission_page(html, "beacon-defender")

    assert mission is not None
    assert mission.action is None
    assert mission.when_drawn is not None
    assert "WHEN DRAWN" in mission.when_drawn
    assert mission.sections[0].rows[1].or_ is True


def test_parse_secondary_mission_page_returns_none_for_a_non_mission_page():
    html = (FIXTURES / "deck-listing.html").read_text(encoding="utf-8")
    assert parse_secondary_mission_page(html, "deck-listing") is None
