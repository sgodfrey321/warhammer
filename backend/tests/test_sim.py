from __future__ import annotations

from app.sim.dice import DiceNotation, parse_dice
from app.sim.keywords import WeaponKeywords, parse_keywords
from app.sim.montecarlo import simulate
from app.sim.profiles import AttackerProfile, DefenderProfile
from app.sim.sequence import (
    AttackOptions,
    _armour_save_needed,
    _resolve_hits,
    _resolve_wounds,
    _save_succeeds,
    _wound_target,
    resolve_sequence,
)


class QueueRandom:
    """A fake `random.Random` that returns pre-scripted values for `randint`,
    so tests can pin exactly which dice come up. Raises if the script runs
    out (a test bug) and exposes `exhausted()` so tests can assert every
    scripted value was actually consumed (i.e. no code path rolled dice we
    didn't expect it to)."""

    def __init__(self, values: list[int]):
        self._values = list(values)

    def randint(self, a: int, b: int) -> int:
        assert self._values, "QueueRandom ran out of scripted rolls"
        v = self._values.pop(0)
        assert a <= v <= b, f"scripted roll {v} out of range [{a},{b}]"
        return v

    def exhausted(self) -> bool:
        return not self._values


def _weapon(name="W", is_melee=False, skill=3, strength=4, ap=0, keywords=None, damage_bonus=1):
    return AttackerProfile(
        name=name,
        is_melee=is_melee,
        attacks=DiceNotation(0, 0, 1),
        skill=skill,
        strength=strength,
        ap=ap,
        damage=DiceNotation(0, 0, damage_bonus),
        keywords=keywords or WeaponKeywords(),
    )


def _unit(toughness=4, save=4, invuln=None, wounds_per_model=2, model_count=5):
    return DefenderProfile(
        toughness=toughness,
        save=save,
        invuln=invuln,
        wounds_per_model=wounds_per_model,
        model_count=model_count,
    )


# ---------------------------------------------------------------------------
# dice.py
# ---------------------------------------------------------------------------


def test_parse_dice_flat_int():
    assert parse_dice("4") == DiceNotation(count=0, die=0, bonus=4)


def test_parse_dice_die():
    assert parse_dice("D6") == DiceNotation(count=1, die=6, bonus=0)


def test_parse_dice_multiplier():
    assert parse_dice("2D6") == DiceNotation(count=2, die=6, bonus=0)


def test_parse_dice_die_plus_bonus():
    assert parse_dice("D3+1") == DiceNotation(count=1, die=3, bonus=1)


def test_parse_dice_missing_or_na():
    assert parse_dice(None) == DiceNotation(0, 0, 0)
    assert parse_dice("-") == DiceNotation(0, 0, 0)
    assert parse_dice("N/A") == DiceNotation(0, 0, 0)


def test_roll_dice_uses_injected_rng():
    rng = QueueRandom([3, 5])
    assert DiceNotation(2, 6, 1).roll(rng) == 3 + 5 + 1
    assert rng.exhausted()


# ---------------------------------------------------------------------------
# keywords.py
# ---------------------------------------------------------------------------


def test_parse_keywords_tolerant_of_case_and_hyphens():
    kw = parse_keywords("twin-linked, SUSTAINED HITS 1, Anti-Vehicle 4+")
    assert kw.twin_linked is True
    assert kw.sustained_hits == 1
    assert kw.anti_threshold == 4


def test_parse_keywords_unknown_is_noop():
    kw = parse_keywords("Some Made Up Keyword, Precision")
    assert kw == WeaponKeywords()


def test_parse_keywords_empty():
    assert parse_keywords(None) == WeaponKeywords()
    assert parse_keywords("") == WeaponKeywords()


def test_parse_keywords_rapid_fire_melta_blast():
    kw = parse_keywords("Rapid Fire 2, Melta 3, Blast")
    assert kw.rapid_fire == 2
    assert kw.melta == 3
    assert kw.blast is True


# ---------------------------------------------------------------------------
# profiles.py
# ---------------------------------------------------------------------------


def test_attacker_profile_from_ranged_weapon():
    weapon = {
        "name": "Bolt rifle",
        "range_type": "Ranged Weapons",
        "characteristics": {"A": "2", "BS": "3+", "S": "4", "AP": "-1", "D": "1", "Keywords": ""},
    }
    p = AttackerProfile.from_characteristics(weapon)
    assert p.is_melee is False
    assert p.skill == 3
    assert p.strength == 4
    assert p.ap == -1
    assert p.attacks.bonus == 2


def test_attacker_profile_from_melee_weapon_uses_ws():
    weapon = {
        "name": "Twin power fist",
        "range_type": "Melee Weapons",
        "characteristics": {"A": "3", "WS": "3+", "S": "8", "AP": "-2", "D": "2", "Keywords": "Twin-linked"},
    }
    p = AttackerProfile.from_characteristics(weapon)
    assert p.is_melee is True
    assert p.skill == 3
    assert p.keywords.twin_linked is True


