from __future__ import annotations

import pytest

from app.sim.abilities import extract_effects
from app.sim.dice import DiceNotation
from app.sim.keywords import WeaponKeywords, parse_keywords
from app.sim.profiles import AttackerProfile, DefenderProfile, _parse_skill
from app.sim.sequence import AttackOptions, _resolve_hits, _resolve_wounds, resolve_sequence

from .test_sim import QueueRandom, _unit, _weapon


# 1. invuln parsing
@pytest.mark.parametrize(
    "raw,expected",
    [("4+*", 4), ("5+ (Ranged)", 5), ("4+* / 5+", 4), ("2+*", 2), ("4+\n", 4), ("3", 3), ("3+", 3),
     ("-", None), ("N/A", None), ("", None), (None, None)],
)
def test_parse_skill_variants(raw, expected):
    assert _parse_skill(raw) == expected


def test_defender_invuln_with_asterisk_kept():
    assert DefenderProfile.from_stats({"T": "4", "Sv": "3+", "InSv": "4+*", "W": "2"}, 1).invuln == 4


# 2. Anti-X matching
def test_parse_multiple_anti_entries():
    kw = parse_keywords("Anti-MONSTER 2+, Anti-VEHICLE 3+")
    assert kw.anti == ((("monster",), 2), (("vehicle",), 3))
    assert kw.anti_threshold == 2


def test_parse_anti_slash_multiword_and_nonbreaking_hyphen():
    assert parse_keywords("Anti-Monster/Vehicle 3+").anti == ((("monster", "vehicle"), 3),)
    assert parse_keywords("Anti-Epic Hero 2+").anti == ((("epic hero",), 2),)
    assert parse_keywords("ANTI-non‑MONSTER/VEHICLE 2+").anti == ((("non-monster", "non-vehicle"), 2),)


def _anti_wounds(kw_str: str, def_kws, roll: int, options=None):
    attacker = _weapon(strength=1, keywords=parse_keywords(kw_str))
    defender = DefenderProfile.from_stats({"T": "8", "Sv": "7+", "W": "5"}, 1, def_kws)
    return _resolve_wounds(attacker, defender, options or AttackOptions(), [False], QueueRandom([roll]))


def test_anti_auto_applies_when_defender_keyword_matches():
    assert len(_anti_wounds("Anti-Vehicle 4+", ["Vehicle"], 4)) == 1


def test_anti_ignored_when_keyword_missing():
    assert _anti_wounds("Anti-Vehicle 4+", ["Infantry"], 4) == []


def test_anti_uses_lowest_matching_threshold():
    assert len(_anti_wounds("Anti-Monster 5+, Anti-Vehicle 3+", ["Monster", "Vehicle"], 3)) == 1
    assert _anti_wounds("Anti-Monster 5+, Anti-Vehicle 3+", ["Monster"], 3) == []


def test_anti_non_target_matches_when_none_present():
    assert len(_anti_wounds("Anti-non-Monster/Vehicle 2+", ["Infantry"], 2)) == 1
    assert _anti_wounds("Anti-non-Monster/Vehicle 2+", ["Vehicle"], 2) == []


def test_anti_manual_override_mins_with_auto():
    opts = AttackOptions(anti_active=True, anti_threshold=3)
    assert len(_anti_wounds("Anti-Vehicle 5+", ["Vehicle"], 3, opts)) == 1
    assert len(_anti_wounds("Anti-Vehicle 2+", ["Vehicle"], 3, opts)) == 1
    # manual alone, weapon has no matching Anti
    assert len(_anti_wounds("Anti-Vehicle 5+", ["Infantry"], 3, opts)) == 1


# 3. dice-valued keywords
def test_sustained_hits_d3_rolled_per_crit():
    attacker = _weapon(skill=4, keywords=parse_keywords("Sustained Hits D3"))
    assert parse_keywords("Sustained Hits D3").sustained_hits == DiceNotation(1, 3, 0)
    events = _resolve_hits(attacker, AttackOptions(grant_sustained_hits=1), 1, QueueRandom([6, 2]))
    assert events == [False] * (1 + 2 + 1)


