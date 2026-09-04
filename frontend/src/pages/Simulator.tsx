import { type Dispatch, type SetStateAction, useEffect, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { StatBoxes } from "../components/StatBoxes";
import type { Ability, DetectedEffect, ModelProfile, SimulateOptions, SimulateResponse, UnitDefinition, Weapon } from "../types";
import { STAT_ORDER } from "../types";
import { groupWeaponsByRangeType } from "../weapons";

type WeaponLineInput = { name: string; count: number };

// Model-profile name fragments that mark a single "leader" model (one per unit) carrying its own
// distinct weapon -- so it gets a count of 1 while the rest of the squad forms the bulk line.
const LEADER_TERMS = ["exarch", "sergeant", "champion", "superior", "aspiring", "leader", "princeps"];

function isLeaderModel(name: string): boolean {
  const n = name.toLowerCase();
  return LEADER_TERMS.some((t) => n.includes(t));
}

function primaryWeaponName(mp: ModelProfile): string {
  const w = mp.ranged_weapons[0] ?? mp.melee_weapons[0];
  return w ? w.name : "";
}

// Best-effort default loadout for a freshly-picked unit: one row per model type (each defaulting to
// its first weapon), a leader model counted as 1, and the remaining squad size (min_models minus
// leaders) assigned to the single bulk model type. Falls back to one blank row when there's no
// per-model data to work from. Everything stays editable afterwards.
function autoPopulateLines(unit: UnitDefinition): WeaponLineInput[] {
  const profiles = unit.model_profiles ?? [];
  if (profiles.length === 0) return [{ name: "", count: 1 }];

  const leaders = profiles.filter((p) => isLeaderModel(p.name));
  const bulk = profiles.filter((p) => !isLeaderModel(p.name));
  const size = unit.min_models || 0;
  const lines: WeaponLineInput[] = [];

  for (const p of bulk) {
    const name = primaryWeaponName(p);
    // If there's a single bulk model type and we know the squad size, it takes the remainder.
    const count = bulk.length === 1 && size > 0 ? Math.max(1, size - leaders.length) : 1;
    if (name) lines.push({ name, count });
  }
  for (const p of leaders) {
    const name = primaryWeaponName(p);
    if (name) lines.push({ name, count: 1 });
  }
  return lines.length > 0 ? lines : [{ name: "", count: 1 }];
}

const REROLL_RANK: Record<string, number> = { none: 0, ones: 1, all: 2 };

// Folds each toggled-on ability effect's option_patch into the base options: hit/wound
// modifiers add (the backend still clamps to +/-1), re-rolls take the stronger policy, and
// FNP takes the best (lowest) value. Mirrors how these stack at the table.
function mergeEffects(base: SimulateOptions, patches: Partial<SimulateOptions>[]): SimulateOptions {
  const o: SimulateOptions = { ...base };
  for (const p of patches) {
    if (p.hit_modifier) o.hit_modifier += p.hit_modifier;
    if (p.wound_modifier) o.wound_modifier += p.wound_modifier;
    if (p.reroll_hits && REROLL_RANK[p.reroll_hits] > REROLL_RANK[o.reroll_hits]) o.reroll_hits = p.reroll_hits;
    if (p.reroll_wounds && REROLL_RANK[p.reroll_wounds] > REROLL_RANK[o.reroll_wounds]) o.reroll_wounds = p.reroll_wounds;
    if (p.single_reroll_hit) o.single_reroll_hit = true;
    if (p.single_reroll_wound) o.single_reroll_wound = true;
    if (p.reroll_damage) o.reroll_damage = true;
    if (p.fnp != null) o.fnp = o.fnp == null ? p.fnp : Math.min(o.fnp, p.fnp);
  }
  o.hit_modifier = Math.max(-1, Math.min(1, o.hit_modifier));
  o.wound_modifier = Math.max(-1, Math.min(1, o.wound_modifier));
  return o;
}

// Whether a target-conditional effect applies to the chosen defender: an effect with
// requires_target_keywords only applies if the defender has one of those keywords. Effects with
// no requirement always apply.
function effectApplies(e: DetectedEffect, defenderKeywords: string[]): boolean {
  if (!e.requires_target_keywords || e.requires_target_keywords.length === 0) return true;
  const have = defenderKeywords.map((k) => k.toLowerCase());
  return e.requires_target_keywords.some((req) => have.includes(req.toLowerCase()));
}

// An effect the app can fully verify is applied automatically (no click): one with no free-text
// positional condition -- i.e. unconditional, or gated only on the target's keywords (which the
// app checks via effectApplies). A "While within 12\" of..." style condition stays manual because
// only the player knows the board state.
function isAutoApplied(e: DetectedEffect): boolean {
  return e.condition === "";
}

// The detected ability toggles for one side, plus a muted list of that unit's other abilities
// that weren't auto-modelled -- so nothing is hidden and the player can fall back to the manual
// controls for anything the heuristic missed.
function AbilityToggles({
  effects,
  checked,
  onToggle,
  abilities,
  defenderKeywords = [],
}: {
  effects: DetectedEffect[];
  checked: Set<number>;
  onToggle: (i: number) => void;
  abilities: Ability[];
  defenderKeywords?: string[];
}) {
  const detectedNames = new Set(effects.map((e) => e.ability_name));
  const others = abilities.filter((a) => !detectedNames.has(a.name));
  return (
    <div>
      {effects.length > 0 ? (
        effects.map((e, i) => {
          // A target-conditional effect is disabled unless the chosen defender qualifies.
          const applies = effectApplies(e, defenderKeywords);
          // Auto-applied effects (no positional condition) are on whenever eligible and can't be
          // unticked -- they're a fact of the matchup, not a player choice. Positional ones toggle.
          const auto = isAutoApplied(e);
          const isChecked = applies && (auto || checked.has(i));
          return (
            <label
              key={`${e.ability_name}-${e.summary}`}
              className="checkbox-label"
              style={{ display: "block", opacity: applies ? 1 : 0.45 }}
            >
              <input type="checkbox" checked={isChecked} disabled={auto || !applies} onChange={() => onToggle(i)} />
              <strong>{e.summary}</strong> — {e.ability_name}
              {auto && applies && <span className="muted"> (auto)</span>}
              {e.condition && <span className="muted"> ({e.condition})</span>}
              {e.requires_target_keywords.length > 0 && (
                <span className="muted">
                  {" "}
                  [only vs {e.requires_target_keywords.join(" / ")}
                  {applies ? "" : " — this defender doesn't qualify"}]
                </span>
              )}
            </label>
          );
        })
      ) : (
        <p className="muted">No attack modifiers auto-detected from this unit's abilities.</p>
      )}
      {others.length > 0 && (
        <p className="muted" style={{ marginTop: "0.4rem" }}>
          Not auto-modelled (use the manual options if relevant): {others.map((a) => a.name).join(", ")}
        </p>
      )}
    </div>
  );
}

const CHART_COLOR = "#e0574a";
const BAR_SIZE = 24;
const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];