def test_defender_profile_from_stats_with_and_without_invuln():
    d = DefenderProfile.from_stats({"T": "4", "Sv": "3+", "InSv": "4+", "W": "3"}, model_count=6)
    assert (d.toughness, d.save, d.invuln, d.wounds_per_model, d.model_count) == (4, 3, 4, 3, 6)

    d2 = DefenderProfile.from_stats({"T": "6", "Sv": "3+", "W": "3"}, model_count=3)
    assert d2.invuln is None


# ---------------------------------------------------------------------------
# sequence.py -- deterministic mechanics
# ---------------------------------------------------------------------------


def test_wound_target_table():
    assert _wound_target(strength=8, toughness=4) == 2  # S >= 2T
    assert _wound_target(strength=5, toughness=4) == 3  # S > T
    assert _wound_target(strength=4, toughness=4) == 4  # S == T
    assert _wound_target(strength=3, toughness=4) == 5  # S < T
    assert _wound_target(strength=2, toughness=8) == 6  # S <= T/2


def test_unmodified_one_always_fails_hit_even_with_plus_one():
    attacker = _weapon(skill=2)  # BS 2+, trivially easy
    defender = _unit()
    options = AttackOptions(hit_modifier=1)
    rng = QueueRandom([1])  # the only die rolled: the hit roll
    result = resolve_sequence(attacker, defender, options, rng)
    assert result.damage_dealt == 0
    assert result.models_slain == 0
    assert rng.exhausted()


def test_unmodified_six_always_crits_hit_and_wound_even_against_bad_odds():
    # skill=99 and default (no) modifiers -- a modified roll could never hit,
    # but an unmodified 6 always does, and always counts as a critical hit /
    # critical wound in turn.
    attacker = _weapon(skill=99, strength=4)
    defender = _unit(toughness=4, save=7, invuln=None, wounds_per_model=5, model_count=1)
    options = AttackOptions()
    # hit roll=6 (crit hit), wound roll=6 (crit wound). Save is unreachable
    # (needed=7) so it's skipped without rolling, and damage is a flat 1, so
    # no further dice are drawn.
    rng = QueueRandom([6, 6])
    result = resolve_sequence(attacker, defender, options, rng)
    assert result.damage_dealt == 1
    assert result.models_slain == 0
    assert rng.exhausted()


def test_reroll_hits_ones():
    attacker = _weapon(skill=4)
    options = AttackOptions(reroll_hits="ones")
    # attack 1: raw 1 -> rerolled (ones policy) to 5 -> hits (non-crit)
    # attack 2: raw 2 -> not a 1, no reroll -> modified 2 < 4 -> misses
    # attack 3: raw 6 -> crit hit
    rng = QueueRandom([1, 5, 2, 6])
    events = _resolve_hits(attacker, options, num_attacks=3, rng=rng)
    assert events == [False, False]
    assert rng.exhausted()


def test_reroll_hits_all_rerolls_any_unmodified_failure():
    attacker = _weapon(skill=4)
    options = AttackOptions(reroll_hits="all")
    # raw 2 is a natural failure vs target 4 -> rerolled to 5 -> now hits
    rng = QueueRandom([2, 5])
    events = _resolve_hits(attacker, options, num_attacks=1, rng=rng)
    assert events == [False]
    assert rng.exhausted()


def test_reroll_failures_uses_post_modifier_result_not_raw():
    # skill 3+, +1 to hit. A raw 2 becomes a modified 3 = a HIT, so "re-roll
    # failures" must NOT re-roll it (the old raw<target logic wrongly would).
    attacker = _weapon(skill=3)
    options = AttackOptions(reroll_hits="all", hit_modifier=1)
    rng = QueueRandom([2])  # only one die should be rolled -- no re-roll
    events = _resolve_hits(attacker, options, num_attacks=1, rng=rng)
    assert events == [False]  # a (non-crit) hit
    assert rng.exhausted()


def test_reroll_failures_rerolls_a_post_modifier_failure():
    # skill 3+, -1 to hit. A raw 3 becomes a modified 2 = a MISS, so it IS
    # re-rolled; the re-rolled 5 (modified 4) then hits.
    attacker = _weapon(skill=3)
    options = AttackOptions(reroll_hits="all", hit_modifier=-1)
    rng = QueueRandom([3, 5])
    events = _resolve_hits(attacker, options, num_attacks=1, rng=rng)
    assert events == [False]
    assert rng.exhausted()