def test_rapid_fire_d3_adds_rolled_attacks():
    kw = parse_keywords("Rapid Fire D3")
    attacker = AttackerProfile("W", False, DiceNotation(0, 0, 1), 2, 4, 0, DiceNotation(0, 0, 0), kw)
    rng = QueueRandom([3, 1, 1, 1, 1])  # D3 -> 3 extra, then 4 forced misses
    resolve_sequence(attacker, _unit(model_count=1), AttackOptions(half_range=True), rng)
    assert rng.exhausted()


def test_melta_dice_notation_parsed_and_applied():
    kw = parse_keywords("Melta D3")
    assert kw.melta == DiceNotation(1, 3, 0)
    attacker = _weapon(skill=2, strength=10, keywords=kw, damage_bonus=1)
    defender = _unit(toughness=1, save=7, wounds_per_model=10, model_count=1)
    # hit 6, wound 6, melta D3 rolls 3 -> 1 + 3
    res = resolve_sequence(attacker, defender, AttackOptions(half_range=True), QueueRandom([6, 6, 3]))
    assert res.damage_dealt == 4


# 4. ability sign
def test_add_one_to_hit_targeting_this_unit_is_plus_one():
    (e,) = extract_effects([{"name": "Beacon", "text": "Each time an attack targets this unit, add 1 to the Hit roll."}])
    assert e.side == "defender"
    assert e.option_patch == {"hit_modifier": 1}
    assert e.summary == "+1 to Hit (against this unit)"


def test_add_one_to_wound_targeting_this_unit_is_plus_one():
    (e,) = extract_effects([{"name": "X", "text": "Each time an attack targets this unit, add 1 to the Wound roll."}])
    assert e.option_patch == {"wound_modifier": 1}


# 5. negation / defender hints
@pytest.mark.parametrize(
    "text",
    [
        "Each time an attack targets this unit, that attack cannot benefit from Lethal Hits.",
        "Weapons can't use Devastating Wounds against this unit.",
        "This unit does not gain Sustained Hits 1.",
        "Attacks that target this unit have Lethal Hits.",
        "That model is unable to re-roll the Hit roll.",
        "Models in this unit lose Lethal Hits.",
    ],
)
def test_negated_or_defender_grants_not_detected(text):
    assert extract_effects([{"name": "N", "text": text}]) == []


def test_plain_grant_still_detected():
    (e,) = extract_effects([{"name": "G", "text": "Weapons in this unit have Lethal Hits."}])
    assert e.option_patch == {"grant_lethal_hits": True}


# 6. damage reduction and options
def _dmg(damage_bonus, **opts):
    attacker = _weapon(skill=2, strength=10, damage_bonus=damage_bonus)
    defender = _unit(toughness=1, save=7, wounds_per_model=20, model_count=1)
    return resolve_sequence(attacker, defender, AttackOptions(**opts), QueueRandom([6, 6])).damage_dealt


def test_damage_reduction_min_one():
    assert _dmg(3, damage_reduction=1) == 2
    assert _dmg(1, damage_reduction=3) == 1


def test_halve_damage_rounds_up_before_reduction():
    assert _dmg(5, halve_damage=True) == 3
    assert _dmg(5, halve_damage=True, damage_reduction=1) == 2


def test_extract_damage_reduction_effects():
    (a,) = extract_effects([{"name": "A", "text": "Each time an attack targets this unit, subtract 1 from the Damage characteristic of that attack."}])
    assert a.side == "defender" and a.option_patch == {"damage_reduction": 1}
    (b,) = extract_effects([{"name": "B", "text": "Each time an attack targets this unit, halve the Damage characteristic of that attack."}])
    assert b.side == "defender" and b.option_patch == {"halve_damage": True}


def test_heavy_stationary_gives_plus_one_to_hit():
    attacker = _weapon(skill=4, keywords=parse_keywords("Heavy"))
    assert _resolve_hits(attacker, AttackOptions(), 1, QueueRandom([3])) == []
    assert len(_resolve_hits(attacker, AttackOptions(stationary=True), 1, QueueRandom([3]))) == 1


