import type { LoadoutItem, UnitOut, Weapon } from "./types";

// Matches the loadout-matching convention already used in BattleTracker.tsx: strip the
// "➤ " firing-mode prefix and " - mode" suffix so a loadout item (which only ever names the
// plain weapon) can be matched back to its catalogue profile(s).
export function weaponBaseName(name: string): string {
  const stripped = name.replace(/^➤\s*/, "");
  const dashIndex = stripped.indexOf(" - ");
  return dashIndex === -1 ? stripped : stripped.slice(0, dashIndex);
}

// Normalise for matching a loadout item name against a catalogue profile name: drop a leading
// "The " and lower-case, since exports and the catalogue sometimes disagree there ("The Blade of
// Destruction" vs the profile "Blade of Destruction").
function normalizeWeaponName(name: string): string {
  return weaponBaseName(name).replace(/^the\s+/i, "").trim().toLowerCase();
}

// Match one loadout item (from a BattleScribe/NewRecruit export) to its catalogue weapon
// profile(s). Beyond the plain base-name match it tolerates a leading "The ", and -- when the
// whole name matches nothing -- a combined selection like "Banshee Blade and Shuriken Pistol",
// which it splits on "and"/"&" and matches each part. Returns every matching profile (a
// multi-mode weapon has more than one), or [] if genuinely un-indexed.
export function matchLoadoutWeapons(itemName: string, weapons: Weapon[]): Weapon[] {
  const target = normalizeWeaponName(itemName);
  const whole = weapons.filter((w) => normalizeWeaponName(w.name) === target);
  if (whole.length > 0) return whole;
  const parts = itemName
    .split(/\s+(?:and|&)\s+/i)
    .map((p) => p.replace(/^the\s+/i, "").trim().toLowerCase())
    .filter(Boolean);
  if (parts.length > 1) {
    return weapons.filter((w) => parts.includes(normalizeWeaponName(w.name)));
  }
  return [];
}

