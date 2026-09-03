import { type Dispatch, type SetStateAction, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { StatBoxes } from "../components/StatBoxes";
import type { Ability, DetectedEffect, SimulateOptions, SimulateResponse, UnitDefinition, Weapon } from "../types";
import { STAT_ORDER } from "../types";
import { groupWeaponsByRangeType } from "../weapons";

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

function UnitPicker({
  label,
  faction,
  onFaction,
  factions,
  unitDefs,
  unitId,
  onUnit,
}: {
  label: string;
  faction: string;
  onFaction: (f: string) => void;
  factions: string[];
  unitDefs: UnitDefinition[];
  unitId: string;
  onUnit: (id: string) => void;
}) {
  return (
    <div className="inline-form">
      <label className="checkbox-label">
        {label} faction
        <select value={faction} onChange={(e) => onFaction(e.target.value)}>
          <option value="">Select faction...</option>
          {factions.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </label>
      <label className="checkbox-label">
        {label} unit
        <select value={unitId} onChange={(e) => onUnit(e.target.value)} disabled={!faction}>
          <option value="">Select unit...</option>
          {unitDefs.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
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

export function Simulator() {
  const [factions, setFactions] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [includeNonStandard, setIncludeNonStandard] = useState(false);

  const [attackerFaction, setAttackerFaction] = useState("");
  const [attackerUnitDefs, setAttackerUnitDefs] = useState<UnitDefinition[]>([]);
  const [attackerUnitId, setAttackerUnitId] = useState("");
  // A mixed loadout: one row per distinct weapon (e.g. 4 Fusion guns + 1 Exarch gun).
  const [weaponLines, setWeaponLines] = useState<{ name: string; count: number }[]>([{ name: "", count: 1 }]);

  const [defenderFaction, setDefenderFaction] = useState("");
  const [defenderUnitDefs, setDefenderUnitDefs] = useState<UnitDefinition[]>([]);
  const [defenderUnitId, setDefenderUnitId] = useState("");
  const [defenderModelCount, setDefenderModelCount] = useState(1);

  const [options, setOptions] = useState<SimulateOptions>(DEFAULT_OPTIONS);

  // Ability-derived conditional buffs for each side, and which ones the player has ticked as live.
  const [attackerEffects, setAttackerEffects] = useState<DetectedEffect[]>([]);
  const [defenderEffects, setDefenderEffects] = useState<DetectedEffect[]>([]);
  const [checkedAttacker, setCheckedAttacker] = useState<Set<number>>(new Set());
  const [checkedDefender, setCheckedDefender] = useState<Set<number>>(new Set());

  const [result, setResult] = useState<SimulateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);

  useEffect(() => {
    api.listFactions().then(setFactions).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    setAttackerUnitId("");
    setWeaponLines([{ name: "", count: 1 }]);
    if (!attackerFaction) {
      setAttackerUnitDefs([]);
      return;
    }
    api.listUnitDefinitionsByFaction(attackerFaction).then(setAttackerUnitDefs).catch((e) => setError(String(e)));
  }, [attackerFaction]);

  useEffect(() => {
    setDefenderUnitId("");
    if (!defenderFaction) {
      setDefenderUnitDefs([]);
      return;
    }
    api.listUnitDefinitionsByFaction(defenderFaction).then(setDefenderUnitDefs).catch((e) => setError(String(e)));
  }, [defenderFaction]);

  const attackerUnit = attackerUnitDefs.find((u) => u.id === attackerUnitId) ?? null;
  const defenderUnit = defenderUnitDefs.find((u) => u.id === defenderUnitId) ?? null;
  // Resolve each loadout row to its catalogue weapon profile; drop rows with nothing selected.
  const validWeaponLines = weaponLines
    .map((line) => ({ weapon: attackerUnit?.weapons.find((w) => w.name === line.name) ?? null, count: line.count }))
    .filter((r): r is { weapon: Weapon; count: number } => r.weapon !== null);

  // What the dropdowns actually offer, filtered unless Legends/Crucible are opted in.
  const attackerOptions = includeNonStandard ? attackerUnitDefs : attackerUnitDefs.filter((u) => !isNonStandard(u));
  const defenderOptions = includeNonStandard ? defenderUnitDefs : defenderUnitDefs.filter((u) => !isNonStandard(u));

  useEffect(() => {
    setWeaponLines([{ name: "", count: 1 }]);
  }, [attackerUnitId]);

  // Pull attack modifiers out of the picked unit's abilities so they can be offered as toggles.
  useEffect(() => {
    setCheckedAttacker(new Set());
    if (!attackerUnit) {
      setAttackerEffects([]);
      return;
    }
    api
      .analyzeAbilities(attackerUnit.abilities)
      .then((r) => setAttackerEffects(r.effects.filter((e) => e.side === "attacker")))
      .catch((e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attackerUnitId]);

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

  const canSimulate = validWeaponLines.length > 0 && !!defenderUnit && Object.keys(defenderUnit.stats).length > 0;

  // Helpers to edit the loadout rows.
  function setLine(i: number, patch: Partial<{ name: string; count: number }>) {
    setWeaponLines((lines) => lines.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  }
  function addLine() {
    setWeaponLines((lines) => [...lines, { name: "", count: 1 }]);
  }
  function removeLine(i: number) {
    setWeaponLines((lines) => (lines.length > 1 ? lines.filter((_, j) => j !== i) : lines));
  }

  // The options actually sent. An effect is active when it's eligible for this matchup AND either
  // auto-applied (nothing for the player to decide) or ticked. Target-conditional attacker buffs
  // only count when the chosen defender qualifies -- so a buff drops automatically against a
  // target that doesn't have the required keyword.
  const defenderKeywords = defenderUnit?.keywords ?? [];
  const activePatches = [
    ...attackerEffects.filter((e, i) => effectApplies(e, defenderKeywords) && (isAutoApplied(e) || checkedAttacker.has(i))),
    ...defenderEffects.filter((e, i) => isAutoApplied(e) || checkedDefender.has(i)),
  ].map((e) => e.option_patch);
  const effectiveOptions = mergeEffects(options, activePatches);

  function toggleIn(setter: Dispatch<SetStateAction<Set<number>>>, i: number) {
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  async function handleSimulate() {
    if (validWeaponLines.length === 0 || !defenderUnit) return;
    setLoading(true);
    setSimError(null);
    setResult(null);
    try {
      const res = await api.simulate({
        weapons: validWeaponLines.map((r) => ({
          weapon_characteristics: r.weapon.characteristics,
          range_type: r.weapon.range_type,
          weapon_count: r.count,
        })),
        defender_stats: defenderUnit.stats,
        defender_model_count: defenderModelCount,
        options: effectiveOptions,
      });
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

  // Cumulative "destroyed by end of round N", for the rounds-to-kill chart.
  const roundsToKill = result
    ? Object.entries(result.destroyed_by_round)
        .map(([round, p]) => ({ round: Number(round), pct: Math.round(p * 1000) / 10 }))
        .sort((a, b) => a.round - b.round)
    : [];

  return (
    <div className="page">
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

      <details className="role-group" open>
        <summary className="role-group-header">
          <span>Attacker</span>
        </summary>
        <UnitPicker
          label="Attacker"
          faction={attackerFaction}
          onFaction={setAttackerFaction}
          factions={factions}
          unitDefs={attackerOptions}
          unitId={attackerUnitId}
          onUnit={setAttackerUnitId}
        />
        {attackerUnit && attackerUnit.weapons.length === 0 && <p className="muted">This unit has no weapons.</p>}
        {attackerUnit &&
          attackerUnit.weapons.length > 0 &&
          weaponLines.map((line, i) => (
            <div className="inline-form" key={i}>
              <label className="checkbox-label">
                Weapon
                <select value={line.name} onChange={(e) => setLine(i, { name: e.target.value })}>
                  <option value="">Select weapon...</option>
                  {groupWeaponsByRangeType(attackerUnit.weapons).map(([rangeType, ws]) => (
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
                <button type="button" onClick={() => removeLine(i)}>
                  Remove
                </button>
              )}
            </div>
          ))}
        {attackerUnit && attackerUnit.weapons.length > 0 && (
          <div className="inline-form">
            <button type="button" onClick={addLine}>
              + Add weapon
            </button>
          </div>
        )}
        <p className="muted">
          One row per distinct weapon — "Firing" is how many models carry that gun (e.g. 4 Fusion
          guns + 1 Exarch weapon = two rows). Each weapon's own A is the attacks per model. All rows
          fire at the same defender.
        </p>
        {attackerUnit && (
          <>
            <h4 className="weapon-section-heading">Ability buffs (auto-applied where certain; tick situational ones)</h4>
            <AbilityToggles
              effects={attackerEffects}
              checked={checkedAttacker}
              onToggle={(i) => toggleIn(setCheckedAttacker, i)}
              abilities={attackerUnit.abilities}
              defenderKeywords={defenderUnit?.keywords ?? []}
            />
          </>
        )}
      </details>

      <details className="role-group" open>
        <summary className="role-group-header">
          <span>Defender</span>
        </summary>
        <UnitPicker
          label="Defender"
          faction={defenderFaction}
          onFaction={setDefenderFaction}
          factions={factions}
          unitDefs={defenderOptions}
          unitId={defenderUnitId}
          onUnit={setDefenderUnitId}
        />
        {defenderUnit && Object.keys(defenderUnit.stats).length > 0 && (
          <div className="stat-line">
            <StatBoxes
              pairs={STAT_ORDER.filter((k) => defenderUnit.stats[k]).map((k) => ({ label: k, value: defenderUnit.stats[k] }))}
            />
          </div>
        )}
        {defenderUnit && (
          <div className="inline-form">
            <label className="checkbox-label">
              Model count
              <input
                type="number"
                min={1}
                value={defenderModelCount}
                onChange={(e) => setDefenderModelCount(Math.max(1, Number(e.target.value) || 1))}
                style={{ width: "4rem" }}
              />
            </label>
            {Object.keys(defenderUnit.stats).length === 0 && <span className="muted">This unit has no stats on file.</span>}
          </div>
        )}
        {defenderUnit && (
          <>
            <h4 className="weapon-section-heading">Defensive abilities (auto-applied where certain; tick situational ones)</h4>
            <AbilityToggles
              effects={defenderEffects}
              checked={checkedDefender}
              onToggle={(i) => toggleIn(setCheckedDefender, i)}
              abilities={defenderUnit.abilities}
            />
          </>
        )}
      </details>

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
          Feel No Pain isn't a stat in the unit data, so it isn't detected automatically — set it
          here if the defender has one (e.g. Angron has FNP 5+).
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