def test_reroll_ones_ignores_non_one_modified_failures():
    # skill 3+, -1 to hit. A raw 3 (modified 2) is a failure but not a natural
    # 1, so "re-roll 1s" leaves it alone -> miss, no second die rolled.
    attacker = _weapon(skill=3)
    options = AttackOptions(reroll_hits="ones", hit_modifier=-1)
    rng = QueueRandom([3])
    events = _resolve_hits(attacker, options, num_attacks=1, rng=rng)
    assert events == []  # missed, not re-rolled
    assert rng.exhausted()


def test_single_reroll_rerolls_exactly_one_failure():
    # skill 4+, two attacks both miss (rolls 2,3). "Re-roll one Hit" re-rolls a
    # single failed die -> the 5 hits; the other miss stays a miss.
    attacker = _weapon(skill=4)
    options = AttackOptions(single_reroll_hit=True)
    rng = QueueRandom([2, 3, 5])  # two misses, then the single re-roll
    events = _resolve_hits(attacker, options, num_attacks=2, rng=rng)
    assert events == [False]  # exactly one recovered hit
    assert rng.exhausted()


def test_single_reroll_does_nothing_when_no_failures():
    # Both attacks already hit -> the single re-roll has nothing to re-roll and
    # rolls no extra die.
    attacker = _weapon(skill=4)
    options = AttackOptions(single_reroll_hit=True)
    rng = QueueRandom([4, 5])
    events = _resolve_hits(attacker, options, num_attacks=2, rng=rng)
    assert events == [False, False]
    assert rng.exhausted()


def test_single_reroll_is_redundant_under_reroll_all():
    # With re-roll-all every failure is already re-rolled once, so a die can't be
    # re-rolled again -- the single re-roll must add nothing (roll no extra die).
    attacker = _weapon(skill=4)
    options = AttackOptions(reroll_hits="all", single_reroll_hit=True)
    rng = QueueRandom([2, 3])  # one miss, its policy re-roll to 3 (still a miss); no further die
    events = _resolve_hits(attacker, options, num_attacks=1, rng=rng)
    assert events == []
    assert rng.exhausted()


def test_reroll_never_rerolls_a_success_or_crit():
    # An unmodified 6 is a crit success -- must never be re-rolled even under "all".
    attacker = _weapon(skill=4)
    options = AttackOptions(reroll_hits="all")
    rng = QueueRandom([6])  # a single die; a re-roll would exhaust and raise
    events = _resolve_hits(attacker, options, num_attacks=1, rng=rng)
    assert events == [False]  # a crit hit (no lethal, so guaranteed_wound False)
    assert rng.exhausted()


def test_full_pipeline_no_spillover_across_two_attacks():
    # 2 attacks, both hit and wound automatically (BS/wound target both 2,
    # rolled a comfortable 4), save is a guaranteed fail (rolled a 1), damage
    # is a flat 3 each. wounds_per_model=2 so each attack kills exactly one
    # model and wastes 1 point of damage -- it must NOT spill onto the next
    # model within the same attack.
    attacker = AttackerProfile(
        name="W",
        is_melee=False,
        attacks=DiceNotation(0, 0, 2),
        skill=2,
        strength=4,
        ap=0,
        damage=DiceNotation(0, 0, 3),
        keywords=WeaponKeywords(),
    )
    defender = _unit(toughness=4, save=4, invuln=None, wounds_per_model=2, model_count=5)
    options = AttackOptions()
    # Resolution is phase-batched (all hit rolls, then all wound rolls, then
    # all save rolls) rather than per-attack: 2 hit rolls (both succeed,
    # non-crit), then 2 wound rolls (both succeed, non-crit), then 2 save
    # rolls (both a forced-fail unmodified 1).
    rng = QueueRandom([4, 4, 4, 4, 1, 1])
    result = resolve_sequence(attacker, defender, options, rng)
    assert result.damage_dealt == 4  # 2 wounds actually removed per kill, not 3
    assert result.models_slain == 2
    assert rng.exhausted()


def test_devastating_wounds_bypasses_save_and_still_no_spillover():
    attacker = _weapon(skill=2, strength=4, keywords=WeaponKeywords(devastating_wounds=True), damage_bonus=5)
    defender = _unit(toughness=4, save=2, invuln=None, wounds_per_model=2, model_count=3)
    options = AttackOptions()
    # hit=6 (crit, non-lethal so still rolls to wound), wound=6 (crit -> devastating).
    # No save roll at all (bypassed), damage is a flat 5 against a 2-wound model:
    # kills it (2 dealt) and the remaining 3 points of this one attack are lost.
    rng = QueueRandom([6, 6])
    result = resolve_sequence(attacker, defender, options, rng)
    assert result.damage_dealt == 2
    assert result.models_slain == 1
    assert rng.exhausted()