// Matches a loadout item to its catalogue profiles for charting: one profile per distinct weapon
// base name (first match), so a multi-mode weapon isn't double-counted, while a combined "A and B"
// item yields each of its distinct weapons once.
function loadoutProfiles(itemName: string, weapons: Weapon[], rangeType?: "Ranged Weapons" | "Melee Weapons"): Weapon[] {
  const matched = matchLoadoutWeapons(itemName, rangeType ? weapons.filter((w) => w.range_type === rangeType) : weapons);
  const seen = new Set<string>();
  return matched.filter((w) => {
    const key = normalizeWeaponName(w.name);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// GW's own datasheet ordering: Ranged Weapons section before Melee Weapons.
const WEAPON_SECTION_ORDER = ["Ranged Weapons", "Melee Weapons"];

// Splits a unit's catalogue weapon list into Ranged/Melee sections, in that fixed order --
// used everywhere a unit's full weapon list is shown (UnitsBrowser.tsx, RosterEditor.tsx's
// Available Units panel) so ranged and melee profiles don't render interleaved.
export function groupWeaponsByRangeType(weapons: Weapon[]): [string, Weapon[]][] {
  const groups = new Map<string, Weapon[]>();
  for (const w of weapons) {
    const arr = groups.get(w.range_type) ?? [];
    arr.push(w);
    groups.set(w.range_type, arr);
  }
  return WEAPON_SECTION_ORDER.filter((t) => groups.has(t)).map((t) => [t, groups.get(t) as Weapon[]]);
}

// Same grouping, but for a roster unit's actual equipped loadout rather than the full
// catalogue -- each item is placed by its matched profile's range_type (see weaponBaseName),
// falling back to "Other" for an item with no matching profile at all (surfaced instead of
// silently dropped, same as the "profile not indexed" case elsewhere).
export function groupLoadoutByRangeType(loadout: LoadoutItem[], defWeapons: Weapon[]): [string, LoadoutItem[]][] {
  const groups = new Map<string, LoadoutItem[]>();
  for (const item of loadout) {
    const rangeType = matchLoadoutWeapons(item.name, defWeapons)[0]?.range_type ?? "Other";
    const arr = groups.get(rangeType) ?? [];
    arr.push(item);
    groups.set(rangeType, arr);
  }
  const order = [...WEAPON_SECTION_ORDER, "Other"];
  return order.filter((t) => groups.has(t)).map((t) => [t, groups.get(t) as LoadoutItem[]]);
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

// One contributing unit+weapon pair behind a single Strength/to-hit bar segment -- what the
// "click a bar to see the units" drill-down actually lists.
export interface WeaponContribution {
  unitId: number;
  unitLabel: string;
  weaponName: string;
  skill: string;
  count: number;
  attacksPerModel: number;
  totalAttacks: number;
}

export interface StrengthSkillBucket {
  strength: number;
  // One numeric key per to-hit value present anywhere in the roster (e.g. "3+", "N/A") --
  // recharts stacks one <Bar dataKey={skill}> per key found across ALL buckets, so every
  // bucket needs the same keys (0 where this strength has no attacks at that to-hit value).
  [skill: string]: number;
}

export interface SkillStrengthBucket {
  skill: string;
  // One key per Strength value present anywhere in the roster -- mirrors StrengthSkillBucket,
  // just with the two axes swapped (this is "what do we hit on" as the primary axis instead of
  // "what do we wound with").
  [strength: string]: number | string;
}

export interface StrengthSkillResult {
  buckets: StrengthSkillBucket[];
  skillKeys: string[];
  bySkillBuckets: SkillStrengthBucket[];
  // The full, real set of Strength values -- used for the drill-down, which must aggregate every
  // Strength behind a clicked to-hit value, including ones folded into "Other" for display.
  strengthKeys: number[];
  // What the swapped chart actually renders/colors: capped at MAX_DISTINCT_STRENGTHS real values
  // (the biggest contributors) plus a synthetic "Other" entry for the rest, if any were folded.
  displayStrengths: (number | "Other")[];
  skippedUnits: number;
  // Keyed by `${strength}|${skill}` -- exactly what a clicked stack segment identifies, in
  // either chart orientation (both read the same underlying map).
  contributions: Map<string, WeaponContribution[]>;
}

function bucketKey(strength: number, skill: string): string {
  return `${strength}|${skill}`;
}

// "2+" sorts before "3+" (best to-hit first); non-numeric values ("N/A", "-") sort last rather
// than as 0/NaN, since they represent "can't be improved by BS/WS" rather than "best possible".
function skillSortRank(skill: string): number {
  const n = parseInt(skill, 10);
  return Number.isNaN(n) ? Number.MAX_SAFE_INTEGER : n;
}

// Total attacks (ranged shots or melee swings) a roster can put out, grouped by weapon Strength
// and split by to-hit value (BS for ranged, WS for melee) -- so "what do we wound with" (Strength)
// and "what do we hit on" (BS/WS) read as one stacked chart instead of two separate ones. Only
// counts units with a confirmed loadout (loadout.length > 0) -- a manually-added unit has no
// per-model weapon counts to work from (see the hasLoadout fallback-to-catalogue behavior in
// BattleTracker.tsx/RosterEditor.tsx), so there's nothing reliable to count. One profile per
// weapon name (the first match for the given range type) -- a multi-mode weapon (strike/sweep)
// would otherwise double-count the same physical model's attacks. Doesn't model range-dependent
// bonuses (Rapid Fire, etc.) -- this is baseline profile Attacks only, matching the app's
// "bookkeeping, not a rules engine" scope elsewhere.
export function weaponAttacksByStrengthAndSkill(
  units: UnitOut[],
  rangeType: "Ranged Weapons" | "Melee Weapons",
): StrengthSkillResult {
  const skillField = rangeType === "Ranged Weapons" ? "BS" : "WS";
  const totals = new Map<string, number>();
  const contributions = new Map<string, WeaponContribution[]>();
  const skillKeysSet = new Set<string>();
  const strengthsSet = new Set<number>();
  let skippedUnits = 0;

  for (const u of units) {
    if (u.loadout.length === 0) {
      skippedUnits += 1;
      continue;
    }
    for (const item of u.loadout) {
      for (const profile of loadoutProfiles(item.name, u.unit_definition.weapons, rangeType)) {
        const strength = Number(profile.characteristics.S);
        if (!Number.isFinite(strength)) continue;
        const skill = profile.characteristics[skillField]?.trim() || "N/A";
        const attacksPerModel = parseAttacks(profile.characteristics.A ?? "");
        const totalAttacks = attacksPerModel * item.count;

        const key = bucketKey(strength, skill);
        totals.set(key, (totals.get(key) ?? 0) + totalAttacks);
        skillKeysSet.add(skill);
        strengthsSet.add(strength);

        const list = contributions.get(key) ?? [];
        list.push({
          unitId: u.id,
          unitLabel: u.unit_definition.name,
          weaponName: profile.name,
          skill,
          count: item.count,
          attacksPerModel: Math.round(attacksPerModel * 10) / 10,
          totalAttacks: Math.round(totalAttacks * 10) / 10,
        });
        contributions.set(key, list);
      }
    }
  }

  const skillKeys = Array.from(skillKeysSet).sort((a, b) => skillSortRank(a) - skillSortRank(b));
  const strengths = Array.from(strengthsSet).sort((a, b) => a - b);

  const buckets = strengths.map((strength) => {
    const bucket: StrengthSkillBucket = { strength };
    for (const skill of skillKeys) {
      bucket[skill] = Math.round((totals.get(bucketKey(strength, skill)) ?? 0) * 10) / 10;
    }
    return bucket;
  });

  // For the swapped chart, Strength becomes the *stacked* dimension -- and unlike BS/WS (~5
  // categories), Strength is effectively unbounded (a roster can easily have 7+ distinct
  // values). Confirmed in practice this produces two real problems at once: a fixed categorical
  // palette collides (two different Strengths sharing a color once it cycles), and past ~5
  // values several segments become slivers too thin to read no matter the palette. Both are
  // solved the same way the dataviz skill prescribes for "too many categories": keep the
  // MAX_DISTINCT_STRENGTHS biggest contributors (by total attacks across all to-hit values) as
  // their own color, and fold everything else into one "Other" segment -- never more than
  // MAX_DISTINCT_STRENGTHS + 1 colors on screen regardless of how many Strength values exist.
  const MAX_DISTINCT_STRENGTHS = 5;
  const strengthTotals = new Map<number, number>();
  for (const strength of strengths) {
    let total = 0;
    for (const skill of skillKeys) total += totals.get(bucketKey(strength, skill)) ?? 0;
    strengthTotals.set(strength, total);
  }
  const topStrengths = [...strengths]
    .sort((a, b) => (strengthTotals.get(b) ?? 0) - (strengthTotals.get(a) ?? 0))
    .slice(0, MAX_DISTINCT_STRENGTHS)
    .sort((a, b) => a - b);
  const topStrengthsSet = new Set(topStrengths);
  const hasOtherStrengths = strengths.some((s) => !topStrengthsSet.has(s));
  const displayStrengths: (number | "Other")[] = hasOtherStrengths ? [...topStrengths, "Other"] : topStrengths;

  const bySkillBuckets = skillKeys.map((skill) => {
    const bucket: SkillStrengthBucket = { skill };
    for (const strength of topStrengths) {
      bucket[String(strength)] = Math.round((totals.get(bucketKey(strength, skill)) ?? 0) * 10) / 10;
    }
    if (hasOtherStrengths) {
      let other = 0;
      for (const strength of strengths) {
        if (!topStrengthsSet.has(strength)) other += totals.get(bucketKey(strength, skill)) ?? 0;
      }
      bucket.Other = Math.round(other * 10) / 10;
    }
    return bucket;
  });

  return {
    buckets,
    skillKeys,
    bySkillBuckets,
    strengthKeys: strengths,
    displayStrengths,
    skippedUnits,
    contributions,
  };
}

// Stats come as inconsistent free text across the indexed data ('6"', '10', '20+"', '-' for no
// value at all) -- pull out the leading number and ignore the rest. Returns null for "-".
export function parseLeadingInt(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "-") return null;
  const match = trimmed.match(/(\d+)/);
  return match ? Number(match[1]) : null;
}

// Counts unit *entries*, not physical models -- there's no reliable per-unit model count in
// this data (loadout counts are weapon totals, not a model census, and quantity is always 1
// on an imported unit), so a 10-model squad and a lone Character both count as one bar
// contribution. Caveat surfaced in the chart's own caption, not hidden.
function countUnitsByStat(units: UnitOut[], stat: "M" | "T" | "W"): [number, number][] {
  const totals = new Map<number, number>();
  for (const u of units) {
    const value = parseLeadingInt(u.unit_definition.stats[stat] ?? "");
    if (value === null) continue;
    totals.set(value, (totals.get(value) ?? 0) + 1);
  }
  return Array.from(totals).sort((a, b) => a[0] - b[0]);
}

export interface MovementBucket {
  movement: number;
  units: number;
}

export function unitsByMovement(units: UnitOut[]): MovementBucket[] {
  return countUnitsByStat(units, "M").map(([movement, count]) => ({ movement, units: count }));
}

export interface ToughnessBucket {
  toughness: number;
  units: number;
}

export function unitsByToughness(units: UnitOut[]): ToughnessBucket[] {
  return countUnitsByStat(units, "T").map(([toughness, count]) => ({ toughness, units: count }));
}

export interface WoundsBucket {
  wounds: number;
  units: number;
}

export function unitsByWounds(units: UnitOut[]): WoundsBucket[] {
  return countUnitsByStat(units, "W").map(([wounds, count]) => ({ wounds, units: count }));
}

// One contributing unit+weapon pair behind a single Strength/Damage bar on the Army Comparison
// charts -- same shape as WeaponContribution minus the to-hit `skill` field, which doesn't apply
// here (this is about raw wounding/killing potential, not accuracy).
export interface CharacteristicContribution {
  unitId: number;
  unitLabel: string;
  weaponName: string;
  count: number;
  attacksPerModel: number;
  totalAttacks: number;
}

interface CharacteristicTotals {
  totals: Map<number, number>;
  total: number;
  skippedUnits: number;
  contributions: Map<number, CharacteristicContribution[]>;
}

// Total attacks (ranged AND melee combined), grouped by weapon Strength or Damage -- ignores
// to-hit value and range type entirely, unlike weaponAttacksByStrengthAndSkill. This is "how much
// of this army's wounding/killing potential sits at each value", for comparing against an
// opposing army's Toughness/Wounds distribution (see strengthVsToughness/damageVsWounds below).
// Same loadout-only scope and "first matching profile per weapon name" simplification as
// weaponAttacksByStrengthAndSkill.
function attacksByCharacteristic(
  units: UnitOut[],
  characteristic: "S" | "D",
  rangeType?: "Ranged Weapons" | "Melee Weapons",
): CharacteristicTotals {
  const totals = new Map<number, number>();
  const contributions = new Map<number, CharacteristicContribution[]>();
  let total = 0;
  let skippedUnits = 0;

  for (const u of units) {
    if (u.loadout.length === 0) {
      skippedUnits += 1;
      continue;
    }
    for (const item of u.loadout) {
      for (const profile of loadoutProfiles(item.name, u.unit_definition.weapons, rangeType)) {
        const raw = profile.characteristics[characteristic];
        if (!raw) continue;
        // S is always a clean integer; D can be dice notation ("D6+2") like Attacks -- parseAttacks
        // averages either shape (a clean integer passes through its fallback unchanged), rounded to
        // the nearest whole value so it buckets onto the same integer axis as Wounds.
        const value = Math.round(parseAttacks(raw));
        const attacksPerModel = parseAttacks(profile.characteristics.A ?? "");
        const totalAttacks = attacksPerModel * item.count;

        totals.set(value, (totals.get(value) ?? 0) + totalAttacks);
        total += totalAttacks;

        const list = contributions.get(value) ?? [];
        list.push({
          unitId: u.id,
          unitLabel: u.unit_definition.name,
          weaponName: profile.name,
          count: item.count,
          attacksPerModel: Math.round(attacksPerModel * 10) / 10,
          totalAttacks: Math.round(totalAttacks * 10) / 10,
        });
        contributions.set(value, list);
      }
    }
  }

  return { totals, total, skippedUnits, contributions };
}

export interface OverlayBucket {
  value: number;
  armyAPct: number;
  armyBPct: number;
  armyARaw: number;
  armyBRaw: number;
}

function toOverlayBuckets(
  aTotals: Map<number, number>,
  aTotal: number,
  bTotals: Map<number, number>,
  bTotal: number,
): OverlayBucket[] {
  const values = new Set<number>([...aTotals.keys(), ...bTotals.keys()]);
  return Array.from(values)
    .sort((x, y) => x - y)
    .map((value) => {
      const armyARaw = Math.round((aTotals.get(value) ?? 0) * 10) / 10;
      const armyBRaw = bTotals.get(value) ?? 0;
      return {
        value,
        armyARaw,
        armyBRaw,
        armyAPct: aTotal > 0 ? Math.round((armyARaw / aTotal) * 1000) / 10 : 0,
        armyBPct: bTotal > 0 ? Math.round((armyBRaw / bTotal) * 1000) / 10 : 0,
      };
    });
}

function unitCountTotal(buckets: { units: number }[]): number {
  return buckets.reduce((sum, b) => sum + b.units, 0);
}

export interface OverlayResult {
  buckets: OverlayBucket[];
  skippedUnitsA: number;
  // Keyed by the same `value` as OverlayBucket -- army A's side of a clicked bar.
  contributionsA: Map<number, CharacteristicContribution[]>;
}

// Army A's total attack output grouped by weapon Strength, against army B's model-count
// distribution grouped by Toughness -- both expressed as % of their own army's total (attacks
// for A, unit entries for B) so two differently-scaled distributions read on one shared axis.
// `rangeType` optionally restricts army A's side to just Ranged or just Melee weapons (unset ==
// both combined); armyA/armyB should already be pre-filtered by unit type (role) by the caller,
// if that filter is in use -- this function doesn't know about roles.
export function strengthVsToughness(
  armyA: UnitOut[],
  armyB: UnitOut[],
  rangeType?: "Ranged Weapons" | "Melee Weapons",
): OverlayResult {
  const { totals: aTotals, total: aTotal, skippedUnits, contributions } = attacksByCharacteristic(
    armyA,
    "S",
    rangeType,
  );
  const toughnessBuckets = unitsByToughness(armyB);
  const bTotals = new Map(toughnessBuckets.map((b) => [b.toughness, b.units]));
  return {
    buckets: toOverlayBuckets(aTotals, aTotal, bTotals, unitCountTotal(toughnessBuckets)),
    skippedUnitsA: skippedUnits,
    contributionsA: contributions,
  };
}

// Same idea as strengthVsToughness, for weapon Damage against Wounds.
export function damageVsWounds(
  armyA: UnitOut[],
  armyB: UnitOut[],
  rangeType?: "Ranged Weapons" | "Melee Weapons",
): OverlayResult {
  const { totals: aTotals, total: aTotal, skippedUnits, contributions } = attacksByCharacteristic(
    armyA,
    "D",
    rangeType,
  );
  const woundsBuckets = unitsByWounds(armyB);
  const bTotals = new Map(woundsBuckets.map((b) => [b.wounds, b.units]));
  return {
    buckets: toOverlayBuckets(aTotals, aTotal, bTotals, unitCountTotal(woundsBuckets)),
    skippedUnitsA: skippedUnits,
    contributionsA: contributions,
  };
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
