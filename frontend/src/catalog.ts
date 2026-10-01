import type { UnitDefinition } from "./types";

// GW's own datasheet ordering for Battlefield Role, roughly "who leads, who holds the line,
// who else" -- anything not in this fixed list (or role === null) sorts after it as "Other".
export const ROLE_ORDER = [
  "Character",
  "Epic Hero",
  "Battleline",
  "Infantry",
  "Mounted",
  "Beast",
  "Monster",
  "Vehicle",
  "Dedicated Transport",
  "Fortification",
];

export function roleRank(role: string): number {
  const idx = ROLE_ORDER.indexOf(role);
  return idx === -1 ? ROLE_ORDER.length : idx;
}

export function groupDefsByRole(defs: UnitDefinition[]): [string, UnitDefinition[]][] {
  const byRole = new Map<string, UnitDefinition[]>();
  for (const u of defs) {
    const role = u.role ?? "Other";
    const arr = byRole.get(role) ?? [];
    arr.push(u);
    byRole.set(role, arr);
  }
  return Array.from(byRole.entries()).sort((a, b) => {
    const rankDiff = roleRank(a[0]) - roleRank(b[0]);
    return rankDiff !== 0 ? rankDiff : a[0].localeCompare(b[0]);
  });
}

// No dedicated backend flag (unlike is_legends): Crucible of War datasheets carry a "[Crucible]"
// name suffix and/or a "Crucible" keyword in the BSData.
export function isCrucible(u: UnitDefinition): boolean {
  return u.name.toLowerCase().includes("[crucible]") || u.keywords.some((k) => k.toLowerCase() === "crucible");
}

// Legends and Crucible units aren't part of a standard matched-play list.
export function isNonStandard(u: UnitDefinition): boolean {
  return u.is_legends || isCrucible(u);
}

// A roster's faction string doesn't always match a faction key in army-rules.json /
// detachments.json -- confirmed against real data: "Aeldari - Craftworlds"'s detachments live
// under "Xenos - Aeldari" and its army rules under the shared "Aeldari - Aeldari Library".
// Exact match first; then each of the roster faction's " - " segments, most specific (last)
// first, since the generic "Imperium" would hit the wrong (alphabetically first) entry; finally
// the same top-level category's shared "Library" entry.
export function matchFaction<T extends { faction: string }>(all: T[], faction: string): T | undefined {
  const exact = all.find((f) => f.faction === faction);
  if (exact) return exact;
  const segments = faction.split(" - ");
  for (const seg of [...segments].reverse()) {
    const match = all.find((f) => f.faction.includes(seg));
    if (match) return match;
  }
  return all.find((f) => f.faction.startsWith(`${segments[0]} - `) && f.faction.includes("Library"));
}