def test_lethal_hits_auto_wounds_when_devastating_absent():
    attacker = _weapon(skill=2, strength=1, keywords=WeaponKeywords(lethal_hits=True))  # S=1 -> normally needs 6+ to wound
    defender = _unit(toughness=6, save=7, invuln=None, wounds_per_model=3, model_count=1)
    options = AttackOptions()
    # hit=6 (crit) -> Lethal Hits auto-wounds, skipping the wound roll entirely.
    # No save roll drawn (needed=7, unreachable). Damage is flat 1.
    rng = QueueRandom([6])
    result = resolve_sequence(attacker, defender, options, rng)
    assert result.damage_dealt == 1
    assert rng.exhausted()


def test_lethal_and_devastating_together_does_not_auto_wound():
    # When both keywords are present, auto-wounding via Lethal would skip the
    # wound roll and so could never crit-wound, meaning Devastating Wounds
    # could never trigger. So the crit hit must roll to wound normally.
    attacker = _weapon(skill=2, strength=4, keywords=WeaponKeywords(lethal_hits=True, devastating_wounds=True))
    events = _resolve_hits(attacker, AttackOptions(), num_attacks=1, rng=QueueRandom([6]))
    assert events == [False]  # not guaranteed_wound, despite Lethal Hits being present


def test_sustained_hits_adds_extra_non_crit_hits():
    attacker = _weapon(skill=4, keywords=WeaponKeywords(sustained_hits=2))
    rng = QueueRandom([6])  # a single crit hit
    events = _resolve_hits(attacker, AttackOptions(), num_attacks=1, rng=rng)
    assert events == [False, False, False]  # original hit + 2 sustained, none guaranteed-wound
    assert rng.exhausted()


def test_twin_linked_always_rerolls_failed_wounds():
    attacker = _weapon(strength=4, keywords=WeaponKeywords(twin_linked=True))
    defender = _unit(toughness=4)  # wound target 4
    # hit_events: one normal (non-guaranteed) hit
    # wound roll 1 (fail) -> Twin-linked forces a reroll even though the
    # caller passed reroll_wounds="none" -- rerolled to 5 (success, non-crit)
    rng = QueueRandom([1, 5])
    wounds = _resolve_wounds(attacker, defender, AttackOptions(reroll_wounds="none"), [False], rng)
    assert len(wounds) == 1
    assert wounds[0].devastating is False
    assert rng.exhausted()


def test_torrent_auto_hits_without_rolling_dice():
    attacker = _weapon(strength=4, keywords=WeaponKeywords(torrent=True))
    defender = _unit(toughness=4, save=7, wounds_per_model=1, model_count=1)
    # No hit dice rolled at all (torrent auto-hits). 3 wound rolls follow,
    # scripted to all fail outright (unmodified 1).
    rng = QueueRandom([1, 1, 1])
    result = resolve_sequence(
        AttackerProfile(
            name="W", is_melee=False, attacks=DiceNotation(0, 0, 3), skill=None, strength=4, ap=0,
            damage=DiceNotation(0, 0, 1), keywords=attacker.keywords,
        ),
        defender,
        AttackOptions(),
        rng,
    )
    assert result.damage_dealt == 0
    assert rng.exhausted()


def test_anti_keyword_triggers_critical_wound_below_natural_six():
    attacker = _weapon(strength=1)  # normally needs a 6+ to wound vs T much higher
    defender = _unit(toughness=8)  # wound target 6 without Anti
    options = AttackOptions(anti_active=True, anti_threshold=4)
    # raw wound roll of 4 is not a natural 6, but Anti-X 4+ makes it a critical
    # wound (and thus an automatic success) despite the base wound target being 6.
    rng = QueueRandom([4])
    wounds = _resolve_wounds(attacker, defender, options, [False], rng)
    assert len(wounds) == 1
    assert rng.exhausted()


def test_cover_improves_armour_save_but_caps_at_two_plus():
    attacker = _weapon(ap=0)
    defender = _unit(save=2)
    # Sv 2+ with Cover would naturally become 1+, but is capped at 2+.
    assert _armour_save_needed(attacker, defender, AttackOptions(cover=True)) == 2


def test_ignores_cover_negates_the_cover_toggle():
    attacker = _weapon(ap=0, keywords=WeaponKeywords(ignores_cover=True))
    defender = _unit(save=4)
    assert _armour_save_needed(attacker, defender, AttackOptions(cover=True)) == 4


def test_save_roll_unmodified_one_always_fails():
    rng = QueueRandom([1])
    assert _save_succeeds(rng, needed=2) is False


def test_rapid_fire_adds_attacks_only_at_half_range():
    attacker = AttackerProfile(
        name="W", is_melee=False, attacks=DiceNotation(0, 0, 1), skill=2, strength=4, ap=0,
        damage=DiceNotation(0, 0, 0), keywords=WeaponKeywords(rapid_fire=2),
    )
    defender = _unit(model_count=1)
    # Out of half range: 1 base attack, misses (raw=1).
    rng = QueueRandom([1])
    assert resolve_sequence(attacker, defender, AttackOptions(half_range=False), rng).damage_dealt == 0
    assert rng.exhausted()
    # At half range: 1 + 2 = 3 attacks, all forced misses (raw=1 each).
    rng2 = QueueRandom([1, 1, 1])
    resolve_sequence(attacker, defender, AttackOptions(half_range=True), rng2)
    assert rng2.exhausted()


