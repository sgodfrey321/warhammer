import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fetch_layouts import Layout, LayoutMatchup, parse_layout_page

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_layout_page_extracts_both_image_variants_for_each_layout():
    html = (FIXTURES / "take-and-hold-purge-the-foe.html").read_text(encoding="utf-8")

    matchup = parse_layout_page(html, "take-and-hold", "purge-the-foe")

    assert matchup == LayoutMatchup(
        deck="take-and-hold",
        vs="purge-the-foe",
        name="Take and Hold vs Purge the Foe",
        layouts=[
            Layout(
                number=1,
                name="Layout 1",
                image="https://gdmissions.app/assets/11th/layouts/no-measurements/take-and-hold-vs-purge-the-foe-1-portrait.png",
                measurements_image="https://gdmissions.app/assets/11th/layouts/with-measurements/take-and-hold-vs-purge-the-foe-1-portrait.png",
            ),
            Layout(
                number=2,
                name="Layout 2",
                image="https://gdmissions.app/assets/11th/layouts/no-measurements/take-and-hold-vs-purge-the-foe-2.png",
                measurements_image="https://gdmissions.app/assets/11th/layouts/with-measurements/take-and-hold-vs-purge-the-foe-2.png",
            ),
        ],
    )


def test_parse_layout_page_returns_none_for_a_non_layout_page():
    html = (FIXTURES / "deck-listing.html").read_text(encoding="utf-8")
    assert parse_layout_page(html, "take-and-hold", "deck-listing") is None