const DEFAULT_OPTIONS: SimulateOptions = {
  half_range: false,
  charged: false,
  cover: false,
  hit_modifier: 0,
  wound_modifier: 0,
  reroll_hits: "none",
  reroll_wounds: "none",
  single_reroll_hit: false,
  single_reroll_wound: false,
  reroll_damage: false,
  fnp: null,
  anti_active: false,
  anti_threshold: null,
  trials: 10000,
  seed: null,
};

// One-line summary for a weapon <option> -- <option> can't render StatBoxes, so this is a plain
// string. Skill characteristic is "BS" for ranged weapons, "WS" for melee.
function weaponSummary(w: Weapon): string {
  const c = w.characteristics;
  const skillKey = w.range_type === "Melee Weapons" ? "WS" : "BS";
  const parts: string[] = [];
  if (c.A) parts.push(`A${c.A}`);
  if (c[skillKey]) parts.push(`${skillKey}${c[skillKey]}`);
  if (c.S) parts.push(`S${c.S}`);
  if (c.AP) parts.push(`AP${c.AP}`);
  if (c.D) parts.push(`D${c.D}`);
  return parts.join(" ");
}

// Legends and Crucible (custom-character) units aren't part of a standard matched-play list, so
// they're hidden from the pickers unless explicitly included. Crucible units carry a "Crucible"
// keyword and a "[Crucible]" name suffix; Legends units carry the is_legends flag.
function isNonStandard(u: UnitDefinition): boolean {
  return (
    u.is_legends ||
    u.name.includes("[Crucible]") ||
    u.keywords.some((k) => k.toLowerCase() === "crucible")
  );
}

