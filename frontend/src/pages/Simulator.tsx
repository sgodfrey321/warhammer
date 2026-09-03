import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { StatBoxes } from "../components/StatBoxes";
import type { SimulateOptions, SimulateResponse, UnitDefinition, Weapon } from "../types";
import { groupWeaponsByRangeType } from "../weapons";

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

export function Simulator() {
  const [factions, setFactions] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [attackerFaction, setAttackerFaction] = useState("");
  const [attackerUnitDefs, setAttackerUnitDefs] = useState<UnitDefinition[]>([]);
  const [attackerUnitId, setAttackerUnitId] = useState("");
  const [weaponName, setWeaponName] = useState("");
  const [weaponCount, setWeaponCount] = useState(1);

  const [defenderFaction, setDefenderFaction] = useState("");
  const [defenderUnitDefs, setDefenderUnitDefs] = useState<UnitDefinition[]>([]);
  const [defenderUnitId, setDefenderUnitId] = useState("");
  const [defenderModelCount, setDefenderModelCount] = useState(1);

  const [options, setOptions] = useState<SimulateOptions>(DEFAULT_OPTIONS);

  const [result, setResult] = useState<SimulateResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);

  useEffect(() => {
    api.listFactions().then(setFactions).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    setAttackerUnitId("");
    setWeaponName("");
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
  const weapon = attackerUnit?.weapons.find((w) => w.name === weaponName) ?? null;

  useEffect(() => {
    setWeaponName("");
  }, [attackerUnitId]);

  const canSimulate = !!weapon && !!defenderUnit && Object.keys(defenderUnit.stats).length > 0;

  async function handleSimulate() {
    if (!weapon || !defenderUnit) return;
    setLoading(true);
    setSimError(null);
    setResult(null);
    try {
      const res = await api.simulate({
        weapon_characteristics: weapon.characteristics,
        range_type: weapon.range_type,
        defender_stats: defenderUnit.stats,
        defender_model_count: defenderModelCount,
        weapon_count: weaponCount,
        options,
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

  return (
    <div className="page">
      <h1>Dice Simulator</h1>
      <p className="muted">
        Pick an attacking weapon and a defending unit, run a batch of simulated trials, and
        spot-check the resulting damage/kill numbers.
      </p>
      {error && <p className="error">{error}</p>}

      <details className="role-group" open>
        <summary className="role-group-header">
          <span>Attacker</span>
        </summary>
        <UnitPicker
          label="Attacker"
          faction={attackerFaction}
          onFaction={setAttackerFaction}
          factions={factions}
          unitDefs={attackerUnitDefs}
          unitId={attackerUnitId}
          onUnit={setAttackerUnitId}
        />
        {attackerUnit && (
          <div className="inline-form">
            <label className="checkbox-label">
              Weapon
              <select value={weaponName} onChange={(e) => setWeaponName(e.target.value)} disabled={attackerUnit.weapons.length === 0}>
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
            {attackerUnit.weapons.length === 0 && <span className="muted">This unit has no weapons.</span>}
            <label className="checkbox-label">
              Weapons firing
              <input
                type="number"
                min={1}
                value={weaponCount}
                onChange={(e) => setWeaponCount(Math.max(1, Number(e.target.value) || 1))}
                style={{ width: "4rem" }}
              />
            </label>
          </div>
        )}
        <p className="muted">
          "Weapons firing" is how many copies of this weapon shoot (e.g. a 5-model squad all with
          this gun = 5). The weapon's own A is the attacks per model.
        </p>
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
          unitDefs={defenderUnitDefs}
          unitId={defenderUnitId}
          onUnit={setDefenderUnitId}
        />
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
