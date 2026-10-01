// Reading your own row (deck) against their column (vs) is deliberately asymmetric -- see
// MissionsExplorer.tsx. Layout matchups share the same deck/vs keys.
export function findMatchup<T extends { deck: string; vs: string }>(items: T[], deck: string | null, vs: string | null): T | undefined {
  return items.find((m) => m.deck === deck && m.vs === vs);
}

export const findMission = findMatchup;