def test_indirect_fire_not_visible_minus_one_and_cover():
    attacker = _weapon(skill=4, keywords=parse_keywords("Indirect Fire"))
    assert len(_resolve_hits(attacker, AttackOptions(), 1, QueueRandom([4]))) == 1
    assert _resolve_hits(attacker, AttackOptions(not_visible=True), 1, QueueRandom([4])) == []
    plain = _weapon(skill=4)
    assert len(_resolve_hits(plain, AttackOptions(not_visible=True), 1, QueueRandom([4]))) == 1
    from app.sim.sequence import _armour_save_needed

    d = _unit(save=4)
    assert _armour_save_needed(attacker, d, AttackOptions(not_visible=True)) == 3
    assert _armour_save_needed(plain, d, AttackOptions(not_visible=True)) == 4


def test_hit_modifiers_still_clamp():
    attacker = _weapon(skill=4, keywords=parse_keywords("Heavy"))
    assert _resolve_hits(attacker, AttackOptions(hit_modifier=1, stationary=True), 1, QueueRandom([2])) == []


# 7. Lethal + Devastating
def test_lethal_with_devastating_pipeline_auto_wounds_then_saves():
    attacker = _weapon(skill=2, strength=1, keywords=WeaponKeywords(lethal_hits=True, devastating_wounds=True))
    defender = _unit(toughness=6, save=2, wounds_per_model=3, model_count=1)
    # hit 6 -> auto-wound (no wound roll, not devastating) -> save roll 6 succeeds
    rng = QueueRandom([6, 6])
    assert resolve_sequence(attacker, defender, AttackOptions(), rng).damage_dealt == 0
    assert rng.exhausted()


# 8. router
def _body(**over):
    body = {
        "attackers": [{"weapons": [{"weapon_characteristics": {"A": "2", "BS": "3+", "S": "4", "AP": "0", "D": "1"}, "weapon_count": 1}],
                       "options": {"trials": 50, "seed": 1}}],
        "defender_stats": {"T": "4", "Sv": "3+", "W": "2"},
        "defender_model_count": 5,
    }
    body.update(over)
    return body


def test_bad_dice_notation_is_422(client):
    body = _body()
    body["attackers"][0]["weapons"][0]["weapon_characteristics"]["A"] = "D6+D3"
    r = client.post("/simulate", json=body)
    assert r.status_code == 422
    assert "D6+D3" in r.json()["detail"]


def test_defender_keywords_and_new_options_accepted(client):
    body = _body(defender_keywords=["Vehicle"])
    body["attackers"][0]["weapons"][0]["weapon_characteristics"]["Keywords"] = "Anti-Vehicle 2+, Heavy"
    body["attackers"][0]["options"].update(damage_reduction=1, halve_damage=True, stationary=True, not_visible=False)
    assert client.post("/simulate", json=body).status_code == 200


def test_input_bounds(client):
    def with_opts(**o):
        b = _body()
        b["attackers"][0]["options"].update(o)
        return b

    for o in ({"trials": 0}, {"trials": 100_001}, {"hit_modifier": 4}, {"wound_modifier": -4}, {"damage_reduction": 4}, {"damage_reduction": -1}):
        assert client.post("/simulate", json=with_opts(**o)).status_code == 422, o
    assert client.post("/simulate", json=_body(defender_model_count=0)).status_code == 422
    assert client.post("/simulate", json=_body(defender_model_count=201)).status_code == 422
    b = _body()
    b["attackers"][0]["weapons"][0]["weapon_count"] = 201
    assert client.post("/simulate", json=b).status_code == 422
    b = _body()
    b["attackers"] = b["attackers"] * 11
    assert client.post("/simulate", json=b).status_code == 422
    b = _body()
    b["attackers"][0]["weapons"] = b["attackers"][0]["weapons"] * 21
    assert client.post("/simulate", json=b).status_code == 422