def test_blast_adds_one_attack_per_five_models():
    attacker = AttackerProfile(
        name="W", is_melee=False, attacks=DiceNotation(0, 0, 1), skill=2, strength=4, ap=0,
        damage=DiceNotation(0, 0, 0), keywords=WeaponKeywords(blast=True),
    )
    defender = _unit(model_count=12)  # +2 attacks (12 // 5)
    rng = QueueRandom([1, 1, 1])  # 1 base + 2 blast = 3 hit rolls, all forced misses
    resolve_sequence(attacker, defender, AttackOptions(), rng)
    assert rng.exhausted()


# ---------------------------------------------------------------------------
# montecarlo.py -- statistical
# ---------------------------------------------------------------------------


def test_worked_example_mean_damage():
    # 10 attacks, BS 3+ (4/6 to hit), S/T giving 3+ to wound (4/6), Sv 4+ AP 0
    # (1/2 unsaved), D=1. Expected unsaved wounds = 10 * 4/6 * 4/6 * 1/2 ≈ 2.222.
    # One model with 10 wounds so total damage capacity (10) exactly matches
    # the maximum possible unsaved hits (10) -- no-spillover loss can't skew
    # the mean here since it will never actually trigger.
    weapon = {
        "range_type": "Ranged Weapons",
        "characteristics": {"A": "10", "BS": "3+", "S": "5", "AP": "0", "D": "1", "Keywords": ""},
    }
    attacker = AttackerProfile.from_characteristics(weapon)
    defender = DefenderProfile.from_stats({"T": "4", "Sv": "4+", "W": "10"}, model_count=1)

    result = simulate(attacker, defender, AttackOptions(), trials=20000, seed=12345)

    expected = 10 * (4 / 6) * (4 / 6) * (1 / 2)
    assert abs(result.mean_damage - expected) < 0.15


def test_weapon_count_scales_damage_and_shares_unit_state():
    # A single A=1 weapon barely scratches a 16-wound model; five of them
    # firing at the same unit each trial should deal ~5x the wounds (they share
    # one DefenderState, so damage accumulates across the volley).
    weapon = {
        "range_type": "Ranged Weapons",
        "characteristics": {"A": "1", "BS": "4+", "S": "14", "AP": "-4", "D": "D6+1"},
    }
    attacker = AttackerProfile.from_characteristics(weapon)
    defender = DefenderProfile.from_stats({"T": "11", "Sv": "2+", "InSv": "4+", "W": "16"}, model_count=1)

    one = simulate(attacker, defender, AttackOptions(), trials=20000, seed=3, weapon_count=1)
    five = simulate(attacker, defender, AttackOptions(), trials=20000, seed=3, weapon_count=5)

    assert five.weapon_count == 5
    # ~5x within Monte Carlo noise (single-shot mean is small, so use a ratio band).
    assert 4.3 < (five.mean_damage / one.mean_damage) < 5.7


def test_damage_histogram_covers_all_trials_and_matches_mean():
    weapon = {
        "range_type": "Ranged Weapons",
        "characteristics": {"A": "10", "BS": "3+", "S": "5", "AP": "0", "D": "1", "Keywords": ""},
    }
    attacker = AttackerProfile.from_characteristics(weapon)
    defender = DefenderProfile.from_stats({"T": "4", "Sv": "4+", "W": "10"}, model_count=1)

    result = simulate(attacker, defender, AttackOptions(), trials=5000, seed=9)

    assert sum(result.damage_histogram.values()) == 5000
    # Mean rebuilt from the histogram must match the reported mean_damage.
    weighted = sum(dmg * n for dmg, n in result.damage_histogram.items())
    assert abs(weighted / 5000 - result.mean_damage) < 1e-9


def test_simulate_p_wipe_and_p_kill_and_histogram_shape():
    # A weapon that always hits, always wounds, is never saved and always
    # one-shots a 1-wound model unit of 3 -- should wipe essentially every time.
    weapon = {
        "range_type": "Ranged Weapons",
        "characteristics": {"A": "6", "BS": "2+", "S": "10", "AP": "-4", "D": "1", "Keywords": ""},
    }
    attacker = AttackerProfile.from_characteristics(weapon)
    defender = DefenderProfile.from_stats({"T": "1", "Sv": "6+", "W": "1"}, model_count=3)

    result = simulate(attacker, defender, AttackOptions(), trials=2000, seed=7)

    assert result.p_wipe > 0.9
    assert result.p_at_least_one_kill > 0.95
    assert result.models_slain_histogram.get(3, 0) > 0
    assert sum(result.models_slain_histogram.values()) == 2000
    assert set(result.damage_percentiles.keys()) == {10, 50, 90}


