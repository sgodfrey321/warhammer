from pathlib import Path

from bsdata_indexer import mfm
from bsdata_indexer.util import normalize_name

FIXTURES = Path(__file__).parent / "fixtures"


def load_doc() -> dict:
    return mfm.load_yaml((FIXTURES / "aeldari_mfm.yaml").read_bytes())


def test_index_units_simple_flat_price():
    index = mfm.index_units(load_doc())
    wraithlord = index[normalize_name("Wraithlord")]
    assert wraithlord.is_legends is False
    assert len(wraithlord.points) == 1
    assert wraithlord.points[0].points == 125
    assert wraithlord.points[0].models == 1


def test_index_units_tiered_price_by_copy_count():
    index = mfm.index_units(load_doc())
    wave_serpent = index[normalize_name("Wave Serpent")]
    tiers = {t.range: t.points for t in wave_serpent.points}
    assert tiers == {"[1,3]": 115, "[4,)": 125}


def test_index_units_legends_flag():
    index = mfm.index_units(load_doc())
    assert index[normalize_name("Autarch Skyrunner")].is_legends is True
    assert index[normalize_name("Wraithlord")].is_legends is False


def test_index_units_matches_across_connector_word_casing():
    """Regression test: MFM title-cases every word ("Daemon Prince Of Khorne With Wings"),
    catalogues use natural sentence case ("Daemon Prince of Khorne with wings") -- found on
    World Eaters, where it silently broke matching for real, common, currently-priced units
    (Khârn the Betrayer, both Daemon Prince variants). normalize_name's casefold must bridge
    this, not just exact string equality."""
    index = mfm.index_units(load_doc())
    catalogue_style_name = "Daemon Prince of Khorne with wings"
    unit = index[normalize_name(catalogue_style_name)]
    assert unit.points[0].points == 180