function toggleSet(setter: Dispatch<SetStateAction<Set<number>>>, i: number) {
  setter((prev) => {
    const next = new Set(prev);
    if (next.has(i)) next.delete(i);
    else next.add(i);
    return next;
  });
}

// What one attacking unit contributes to the combined volley: its resolved weapon lines and the
// option patches from its own (auto/ticked, target-eligible) ability buffs.
interface AttackerContribution {
  label: string;
  weapons: import("../types").SimulateWeaponLine[];
  effectPatches: Partial<SimulateOptions>[];
}

// One attacking unit: faction/unit picker, auto-populated loadout, and its ability buffs. Self-
// contained state; reports its contribution up so several units can fire into one defender.
function AttackerUnit({
  index,
  factions,
  includeNonStandard,
  defenderKeywords,
  onContribution,
  onRemove,
  canRemove,
  onError,
}: {
  index: number;
  factions: string[];
  includeNonStandard: boolean;
  defenderKeywords: string[];
  onContribution: (c: AttackerContribution) => void;
  onRemove: () => void;
  canRemove: boolean;
  onError: (msg: string) => void;
}) {
  const [faction, setFaction] = useState("");
  const [unitDefs, setUnitDefs] = useState<UnitDefinition[]>([]);
  const [unitId, setUnitId] = useState("");
  const [weaponLines, setWeaponLines] = useState<WeaponLineInput[]>([{ name: "", count: 1 }]);
  const [effects, setEffects] = useState<DetectedEffect[]>([]);
  const [checked, setChecked] = useState<Set<number>>(new Set());

  useEffect(() => {
    setUnitId("");
    if (!faction) {
      setUnitDefs([]);
      return;
    }
    api.listUnitDefinitionsByFaction(faction).then(setUnitDefs).catch((e) => onError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [faction]);

  const unit = unitDefs.find((u) => u.id === unitId) ?? null;
  const unitOptions = includeNonStandard ? unitDefs : unitDefs.filter((u) => !isNonStandard(u));

  useEffect(() => {
    const u = unitDefs.find((x) => x.id === unitId);
    setWeaponLines(u ? autoPopulateLines(u) : [{ name: "", count: 1 }]);
    setChecked(new Set());
    if (!u) {
      setEffects([]);
      return;
    }
    api
      .analyzeAbilities(u.abilities)
      .then((r) => setEffects(r.effects.filter((e) => e.side === "attacker")))
      .catch((e) => onError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unitId]);

  const validWeaponLines = weaponLines
    .map((line) => ({ weapon: unit?.weapons.find((w) => w.name === line.name) ?? null, count: line.count }))
    .filter((r): r is { weapon: Weapon; count: number } => r.weapon !== null);

  // Report this unit's contribution whenever its inputs (or the defender it's gated against) change.
  useEffect(() => {
    const patches = effects
      .filter((e, i) => effectApplies(e, defenderKeywords) && (isAutoApplied(e) || checked.has(i)))
      .map((e) => e.option_patch);
    onContribution({
      label: unit?.name ?? `Unit ${index + 1}`,
      weapons: validWeaponLines.map((r) => ({
        weapon_characteristics: r.weapon.characteristics,
        range_type: r.weapon.range_type,
        weapon_count: r.count,
      })),
      effectPatches: patches,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unitId, weaponLines, effects, checked, defenderKeywords]);

  function setLine(i: number, patch: Partial<WeaponLineInput>) {
    setWeaponLines((lines) => lines.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  }

  return (
    <div className="sim-unit-card">
      <div className="sim-unit-picker">
        <label>
          Faction
          <select value={faction} onChange={(e) => setFaction(e.target.value)}>
            <option value="">Select faction...</option>
            {factions.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </label>
        <label>
          Unit
          <select value={unitId} onChange={(e) => setUnitId(e.target.value)} disabled={!faction}>
            <option value="">Select unit...</option>
            {unitOptions.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        </label>
        {canRemove && (
          <button type="button" onClick={onRemove}>
            Remove unit
          </button>
        )}
      </div>
      <div className="sim-unit-body">
        <p className="sim-unit-title">Attacker {index + 1}{unit ? `: ${unit.name}` : ""}</p>
        {unit && unit.weapons.length === 0 && <p className="muted">This unit has no weapons.</p>}
      {unit &&
        unit.weapons.length > 0 &&
        weaponLines.map((line, i) => (
          <div className="inline-form" key={i}>
            <label className="checkbox-label">
              Weapon
              <select value={line.name} onChange={(e) => setLine(i, { name: e.target.value })}>
                <option value="">Select weapon...</option>
                {groupWeaponsByRangeType(unit.weapons).map(([rangeType, ws]) => (
                  <optgroup key={rangeType} label={rangeType}>
                    {ws.map((w) => (
                      <option key={w.name} value={w.name}>
                        {w.name} — {weaponSummary(w)}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>
            <label className="checkbox-label">
              Firing
              <input
                type="number"
                min={1}
                value={line.count}
                onChange={(e) => setLine(i, { count: Math.max(1, Number(e.target.value) || 1) })}
                style={{ width: "4rem" }}
              />
            </label>
            {weaponLines.length > 1 && (
              <button type="button" onClick={() => setWeaponLines((lines) => lines.filter((_, j) => j !== i))}>
                Remove
              </button>
            )}
          </div>
        ))}
      {unit && unit.weapons.length > 0 && (
        <div className="inline-form">
          <button type="button" onClick={() => setWeaponLines((lines) => [...lines, { name: "", count: 1 }])}>
            + Add weapon
          </button>
        </div>
      )}
        {unit && (
          <>
            <h4 className="weapon-section-heading">Ability buffs (auto-applied where certain; tick situational ones)</h4>
            <AbilityToggles
              effects={effects}
              checked={checked}
              onToggle={(i) => toggleSet(setChecked, i)}
              abilities={unit.abilities}
              defenderKeywords={defenderKeywords}
            />
          </>
        )}
      </div>
    </div>
  );
}

export function Simulator() {
  const [factions, setFactions] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [includeNonStandard, setIncludeNonStandard] = useState(false);

  // --- Attacking units: one or more, each firing into the same defender ---
  const [attackerIds, setAttackerIds] = useState<number[]>([0]);
  const nextIdRef = useRef(1);
  const [contributions, setContributions] = useState<Record<number, AttackerContribution>>({});

  const [defenderFaction, setDefenderFaction] = useState("");
  const [defenderUnitDefs, setDefenderUnitDefs] = useState<UnitDefinition[]>([]);
  const [defenderUnitId, setDefenderUnitId] = useState("");
  const [defenderModelCount, setDefenderModelCount] = useState(1);

  const [options, setOptions] = useState<SimulateOptions>(DEFAULT_OPTIONS);

  const [defenderEffects, setDefenderEffects] = useState<DetectedEffect[]>([]);
  const [checkedDefender, setCheckedDefender] = useState<Set<number>>(new Set());

  const [result, setResult] = useState<SimulateResponse | null>(null);
  const [resultLabels, setResultLabels] = useState<string[]>([]); // unit names for the last run's per-unit breakdown
  const [loading, setLoading] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);

  useEffect(() => {
    api.listFactions().then(setFactions).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    setDefenderUnitId("");
    if (!defenderFaction) {
      setDefenderUnitDefs([]);
      return;
    }
    api.listUnitDefinitionsByFaction(defenderFaction).then(setDefenderUnitDefs).catch((e) => setError(String(e)));
  }, [defenderFaction]);

  const defenderUnit = defenderUnitDefs.find((u) => u.id === defenderUnitId) ?? null;
  const defenderOptions = includeNonStandard ? defenderUnitDefs : defenderUnitDefs.filter((u) => !isNonStandard(u));
  const defenderKeywords = defenderUnit?.keywords ?? [];

  useEffect(() => {
    setCheckedDefender(new Set());
    if (!defenderUnit) {
      setDefenderEffects([]);
      return;
    }
    api
      .analyzeAbilities(defenderUnit.abilities)
      .then((r) => setDefenderEffects(r.effects.filter((e) => e.side === "defender")))
      .catch((e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defenderUnitId]);

  function handleContribution(id: number, c: AttackerContribution) {
    setContributions((prev) => ({ ...prev, [id]: c }));
  }
  function addUnit() {
    const id = nextIdRef.current++;
    setAttackerIds((ids) => [...ids, id]);
  }
  function removeUnit(id: number) {
    setAttackerIds((ids) => ids.filter((x) => x !== id));
    setContributions((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }

  // Defender-side ability patches (FNP etc.) apply to every incoming attack.
  const defenderPatches = defenderEffects
    .filter((e, i) => isAutoApplied(e) || checkedDefender.has(i))
    .map((e) => e.option_patch);

  // Each attacking unit's final options = shared manual options + defender-side patches + that
  // unit's OWN ability patches, so one unit's re-roll aura never leaks onto another.
  const attackerContribs = attackerIds
    .map((id) => contributions[id])
    .filter((c): c is AttackerContribution => !!c && c.weapons.length > 0);
  const attackerGroups = attackerContribs.map((c) => ({
    weapons: c.weapons,
    options: mergeEffects(options, [...c.effectPatches, ...defenderPatches]),
  }));

  const canSimulate = attackerGroups.length > 0 && !!defenderUnit && Object.keys(defenderUnit.stats).length > 0;

  async function handleSimulate() {
    if (attackerGroups.length === 0 || !defenderUnit) return;
    setLoading(true);
    setSimError(null);
    setResult(null);
    try {
      const res = await api.simulate({
        attackers: attackerGroups,
        defender_stats: defenderUnit.stats,
        defender_model_count: defenderModelCount,
      });
      setResultLabels(attackerContribs.map((c) => c.label));
      setResult(res);
    } catch (e) {
      setSimError(String(e));
    } finally {
      setLoading(false);
    }
  }

  const damageHistogram = result
    ? Object.entries(result.damage_histogram)
        .map(([wounds, count]) => ({ wounds: Number(wounds), count }))
        .sort((a, b) => a.wounds - b.wounds)
    : [];

  const histogram = result
    ? Object.entries(result.models_slain_histogram)
        .map(([slain, count]) => ({ slain: Number(slain), count }))
        .sort((a, b) => a.slain - b.slain)
    : [];

  const percentiles = result
    ? Object.entries(result.damage_percentiles).sort((a, b) => Number(a[0]) - Number(b[0]))
    : [];

  // "Chance of dealing >= X wounds in one round" at quarter/half/etc of the target's pool.
  const thresholds = result
    ? Object.entries(result.damage_at_least)
        .map(([wounds, p]) => ({ wounds: Number(wounds), pct: p * 100 }))
        .sort((a, b) => a.wounds - b.wounds)
    : [];

  // Per-unit mean wounds, for the contribution bar chart.
  const perUnitData = result
    ? result.per_unit.map((u, i) => ({
        unit: resultLabels[i] ?? `Unit ${i + 1}`,
        wounds: Math.round(u.mean_damage * 100) / 100,
      }))
    : [];

  // Cumulative "destroyed by end of round N", for the rounds-to-kill chart.
  const roundsToKill = result
    ? Object.entries(result.destroyed_by_round)
        .map(([round, p]) => ({ round: Number(round), pct: Math.round(p * 1000) / 10 }))
        .sort((a, b) => a.round - b.round)
    : [];

  return (
    <div className="page sim-page">
      <h1>Dice Simulator</h1>
      <p className="muted">
        Pick an attacking weapon and a defending unit, run a batch of simulated trials, and
        spot-check the resulting damage/kill numbers.
      </p>
      {error && <p className="error">{error}</p>}

      <div className="inline-form">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={includeNonStandard}
            onChange={(e) => setIncludeNonStandard(e.target.checked)}
          />
          Include Legends &amp; Crucible units
        </label>
      </div>

      <div className="sim-units-box">
        <div className="sim-units-box-header">
          <span>Attacking units</span>
          <button type="button" onClick={addUnit}>
            + Add unit
          </button>
        </div>
        {attackerIds.map((id, i) => (
          <AttackerUnit
            key={id}
            index={i}
            factions={factions}
            includeNonStandard={includeNonStandard}
            defenderKeywords={defenderKeywords}
            onContribution={(c) => handleContribution(id, c)}
            onRemove={() => removeUnit(id)}
            canRemove={attackerIds.length > 1}
            onError={setError}
          />
        ))}
      </div>
      <p className="muted">
        Add a unit per firing unit (e.g. Fire Dragons + a Fire Prism into the same target). Each
        unit auto-fills its loadout (bulk gun + a differently-armed leader) and applies its own
        abilities; the shared Options below cover the whole attack.
      </p>

      <div className="sim-units-box">
        <div className="sim-units-box-header">
          <span>Defender</span>
        </div>
        <div className="sim-unit-card">
          <div className="sim-unit-picker">
            <label>
              Faction
              <select value={defenderFaction} onChange={(e) => setDefenderFaction(e.target.value)}>
                <option value="">Select faction...</option>
                {factions.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Unit
              <select value={defenderUnitId} onChange={(e) => setDefenderUnitId(e.target.value)} disabled={!defenderFaction}>
                <option value="">Select unit...</option>
                {defenderOptions.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Model count
              <input
                type="number"
                min={1}
                value={defenderModelCount}
                onChange={(e) => setDefenderModelCount(Math.max(1, Number(e.target.value) || 1))}
              />
            </label>
          </div>
          <div className="sim-unit-body">
            {defenderUnit && <p className="sim-unit-title">{defenderUnit.name}</p>}
            {defenderUnit && Object.keys(defenderUnit.stats).length > 0 && (
              <div className="stat-line">
                <StatBoxes
                  pairs={STAT_ORDER.filter((k) => defenderUnit.stats[k]).map((k) => ({ label: k, value: defenderUnit.stats[k] }))}
                />
              </div>
            )}
            {defenderUnit && Object.keys(defenderUnit.stats).length === 0 && (
              <p className="muted">This unit has no stats on file.</p>
            )}
            {defenderUnit && (
              <>
                <h4 className="weapon-section-heading">Defensive abilities (auto-applied where certain; tick situational ones)</h4>
                <AbilityToggles
                  effects={defenderEffects}
                  checked={checkedDefender}
                  onToggle={(i) => toggleSet(setCheckedDefender, i)}
                  abilities={defenderUnit.abilities}
                />
              </>
            )}
          </div>
        </div>
      </div>

      <details className="role-group" open>
        <summary className="role-group-header">
          <span>Options</span>
        </summary>
        <div className="inline-form">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={options.cover}
              onChange={(e) => setOptions((o) => ({ ...o, cover: e.target.checked }))}
            />
            Cover
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={options.half_range}
              onChange={(e) => setOptions((o) => ({ ...o, half_range: e.target.checked }))}
            />
            Within half range (Rapid Fire/Melta)
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={options.charged}
              onChange={(e) => setOptions((o) => ({ ...o, charged: e.target.checked }))}
            />
            Charged this turn (Lance)
          </label>
        </div>
        <div className="inline-form">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={options.reroll_hits === "all"}
              onChange={(e) => setOptions((o) => ({ ...o, reroll_hits: e.target.checked ? "all" : "none" }))}
            />
            Re-roll failed Hits
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={options.reroll_wounds === "all"}
              onChange={(e) => setOptions((o) => ({ ...o, reroll_wounds: e.target.checked ? "all" : "none" }))}
            />
            Re-roll failed Wounds
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={options.reroll_damage}
              onChange={(e) => setOptions((o) => ({ ...o, reroll_damage: e.target.checked }))}
            />
            Re-roll Damage (low rolls)
          </label>
        </div>
        <div className="inline-form">
          <label className="checkbox-label">
            Hit modifier
            <input
              type="number"
              min={-1}
              max={1}
              value={options.hit_modifier}
              onChange={(e) => setOptions((o) => ({ ...o, hit_modifier: Number(e.target.value) }))}
              style={{ width: "3.5rem" }}
            />
          </label>
          <label className="checkbox-label">
            Wound modifier
            <input
              type="number"
              min={-1}
              max={1}
              value={options.wound_modifier}
              onChange={(e) => setOptions((o) => ({ ...o, wound_modifier: Number(e.target.value) }))}
              style={{ width: "3.5rem" }}
            />
          </label>
          <label className="checkbox-label">
            Defender Feel No Pain
            <select
              value={options.fnp ?? ""}
              onChange={(e) => setOptions((o) => ({ ...o, fnp: e.target.value ? Number(e.target.value) : null }))}
            >
              <option value="">None</option>
              <option value="6">6+</option>
              <option value="5">5+</option>
              <option value="4">4+</option>
              <option value="3">3+</option>
            </select>
          </label>
          <label className="checkbox-label">
            Trials
            <input
              type="number"
              min={100}
              step={100}
              value={options.trials}
              onChange={(e) => setOptions((o) => ({ ...o, trials: Number(e.target.value) || DEFAULT_OPTIONS.trials }))}
              style={{ width: "5.5rem" }}
            />
          </label>
        </div>
        <p className="muted">
          Feel No Pain isn't a stat in the unit data, so it isn't auto-detected from a bare stat
          line — set it here if the defender has one (a detected "Feel No Pain X+" ability toggle
          will also apply it).
        </p>
      </details>

      <div className="inline-form">
        <button type="button" className="primary" onClick={handleSimulate} disabled={!canSimulate || loading}>
          {loading ? "Simulating..." : "Simulate"}
        </button>
      </div>
      {simError && <p className="error">{simError}</p>}

      {result && (
        <details className="role-group" open>
          <summary className="role-group-header">
            <span>Results ({result.trials} trials)</span>
          </summary>
          <div className="stat-line">
            <StatBoxes
              pairs={[
                { label: "Mean Dmg", value: result.mean_damage.toFixed(2) },
                { label: "Median Dmg", value: result.median_damage.toFixed(2) },
                { label: "Mean Slain", value: result.mean_models_slain.toFixed(2) },
                { label: "P(≥1 kill)", value: `${(result.p_at_least_one_kill * 100).toFixed(1)}%` },
                { label: "P(wipe)", value: `${(result.p_wipe * 100).toFixed(1)}%` },
              ]}
            />
          </div>
          {percentiles.length > 0 && (
            <div className="stat-line">
              <StatBoxes pairs={percentiles.map(([p, v]) => ({ label: `p${p}`, value: v.toFixed(1) }))} />
            </div>
          )}

          {(result.per_unit?.length ?? 0) > 1 && (
            <>
              <h4 className="weapon-section-heading">Per-unit contribution (mean wounds this round)</h4>
              <div className="chart-container">
                <ResponsiveContainer width="100%" height={60 + perUnitData.length * 42}>
                  <BarChart data={perUnitData} layout="vertical" margin={{ left: 10, right: 40 }}>
                    <CartesianGrid strokeDasharray="" stroke="#333747" horizontal={false} />
                    <XAxis type="number" stroke="#8b8f9e" />
                    <YAxis type="category" dataKey="unit" width={140} stroke="#8b8f9e" />
                    <Tooltip
                      contentStyle={{ background: "#1e212b", border: "1px solid #333747" }}
                      formatter={(value) => [`${value} wounds`, "Mean"]}
                    />
                    <Bar dataKey="wounds" name="Mean wounds" fill={CHART_COLOR} radius={[0, 4, 4, 0]} maxBarSize={28}>
                      <LabelList dataKey="wounds" position="right" fill="#c8ccd6" />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="muted">
                How much of the combined damage each unit actually deals, in firing order (so they
                sum to the mean total). A later unit gets less credit when an earlier one has already
                over-killed the target.
              </p>
            </>
          )}

          <h4 className="weapon-section-heading">Kill summary — {result.total_wounds} wounds to destroy</h4>
          <div className="stat-line">
            <StatBoxes
              pairs={[
                { label: "Target wounds", value: String(result.total_wounds) },
                { label: "Mean/round", value: result.mean_damage.toFixed(2) },
                {
                  label: "Median rounds to kill",
                  value: result.median_rounds_to_destroy != null ? String(result.median_rounds_to_destroy) : `>${roundsToKill.length}`,
                },
              ]}
            />
          </div>

          <p className="muted">Chance of dealing at least this many wounds in a single round:</p>
          <div className="stat-line">
            <StatBoxes
              pairs={thresholds.map((t) => ({
                label: `≥ ${t.wounds}${t.wounds >= result.total_wounds ? " (one-shot)" : ""}`,
                value: `${t.pct.toFixed(1)}%`,
              }))}
            />
          </div>

          <h4 className="weapon-section-heading">Wounds Dealt Distribution</h4>
          {damageHistogram.length > 0 ? (
            <div className="chart-container">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={damageHistogram}>
                  <CartesianGrid strokeDasharray="" stroke="#333747" vertical={false} />
                  <XAxis dataKey="wounds" stroke="#8b8f9e" label={{ value: "Wounds dealt", position: "insideBottom", offset: -2 }} />
                  <YAxis allowDecimals={false} stroke="#8b8f9e" />
                  <Tooltip
                    contentStyle={{ background: "#1e212b", border: "1px solid #333747" }}
                    labelFormatter={(v) => `${v} wounds`}
                    formatter={(value) => [`${value} trials`, "Count"]}
                  />
                  <Bar dataKey="count" name="Trials" fill={CHART_COLOR} radius={BAR_RADIUS} maxBarSize={BAR_SIZE} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="muted">No histogram data.</p>
          )}

          <h4 className="weapon-section-heading">Chance destroyed by end of round N (5-round game)</h4>
          <p className="muted">
            Damage carries between rounds (wounds don't heal). Read your confidence level off this —
            a target still standing at round 5 is one you can't reliably kill within a game.
          </p>
          {roundsToKill.length > 0 ? (
            <div className="chart-container">
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={roundsToKill}>
                  <CartesianGrid strokeDasharray="" stroke="#333747" vertical={false} />
                  <XAxis dataKey="round" stroke="#8b8f9e" label={{ value: "Round", position: "insideBottom", offset: -2 }} />
                  <YAxis domain={[0, 100]} stroke="#8b8f9e" unit="%" />
                  <Tooltip
                    contentStyle={{ background: "#1e212b", border: "1px solid #333747" }}
                    labelFormatter={(v) => `By round ${v}`}
                    formatter={(value) => [`${value}%`, "Destroyed"]}
                  />
                  <Bar dataKey="pct" name="Destroyed %" fill={CHART_COLOR} radius={BAR_RADIUS} maxBarSize={BAR_SIZE} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="muted">No rounds data.</p>
          )}

          <h4 className="weapon-section-heading">Models Slain Distribution</h4>
          <p className="muted">
            For a big multi-wound target (e.g. a 16-wound Angron) this stays near zero even when
            you're dealing real damage — the wounds chart above is the meaningful readout there.
          </p>
          {histogram.length > 0 ? (
            <div className="chart-container">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={histogram}>
                  <CartesianGrid strokeDasharray="" stroke="#333747" vertical={false} />
                  <XAxis dataKey="slain" stroke="#8b8f9e" label={{ value: "Models slain", position: "insideBottom", offset: -2 }} />
                  <YAxis allowDecimals={false} stroke="#8b8f9e" />
                  <Tooltip
                    contentStyle={{ background: "#1e212b", border: "1px solid #333747" }}
                    labelFormatter={(v) => `${v} slain`}
                    formatter={(value) => [`${value} trials`, "Count"]}
                  />
                  <Bar dataKey="count" name="Trials" fill={CHART_COLOR} radius={BAR_RADIUS} maxBarSize={BAR_SIZE} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="muted">No histogram data.</p>
          )}
        </details>
      )}
    </div>
  );
}