def test_damage_thresholds_and_total_wounds():
    weapon = {
        "range_type": "Ranged Weapons",
        "characteristics": {"A": "10", "BS": "3+", "S": "5", "AP": "0", "D": "1", "Keywords": ""},
    }
    attacker = AttackerProfile.from_characteristics(weapon)
    defender = DefenderProfile.from_stats({"T": "4", "Sv": "4+", "W": "4"}, model_count=4)  # 16 total wounds

    result = simulate(attacker, defender, AttackOptions(), trials=5000, seed=4)

    assert result.total_wounds == 16
    # Thresholds are at 1/4, 1/2, 3/4, 4/4 of the pool.
    assert sorted(result.damage_at_least.keys()) == [4, 8, 12, 16]
    # P(>= X) must be monotonically non-increasing as X grows.
    probs = [result.damage_at_least[x] for x in sorted(result.damage_at_least)]
    assert all(probs[i] >= probs[i + 1] for i in range(len(probs) - 1))


def test_rounds_to_destroy_is_cumulative_and_median_consistent():
    weapon = {
        "range_type": "Ranged Weapons",
        "characteristics": {"A": "3", "BS": "3+", "S": "8", "AP": "-2", "D": "2", "Keywords": ""},
    }
    attacker = AttackerProfile.from_characteristics(weapon)
    defender = DefenderProfile.from_stats({"T": "8", "Sv": "3+", "W": "12"}, model_count=1)

    result = simulate(attacker, defender, AttackOptions(), trials=4000, seed=6)

    by_round = [result.destroyed_by_round[n] for n in sorted(result.destroyed_by_round)]
    assert all(by_round[i] <= by_round[i + 1] for i in range(len(by_round) - 1))  # cumulative
    assert all(0.0 <= p <= 1.0 for p in by_round)
    # median = first round whose cumulative probability reaches 0.5.
    if result.median_rounds_to_destroy is not None:
        assert result.destroyed_by_round[result.median_rounds_to_destroy] >= 0.5


def test_guaranteed_one_shot_destroys_in_one_round():
    # Always hits, always wounds, ignores the save, 6 damage vs a 1-wound model -> dead round 1.
    weapon = {
        "range_type": "Ranged Weapons",
        "characteristics": {"A": "6", "BS": "2+", "S": "20", "AP": "-6", "D": "6", "Keywords": ""},
    }
    attacker = AttackerProfile.from_characteristics(weapon)
    defender = DefenderProfile.from_stats({"T": "1", "Sv": "6+", "W": "1"}, model_count=1)

    result = simulate(attacker, defender, AttackOptions(), trials=1000, seed=2)
    assert result.median_rounds_to_destroy == 1
    assert result.destroyed_by_round[1] > 0.99


# ---------------------------------------------------------------------------
# abilities.py -- ability text extraction
# ---------------------------------------------------------------------------


def test_extract_psychic_guidance_plus_one_hit_with_condition():
    from app.sim.abilities import extract_effects

    abilities = [
        {
            "name": "Psychic Guidance",
            "text": (
                'While this unit is within 12" of one or more friendly Aeldari Psyker '
                "models, models in this unit have a Leadership characteristic of 6+ and "
                "each time a model in this unit makes an attack, add 1 to the Hit roll."
            ),
        }
    ]
    effects = extract_effects(abilities)
    assert len(effects) == 1
    e = effects[0]
    assert e.ability_name == "Psychic Guidance"
    assert e.side == "attacker"
    assert e.option_patch == {"hit_modifier": 1}
    assert "within 12" in e.condition  # condition surfaced for the player to confirm


def test_extract_defender_minus_one_to_hit_is_defender_side():
    from app.sim.abilities import extract_effects

    effects = extract_effects(
        [{"name": "Smokescreen", "text": "Each time an attack targets this unit, subtract 1 from the Hit roll."}]
    )
    assert len(effects) == 1
    assert effects[0].side == "defender"
    assert effects[0].option_patch == {"hit_modifier": -1}


def test_extract_ability_granted_sustained_hits():
    from app.sim.abilities import extract_effects

    # Dire Avengers' Bladestorm grants [Sustained Hits 1] (conditional on half range).
    effects = extract_effects(
        [
            {
                "name": "Bladestorm",
                "text": "Ranged weapons equipped by models in this unit have the [Sustained Hits 1] ability while targeting an enemy unit within half range.",
            }
        ]
    )
    assert len(effects) == 1
    assert effects[0].option_patch == {"grant_sustained_hits": 1}
    assert "half range" in effects[0].condition  # positional -> stays a manual toggle


