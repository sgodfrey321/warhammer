import type { UnitAttachment, UnitOut } from "./types";

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
