from __future__ import annotations

from app.army_rule_handlers import bootstrap_army_rules, derive_army_faction
from app.army_rule_handlers.asuryani import _battle_focus_max
from app.models import DeclaredStatePool, Roster, UnitDefinition
from sqlmodel import select


def _definition(id_: str, *keywords: str) -> UnitDefinition:
    return UnitDefinition(
        id=id_,
        faction="Aeldari - Craftworlds",
        name=id_,
        keywords=list(keywords),
        source_catalogue_id="x",
        source_entry_id=id_,
    )


def test_derive_army_faction_majority_vote():
    definitions = [
        _definition("a", "Faction: Asuryani", "Infantry"),
        _definition("b", "Faction: Asuryani"),
        _definition("c", "Faction: Ynnari"),
    ]
    assert derive_army_faction(definitions) == "Asuryani"


def test_derive_army_faction_none_when_no_keywords():
    assert derive_army_faction([_definition("a", "Infantry")]) is None
    assert derive_army_faction([]) is None


def test_battle_focus_max_by_battle_size():
    assert _battle_focus_max("Incursion (1000 Point limit)") == 2
    assert _battle_focus_max("Strike Force (2000 Point limit)") == 4
    assert _battle_focus_max("Onslaught (3000 Point limit)") == 6
    assert _battle_focus_max(None) is None
    assert _battle_focus_max("Some Custom Size") is None


def test_bootstrap_army_rules_creates_battle_focus_pool_for_asuryani(session):
    roster = Roster(name="R", faction="Aeldari - Craftworlds", battle_size="Strike Force (2000 Point limit)")
    session.add(roster)
    session.commit()
    session.refresh(roster)

    bootstrap_army_rules(roster, [_definition("a", "Faction: Asuryani")], session)
    session.commit()

    pools = session.exec(select(DeclaredStatePool).where(DeclaredStatePool.roster_id == roster.id)).all()
    assert len(pools) == 1
    assert pools[0].name == "Battle Focus"
    assert pools[0].max_value == 4
    assert pools[0].scope == "battle_round"
    assert pools[0].stacking is False


def test_bootstrap_army_rules_noop_for_unregistered_faction(session):
    roster = Roster(name="R", faction="Chaos - World Eaters", battle_size="Strike Force (2000 Point limit)")
    session.add(roster)
    session.commit()
    session.refresh(roster)

    bootstrap_army_rules(roster, [_definition("a", "Faction: World Eaters")], session)
    session.commit()

    pools = session.exec(select(DeclaredStatePool).where(DeclaredStatePool.roster_id == roster.id)).all()
    assert pools == []


def test_bootstrap_army_rules_does_not_duplicate_existing_pool(session):
    roster = Roster(name="R", faction="Aeldari - Craftworlds", battle_size="Strike Force (2000 Point limit)")
    session.add(roster)
    session.commit()
    session.refresh(roster)
    session.add(DeclaredStatePool(roster_id=roster.id, name="Battle Focus", max_value=99, scope="battle_round"))
    session.commit()

    bootstrap_army_rules(roster, [_definition("a", "Faction: Asuryani")], session)
    session.commit()

    pools = session.exec(select(DeclaredStatePool).where(DeclaredStatePool.roster_id == roster.id)).all()
    assert len(pools) == 1
    assert pools[0].max_value == 99  # untouched, not overwritten with the derived value