def test_granted_sustained_hits_raises_damage():
    weapon = {
        "range_type": "Ranged Weapons",
        "characteristics": {"A": "3", "BS": "3+", "S": "4", "AP": "0", "D": "1", "Keywords": ""},
    }
    attacker = AttackerProfile.from_characteristics(weapon)
    defender = DefenderProfile.from_stats({"T": "3", "Sv": "6+", "W": "60"}, model_count=1)

    base = simulate(attacker, defender, AttackOptions(), trials=20000, seed=3, weapon_count=5).mean_damage
    sus = simulate(
        attacker, defender, AttackOptions(grant_sustained_hits=1), trials=20000, seed=3, weapon_count=5
    ).mean_damage
    assert sus > base + 0.3  # extra hits on crits meaningfully raise output


def test_extract_feel_no_pain_is_defender_side():
    from app.sim.abilities import extract_effects

    effects = extract_effects([{"name": "Undying", "text": "Models in this unit have Feel No Pain 5+."}])
    assert len(effects) == 1
    assert effects[0].side == "defender"
    assert effects[0].option_patch == {"fnp": 5}


def test_extract_rerolls_ones_vs_all():
    from app.sim.abilities import extract_effects

    ones = extract_effects([{"name": "A", "text": "You can re-roll a Hit roll of 1 for this weapon."}])
    assert ones[0].option_patch == {"reroll_hits": "ones"}
    allr = extract_effects([{"name": "B", "text": "You can re-roll the Wound roll."}])
    assert allr[0].option_patch == {"reroll_wounds": "all"}


def test_extract_single_reroll_maps_to_single_reroll_flags():
    from app.sim.abilities import extract_effects

    # Fire Prism's Crystal Matrix re-rolls ONE die each -- must map to the single-reroll flags,
    # NOT the re-roll-all policy (which would grossly overstate it).
    effects = extract_effects(
        [
            {
                "name": "Crystal Matrix",
                "text": "Each time this model is selected to shoot, you can re-roll one Hit roll and you can re-roll one Wound roll when resolving those attacks.",
            }
        ]
    )
    patches = [e.option_patch for e in effects]
    assert {"single_reroll_hit": True} in patches
    assert {"single_reroll_wound": True} in patches
    # And it must NOT have emitted a reroll-all/ones policy.
    assert all("reroll_hits" not in p and "reroll_wounds" not in p for p in patches)


def test_extract_target_conditional_rerolls_gate_on_keywords():
    from app.sim.abilities import extract_effects

    # Fire Dragons' Assured Destruction: full re-rolls of Hit/Wound/Damage, but only vs a
    # Monster or Vehicle -- every effect must carry that target-keyword gate.
    txt = (
        "In your Shooting phase, each time a model in this unit makes a ranged attack that "
        "targets a Monster or Vehicle unit, you can re-roll the Hit roll, you can re-roll the "
        "Wound roll and you can re-roll the Damage roll."
    )
    effects = extract_effects([{"name": "Assured Destruction", "text": txt}])
    summaries = {e.summary for e in effects}
    assert {"Re-roll all Hit", "Re-roll all Wound", "Re-roll Damage"} <= summaries
    for e in effects:
        assert e.requires_target_keywords == ["Monster", "Vehicle"]


def test_roll_damage_rerolls_below_average_only():
    from app.sim.dice import DiceNotation
    from app.sim.sequence import _roll_damage

    d6 = DiceNotation(1, 6, 0)  # average 3.5
    assert _roll_damage(d6, True, QueueRandom([2, 6])) == 6  # low roll re-rolled, new kept
    assert _roll_damage(d6, True, QueueRandom([5])) == 5  # above average -> not re-rolled
    assert _roll_damage(d6, False, QueueRandom([2])) == 2  # reroll off -> low roll kept
    assert _roll_damage(DiceNotation(0, 0, 3), True, QueueRandom([])) == 3  # flat damage: nothing to re-roll


def test_reroll_damage_raises_mean_damage():
    weapon = {
        "range_type": "Ranged Weapons",
        "characteristics": {"A": "6", "BS": "2+", "S": "10", "AP": "-4", "D": "D6", "Keywords": ""},
    }
    attacker = AttackerProfile.from_characteristics(weapon)
    defender = DefenderProfile.from_stats({"T": "5", "Sv": "6+", "W": "60"}, model_count=1)  # big soak, no kills

    base = simulate(attacker, defender, AttackOptions(), trials=20000, seed=8).mean_damage
    rr = simulate(attacker, defender, AttackOptions(reroll_damage=True), trials=20000, seed=8).mean_damage
    assert rr > base + 0.5  # re-rolling low damage rolls meaningfully raises the mean


def test_extract_ignores_plain_ability_text():
    from app.sim.abilities import extract_effects

    # "War Construct" has no attack-sequence modifier -> no effect detected.
    effects = extract_effects([{"name": "War Construct", "text": "This unit is eligible to shoot in a turn in which it Fell Back."}])
    assert effects == []


