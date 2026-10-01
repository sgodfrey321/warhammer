import type { Ability, UnitAttachment, UnitOut } from "./types";

// BattleScribe's Battlefield Role categories come through flattened into each unit's
// `keywords` list alongside everything else -- a Farseer's keywords include "Epic Hero",
// "Infantry", AND "Character" all at once (confirmed against real indexed data). There's no
// separate "primary category" field to read, so one group per unit is picked by the first
// match in this fixed priority order, matching how NewRecruit's own grouping reads (a
// Character-with-Epic-Hero renders under "Epic Hero", not also duplicated under "Infantry").
const ROLE_PRIORITY = [
  "Epic Hero",
  "Character",
  "Battleline",
  "Dedicated Transport",
  "Fortification",
  "Allied Units",
  "Vehicle",
  "Infantry",
  "Mounted",
] as const;

export function battlefieldRole(u: UnitOut): string {
  return ROLE_PRIORITY.find((role) => u.unit_definition.keywords.includes(role)) ?? "Other";
}

export interface RoleGroup {
  role: string;
  points: number;
  units: UnitOut[];
}

// Groups units by battlefieldRole(), ordered Epic Hero -> ... -> Other. A group's `points`
// deliberately excludes any unit that's a leader nested into another unit's card elsewhere
// (see RosterEditor.tsx's rendering) -- confirmed against the reference screenshot itself:
// a Character leading a Battleline unit still nests visually under Battleline, and the
// Battleline header's point total doesn't include the leader's cost, nor does the Character
// header's total include it either. The header reflects only what's actually listed under it.
export function groupUnitsByRole(units: UnitOut[], attachments: UnitAttachment[]): RoleGroup[] {
  const nestedLeaderIds = new Set(attachments.map((a) => a.leader_unit_id));

  const byRole = new Map<string, UnitOut[]>();
  for (const u of units) {
    const role = battlefieldRole(u);
    const arr = byRole.get(role) ?? [];
    arr.push(u);
    byRole.set(role, arr);
  }

  const order: string[] = [...ROLE_PRIORITY, "Other"];
  return order
    .filter((role) => byRole.has(role))
    .map((role) => {
      const groupUnits = byRole.get(role)!;
      const points = groupUnits
        .filter((u) => !nestedLeaderIds.has(u.id))
        .reduce((sum, u) => sum + u.unit_definition.points_cost, 0);
      return { role, points, units: groupUnits };
    });
}

// Matches the handful of ability-text phrasings confirmed against real indexed data for "this
// buffs whatever unit I'm attached to as a Leader" (e.g. the Autarch's Superlative Strategist:
// "While this model is leading a unit, you can re-roll Advance rolls made for that unit"). Only
// ~8.5% of abilities across sampled factions match this -- most buff-shaped ability text is a
// proximity aura keyed to a battlefield state ("within 6\" of this model") this app doesn't
// track, not a structural Leader/Bodyguard relationship it does (see UnitAttachment) -- so this
// is a narrow, deliberately-scoped net, not a general buff extractor.
const LEADER_BUFF_PATTERN = /while this model is leading a unit|while leading a unit|units? it leads|this unit is led by/i;

// BSData tags an ability's own *name* with a trailing "(Aura)"/"(Psychic)" (or, inconsistently,
// square brackets -- confirmed against real data, e.g. the Librarian's "Mental Fortress
// [Psychic]" vs. the more common "(Psychic)") -- a reliable structural signal, not a body-text
// guess like LEADER_BUFF_PATTERN above.
const ABILITY_TAG_PATTERN = /[([]\s*(Aura|Psychic)\s*[)\]]\s*$/i;

function abilityTag(ability: Ability): "Aura" | "Psychic" | null {
  const match = ability.name.match(ABILITY_TAG_PATTERN);
  if (!match) return null;
  return match[1].toLowerCase() === "aura" ? "Aura" : "Psychic";
}

export interface AbilityReference {
  unit: UnitOut;
  abilities: Ability[];
}

function referencesWhere(units: UnitOut[], matches: (ability: Ability, unit: UnitOut) => boolean): AbilityReference[] {
  return units
    .map((unit) => ({ unit, abilities: unit.unit_definition.abilities.filter((a) => matches(a, unit)) }))
    .filter((r) => r.abilities.length > 0);
}

// Leader-capable units (the "Leader" rule tag) and whichever of their own abilities read as a
// buff to whatever unit they're attached to -- a reference list independent of whether an
// attachment has actually been made yet, so it's useful *while deciding* who to attach, not just
// after.
export function leaderAbilityReferences(units: UnitOut[]): AbilityReference[] {
  return referencesWhere(units, (a, u) => u.unit_definition.rules.includes("Leader") && LEADER_BUFF_PATTERN.test(a.text));
}

// Auras: passive, always-on-while-in-range effects (e.g. Avatar of Khaine's "The Bloody Handed
// (Aura)"). Who they actually reach depends on live model positions on the table, which this app
// doesn't track -- so, like the Leader list above, this is a reminder that the ability exists,
// never something structured into a Buff or Synergy.
export function auraAbilityReferences(units: UnitOut[]): AbilityReference[] {
  return referencesWhere(units, (a) => abilityTag(a) === "Aura");
}

// Psychic powers and similarly-shaped "select a target, once this phase" abilities (e.g. the
// Farseer's Guide: "select one enemy unit within 18\" ... each time a friendly Aeldari model
// makes an attack that targets that enemy unit, [buff]"). The target is almost always an enemy
// unit chosen live at the table, never one of your own roster's units -- there's nothing to
// attribute a Synergy/Buff to, so this is reminder-only too. Excludes anything already listed as
// a Leader ability above (a dual-tagged ability like the Librarian's "Mental Fortress [Psychic]"
// shouldn't appear twice).
export function psychicAbilityReferences(units: UnitOut[]): AbilityReference[] {
  return referencesWhere(
    units,
    (a, u) => abilityTag(a) === "Psychic" && !(u.unit_definition.rules.includes("Leader") && LEADER_BUFF_PATTERN.test(a.text)),
  );
}
