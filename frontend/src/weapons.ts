import type { UnitOut } from "./types";

// Matches the loadout-matching convention already used in BattleTracker.tsx: strip the
// "➤ " firing-mode prefix and " - mode" suffix so a loadout item (which only ever names the
// plain weapon) can be matched back to its catalogue profile(s).
export function weaponBaseName(name: string): string {
  const stripped = name.replace(/^➤\s*/, "");
  const dashIndex = stripped.indexOf(" - ");
  return dashIndex === -1 ? stripped : stripped.slice(0, dashIndex);
}

// Averages GW's dice-notation Attacks values ("D6", "2D6", "D3+1", ...) to a single expected
// number for charting -- real indexed data confirmed these are always (multiplier)D(faces)(+bonus)?,
// never anything more exotic. Falls back to a plain numeric parse for fixed values ("1", "6"),
// and to 0 for anything unparseable rather than skewing the total.
export function parseAttacks(value: string): number {
  const match = value.match(/^(\d*)[Dd](\d+)(?:\+(\d+))?$/);
  if (match) {
    const multiplier = match[1] ? Number(match[1]) : 1;
    const faces = Number(match[2]);
    const bonus = match[3] ? Number(match[3]) : 0;
    return multiplier * ((faces + 1) / 2) + bonus;
  }
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

export interface StrengthBucket {
  strength: number;
  shots: number;
}

// Total attacks (ranged shots or melee swings) a roster can put out, grouped by weapon
// Strength. Only counts units with a confirmed loadout (loadout.length > 0) -- a manually-
// added unit has no per-model weapon counts to work from (see the hasLoadout fallback-to-
// catalogue behavior in BattleTracker.tsx/RosterEditor.tsx), so there's nothing reliable to
// count. One profile per weapon name (the first match for the given range type) -- a multi-
// mode weapon (strike/sweep) would otherwise double-count the same physical model's attacks.
// Doesn't model range-dependent bonuses (Rapid Fire, etc.) -- this is baseline profile Attacks
// only, matching the app's "bookkeeping, not a rules engine" scope elsewhere.
export function weaponAttacksByStrength(
  units: UnitOut[],
  rangeType: "Ranged Weapons" | "Melee Weapons",
): { buckets: StrengthBucket[]; skippedUnits: number } {
  const totals = new Map<number, number>();
  let skippedUnits = 0;

  for (const u of units) {
    if (u.loadout.length === 0) {
      skippedUnits += 1;
      continue;
    }
    for (const item of u.loadout) {
      const profile = u.unit_definition.weapons.find(
        (w) => w.range_type === rangeType && weaponBaseName(w.name) === item.name,
      );
      if (!profile) continue;
      const strength = Number(profile.characteristics.S);
      if (!Number.isFinite(strength)) continue;
      const attacks = parseAttacks(profile.characteristics.A ?? "");
      totals.set(strength, (totals.get(strength) ?? 0) + attacks * item.count);
    }
  }

  const buckets = Array.from(totals, ([strength, shots]) => ({
    strength,
    shots: Math.round(shots * 10) / 10,
  })).sort((a, b) => a.strength - b.strength);

  return { buckets, skippedUnits };
}

export interface MovementBucket {
  movement: number;
  units: number;
}

// "M" comes as inconsistent free text across the indexed data ('6"', '10', '20+"', '-' for no
// movement value at all) -- pull out the leading number and ignore the rest. Returns null for
// "-" (nothing to bucket).
export function parseMovement(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "-") return null;
  const match = trimmed.match(/(\d+)/);
  return match ? Number(match[1]) : null;
}

// Counts unit *entries*, not physical models -- there's no reliable per-unit model count in
// this data (loadout counts are weapon totals, not a model census, and quantity is always 1
// on an imported unit), so a 10-model squad and a lone Character both count as one bar
// contribution. Caveat surfaced in the chart's own caption, not hidden.
export function unitsByMovement(units: UnitOut[]): MovementBucket[] {
  const totals = new Map<number, number>();
  for (const u of units) {
    const raw = u.unit_definition.stats.M;
    if (!raw) continue;
    const movement = parseMovement(raw);
    if (movement === null) continue;
    totals.set(movement, (totals.get(movement) ?? 0) + 1);
  }
  return Array.from(totals, ([movement, count]) => ({ movement, units: count })).sort(
    (a, b) => a.movement - b.movement,
  );
}

export interface SaveBucket {
  save: string;
  sv: number;
  insv: number;
}

// "Sv" is always a clean "N+"; "InSv" (invulnerable save) is messier in the real data --
// trailing whitespace, footnote asterisks, range-dependent variants ("4+* / 5+", "5+ (Ranged)").
// Only the first "N+" is pulled out (the primary/best value) rather than trying to represent
// every footnote -- matches this chart's job (where does this roster's save profile sit),
// not a full rules reference.
export function parseSaveValue(raw: string | undefined): string | null {
  if (!raw) return null;
  const match = raw.match(/(\d)\+/);
  return match ? `${match[1]}+` : null;
}

// Grouped by save value (2+ best -> 7+ worst) so the two distributions -- armor save and
// invulnerable save -- read on the same scale in one chart.
export function unitsBySave(units: UnitOut[]): SaveBucket[] {
  const svCounts = new Map<string, number>();
  const insvCounts = new Map<string, number>();

  for (const u of units) {
    const sv = parseSaveValue(u.unit_definition.stats.Sv);
    if (sv) svCounts.set(sv, (svCounts.get(sv) ?? 0) + 1);
    const insv = parseSaveValue(u.unit_definition.stats.InSv);
    if (insv) insvCounts.set(insv, (insvCounts.get(insv) ?? 0) + 1);
  }

  const allSaves = new Set([...svCounts.keys(), ...insvCounts.keys()]);
  const buckets = Array.from(allSaves, (save) => ({
    save,
    sv: svCounts.get(save) ?? 0,
    insv: insvCounts.get(save) ?? 0,
  }));
  // "N+" isn't a valid Number() literal (the "+" parses to NaN) -- parseInt stops at the
  // first non-digit character instead, so "6+" -> 6 correctly.
  return buckets.sort((a, b) => parseInt(a.save, 10) - parseInt(b.save, 10));
}
