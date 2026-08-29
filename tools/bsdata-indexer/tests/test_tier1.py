from bsdata_indexer.enrichment import tier1

# Real ability text pulled from a live Aeldari - Craftworlds build during planning.

BATTLE_FOCUS_TEXT = (
    "■ Trigger: When an eligible unit from your army is selected to make a Normal, Advance "
    "or Fall Back move. You can trigger this Agile Manoeuvre more than once per phase "
    "(provided a different unit performs it each time).\n"
    "■ Effect: Until the end of the phase, add 2\" to the Move characteristic of models in "
    "that unit."
)

AURA_TEXT = (
    'While a friendly ^^Aeldari^^ unit is within 6" of this model, add 1 to Advance and '
    "Charge rolls made for that unit."
)

TACTICAL_ACUMEN_TEXT = (
    "While this model is leading a unit, in your Shooting phase, after that unit has shot, "
    'it can make a Normal move of up to 6". If it does, until the end of the turn, that unit '
    "is not eligible to declare a charge."
)

AMBIGUOUS_KEYWORD_TEXT = (
    'While this model is within 3" of one or more friendly ^^Wraith Construct^^ or '
    "^^Asuryani Vehicle^^ units, unless it is leading a unit, this model has the Lone "
    "Operative ability."
)

NO_SIGNAL_TEXT = (
    "You can target this unit with the Heroic Intervention stratagem, regardless of any "
    "other uses of that stratagem this phase. If you do: that use is -1 CP."
)

EXCLUSION_TEXT = (
    "Each time a friendly WORLD EATERS CHARACTER unit, excluding EPIC HERO units, is "
    "destroyed, that unit's controlling player gains 1 CP."
)


def test_battle_focus_template_extracts_trigger_detail_and_duration():
    c = tier1.extract("id-1", "Battle Focus", "Swift as the Wind", BATTLE_FOCUS_TEXT)
    assert c is not None
    assert c.tier == "tier1"
    assert c.confidence == "high"
    assert c.duration_type == "end_of_phase"
    assert "selected to make a Normal" in c.trigger_detail
    assert c.affects_keyword is None  # no keyword-restricted target here


def test_marked_keyword_aura_extracts_keyword_only():
    c = tier1.extract("id-2", "Avatar of Khaine", "The Bloody Handed (Aura)", AURA_TEXT)
    assert c is not None
    assert c.affects_keyword == "AELDARI"
    assert c.trigger_phase is None
    assert c.duration_type is None


def test_extracts_trigger_phase_and_duration_without_keyword():
    c = tier1.extract("id-3", "Asurmen", "Tactical Acumen", TACTICAL_ACUMEN_TEXT)
    assert c is not None
    assert c.affects_keyword is None
    assert c.trigger_phase == "shooting"
    assert c.duration_type == "end_of_turn"


def test_ambiguous_multi_keyword_declines():
    c = tier1.extract("id-4", "Bonesinger", "Bonesinger", AMBIGUOUS_KEYWORD_TEXT)
    assert c is None  # two distinct keywords ORed together -- defer to Tier 2, don't guess


def test_no_extractable_signal_declines():
    c = tier1.extract("id-5", "Corsair Cloud Dancer Band", "Reckless Abandon", NO_SIGNAL_TEXT)
    assert c is None


def test_unmarked_allcaps_keyword_with_exclusion():
    c = tier1.extract("id-6", "Some Character", "Vengeance", EXCLUSION_TEXT)
    assert c is not None
    assert c.affects_keyword == "WORLD_EATERS_CHARACTER"
    assert c.affects_exclusions == ["EPIC_HERO"]


def test_empty_text_declines():
    assert tier1.extract("id-7", "Unit", "Ability", "") is None
    assert tier1.extract("id-7", "Unit", "Ability", "   ") is None