def test_analyze_endpoint(client):
    body = {
        "abilities": [
            {"name": "Psychic Guidance", "text": "each time a model in this unit makes an attack, add 1 to the Hit roll."},
            {"name": "War Construct", "text": "This unit is eligible to shoot in a turn in which it Fell Back."},
        ]
    }
    resp = client.post("/simulate/analyze", json=body)
    assert resp.status_code == 200
    effects = resp.json()["effects"]
    assert len(effects) == 1
    assert effects[0]["ability_name"] == "Psychic Guidance"
    assert effects[0]["option_patch"] == {"hit_modifier": 1}


# ---------------------------------------------------------------------------
# router
# ---------------------------------------------------------------------------


def test_simulate_endpoint(client):
    body = {
        "attackers": [
            {
                "weapons": [
                    {
                        "weapon_characteristics": {"A": "5", "BS": "3+", "S": "5", "AP": "-1", "D": "1", "Keywords": "Sustained Hits 1"},
                        "range_type": "Ranged Weapons",
                        "weapon_count": 1,
                    }
                ],
                "options": {"trials": 500, "seed": 1},
            }
        ],
        "defender_stats": {"T": "4", "Sv": "3+", "W": "2"},
        "defender_model_count": 5,
    }
    resp = client.post("/simulate", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["trials"] == 500
    assert data["mean_damage"] >= 0
    assert 0.0 <= data["p_at_least_one_kill"] <= 1.0
    assert 0.0 <= data["p_wipe"] <= 1.0


def test_simulate_endpoint_multiple_units(client):
    # Two attacking units firing into one target -> combined weapon_count and more damage than
    # either alone; each group keeps its own options.
    fusion = {"weapon_characteristics": {"A": "1", "BS": "3+", "S": "9", "AP": "-4", "D": "D6"}, "range_type": "Ranged Weapons", "weapon_count": 4}
    prism = {"weapon_characteristics": {"A": "2", "BS": "3+", "S": "18", "AP": "-4", "D": "D6"}, "range_type": "Ranged Weapons", "weapon_count": 1}
    body = {
        "attackers": [
            {"weapons": [fusion], "options": {"trials": 3000, "seed": 2}},
            {"weapons": [prism], "options": {"trials": 3000, "seed": 2}},
        ],
        "defender_stats": {"T": "11", "Sv": "2+", "InSv": "4+", "W": "16"},
        "defender_model_count": 1,
    }
    resp = client.post("/simulate", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["weapon_count"] == 5  # 4 fusion + 1 prism
    assert data["mean_damage"] > 0


def test_simulate_endpoint_mixed_loadout():
    # A mixed loadout (squad gun + a different Exarch gun) fires both lines into one target;
    # its mean damage must exceed either line alone. simulate_lines directly, avoiding HTTP.
    from app.sim.montecarlo import simulate_lines

    squad = AttackerProfile.from_characteristics(
        {"range_type": "Ranged Weapons", "characteristics": {"A": "1", "BS": "3+", "S": "9", "AP": "-4", "D": "D6"}}
    )
    exarch = AttackerProfile.from_characteristics(
        {"range_type": "Ranged Weapons", "characteristics": {"A": "2", "BS": "3+", "S": "5", "AP": "-1", "D": "2"}}
    )
    defender = DefenderProfile.from_stats({"T": "9", "Sv": "3+", "W": "40"}, model_count=1)

    squad_only = simulate_lines([(squad, 4)], defender, AttackOptions(), trials=8000, seed=1)
    combined = simulate_lines([(squad, 4), (exarch, 1)], defender, AttackOptions(), trials=8000, seed=1)

    assert combined.weapon_count == 5  # 4 + 1 copies
    assert combined.mean_damage > squad_only.mean_damage


def test_per_group_contributions_sum_to_total():
    from app.sim.montecarlo import simulate_groups

    a = AttackerProfile.from_characteristics(
        {"range_type": "Ranged Weapons", "characteristics": {"A": "3", "BS": "3+", "S": "6", "AP": "-1", "D": "1"}}
    )
    b = AttackerProfile.from_characteristics(
        {"range_type": "Ranged Weapons", "characteristics": {"A": "2", "BS": "2+", "S": "8", "AP": "-2", "D": "2"}}
    )
    defender = DefenderProfile.from_stats({"T": "6", "Sv": "4+", "W": "40"}, model_count=1)

    r = simulate_groups([([(a, 3)], AttackOptions()), ([(b, 2)], AttackOptions())], defender, trials=8000, seed=5)

    assert len(r.per_group_damage) == 2
    # Per-group mean contributions sum to the combined mean (both fire into one shared target).
    assert abs(sum(r.per_group_damage) - r.mean_damage) < 1e-9
