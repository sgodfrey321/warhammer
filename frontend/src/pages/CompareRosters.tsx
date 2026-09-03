import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { CharacteristicContributionsModal } from "../components/CharacteristicContributionsModal";
import { UnitListModal } from "../components/UnitListModal";
import type { Roster, UnitOut } from "../types";
import { damageVsWounds, parseToughness, parseWounds, strengthVsToughness } from "../weapons";
import type { CharacteristicContribution, OverlayBucket, OverlayResult } from "../weapons";

// Same validated pair used by RosterEditor's two-series Save/Invulnerable Save chart.
const CHART_COLOR = "#e0574a";
const CHART_COLOR_SECONDARY = "#4a90c9";
const BAR_SIZE = 24;
const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];

type RangeTypeFilter = "" | "Ranged Weapons" | "Melee Weapons";

function distinctRoles(units: UnitOut[]): string[] {
  return Array.from(new Set(units.map((u) => u.unit_definition.role).filter((r): r is string => !!r))).sort();
}

// Both series expressed as % of their own army's total (attacks for the Strength/Damage side,
// unit entries for the Toughness/Wounds side) -- an overlay of two differently-scaled counts
// would otherwise be misleading read as raw numbers side by side.
function OverlayChart({
  buckets,
  armyALabel,
  armyBLabel,
  valuePrefix,
  onSelectA,
  onSelectB,
}: {
  buckets: OverlayBucket[];
  armyALabel: string;
  armyBLabel: string;
  valuePrefix: string;
  onSelectA: (value: number) => void;
  onSelectB: (value: number) => void;
}) {
  if (buckets.length === 0) return null;
  return (
    <div className="chart-container chart-clickable">
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={buckets}>
          <CartesianGrid strokeDasharray="" stroke="#333747" vertical={false} />
          <XAxis dataKey="value" tickFormatter={(v) => `${valuePrefix}${v}`} stroke="#8b8f9e" />
          <YAxis allowDecimals={false} stroke="#8b8f9e" unit="%" />
          <Tooltip
            contentStyle={{ background: "#1e212b", border: "1px solid #333747" }}
            labelFormatter={(v) => `${valuePrefix}${v}`}
            formatter={(value, name, item) => {
              const raw = item.dataKey === "armyAPct" ? item.payload.armyARaw : item.payload.armyBRaw;
              const unit = item.dataKey === "armyAPct" ? "attacks" : "units";
              return [`${value}% (${raw} ${unit})`, name];
            }}
          />
          <Legend />
          <Bar
            dataKey="armyAPct"
            name={armyALabel}
            fill={CHART_COLOR}
            radius={BAR_RADIUS}
            maxBarSize={BAR_SIZE}
            onClick={(data) => onSelectA((data.payload as OverlayBucket).value)}
          />
          <Bar
            dataKey="armyBPct"
            name={armyBLabel}
            fill={CHART_COLOR_SECONDARY}
            radius={BAR_RADIUS}
            maxBarSize={BAR_SIZE}
            onClick={(data) => onSelectB((data.payload as OverlayBucket).value)}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CompareRosters() {
  const [rosters, setRosters] = useState<Roster[]>([]);
  const [rosterAId, setRosterAId] = useState<number | null>(null);
  const [rosterBId, setRosterBId] = useState<number | null>(null);
  const [unitsA, setUnitsA] = useState<UnitOut[]>([]);
  const [unitsB, setUnitsB] = useState<UnitOut[]>([]);
  const [weaponType, setWeaponType] = useState<RangeTypeFilter>("");
  const [roleFilterA, setRoleFilterA] = useState("");
  const [roleFilterB, setRoleFilterB] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [contributionsModal, setContributionsModal] = useState<{
    title: string;
    contributions: CharacteristicContribution[];
  } | null>(null);
  const [unitListModal, setUnitListModal] = useState<{ title: string; units: UnitOut[] } | null>(null);

  useEffect(() => {
    api.listRosters().then(setRosters).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (rosterAId === null) {
      setUnitsA([]);
      return;
    }
    api.listUnits(rosterAId).then(setUnitsA).catch((e) => setError(String(e)));
  }, [rosterAId]);

  useEffect(() => {
    if (rosterBId === null) {
      setUnitsB([]);
      return;
    }
    api.listUnits(rosterBId).then(setUnitsB).catch((e) => setError(String(e)));
  }, [rosterBId]);

  // Reset a side's unit-type filter when it switches to a roster that doesn't have that role --
  // otherwise it silently filters everything out with no visible explanation.
  useEffect(() => {
    if (roleFilterA && !unitsA.some((u) => u.unit_definition.role === roleFilterA)) setRoleFilterA("");
  }, [unitsA, roleFilterA]);

  useEffect(() => {
    if (roleFilterB && !unitsB.some((u) => u.unit_definition.role === roleFilterB)) setRoleFilterB("");
  }, [unitsB, roleFilterB]);

  const rosterAName = rosters.find((r) => r.id === rosterAId)?.name ?? "Army A";
  const rosterBName = rosters.find((r) => r.id === rosterBId)?.name ?? "Army B";

  function handleSwap() {
    setRosterAId(rosterBId);
    setRosterBId(rosterAId);
    setRoleFilterA(roleFilterB);
    setRoleFilterB(roleFilterA);
  }

  function showContributions(result: OverlayResult, value: number, label: string) {
    setContributionsModal({ title: `${label} — ${rosterAName}`, contributions: result.contributionsA.get(value) ?? [] });
  }

  function showToughnessMatches(toughness: number) {
    const matches = filteredUnitsB.filter((u) => parseToughness(u.unit_definition.stats.T ?? "") === toughness);
    setUnitListModal({ title: `Toughness ${toughness} — ${rosterBName}`, units: matches });
  }

  function showWoundsMatches(wounds: number) {
    const matches = filteredUnitsB.filter((u) => parseWounds(u.unit_definition.stats.W ?? "") === wounds);
    setUnitListModal({ title: `Wounds ${wounds} — ${rosterBName}`, units: matches });
  }

  const rolesA = distinctRoles(unitsA);
  const rolesB = distinctRoles(unitsB);
  const filteredUnitsA = roleFilterA ? unitsA.filter((u) => u.unit_definition.role === roleFilterA) : unitsA;
  const filteredUnitsB = roleFilterB ? unitsB.filter((u) => u.unit_definition.role === roleFilterB) : unitsB;
  const rangeType = weaponType || undefined;
  const weaponTypeLabel = weaponType === "Ranged Weapons" ? "ranged" : weaponType === "Melee Weapons" ? "melee" : "ranged + melee";

  const ready = rosterAId !== null && rosterBId !== null;
  const stResult = ready ? strengthVsToughness(filteredUnitsA, filteredUnitsB, rangeType) : null;
  const dwResult = ready ? damageVsWounds(filteredUnitsA, filteredUnitsB, rangeType) : null;

  return (
    <div className="page">
      <h1>Compare Rosters</h1>
      <p className="muted">
        Overlay two of your rosters' distributions on the same axis — Army A's weapon output
        against Army B's model durability. Both sides are shown as % of their own army's total, so
        differently-scaled counts (attacks vs. unit entries) read on one shared scale.
      </p>
      {error && <p className="error">{error}</p>}

      <div className="inline-form">
        <select value={rosterAId ?? ""} onChange={(e) => setRosterAId(e.target.value ? Number(e.target.value) : null)}>
          <option value="">Army A...</option>
          {rosters.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name} ({r.faction})
            </option>
          ))}
        </select>
        <select value={rosterBId ?? ""} onChange={(e) => setRosterBId(e.target.value ? Number(e.target.value) : null)}>
          <option value="">Army B...</option>
          {rosters.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name} ({r.faction})
            </option>
          ))}
        </select>
        <button type="button" onClick={handleSwap} disabled={rosterAId === null || rosterBId === null}>
          Swap
        </button>
      </div>

      {ready && (
        <div className="inline-form">
          <label className="checkbox-label">
            Weapon type
            <select value={weaponType} onChange={(e) => setWeaponType(e.target.value as RangeTypeFilter)}>
              <option value="">Ranged + Melee</option>
              <option value="Ranged Weapons">Ranged only</option>
              <option value="Melee Weapons">Melee only</option>
            </select>
          </label>
          <label className="checkbox-label">
            {rosterAName} unit type
            <select value={roleFilterA} onChange={(e) => setRoleFilterA(e.target.value)}>
              <option value="">All unit types</option>
              {rolesA.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
          <label className="checkbox-label">
            {rosterBName} unit type
            <select value={roleFilterB} onChange={(e) => setRoleFilterB(e.target.value)}>
              <option value="">All unit types</option>
              {rolesB.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {!ready && <p className="muted">Pick two rosters to compare.</p>}

      {ready && stResult && (
        <details className="role-group" open>
          <summary className="role-group-header">
            <span>Strength vs Toughness</span>
          </summary>
          <p className="muted">
            {rosterAName}'s total {weaponTypeLabel} attack output grouped by weapon Strength, against{" "}
            {rosterBName}'s models grouped by Toughness. Click a bar to see which units/weapons it's
            made of.
            {stResult.skippedUnitsA > 0 &&
              ` ${stResult.skippedUnitsA} unit${stResult.skippedUnitsA === 1 ? "" : "s"} in ${rosterAName} with no confirmed loadout not included.`}
          </p>
          {stResult.buckets.length > 0 ? (
            <OverlayChart
              buckets={stResult.buckets}
              armyALabel={`${rosterAName} — Strength`}
              armyBLabel={`${rosterBName} — Toughness`}
              valuePrefix=""
              onSelectA={(value) => showContributions(stResult, value, `Strength ${value}`)}
              onSelectB={showToughnessMatches}
            />
          ) : (
            <p className="muted">No data to chart yet.</p>
          )}
        </details>
      )}

      {ready && dwResult && (
        <details className="role-group" open>
          <summary className="role-group-header">
            <span>Damage vs Wounds</span>
          </summary>
          <p className="muted">
            {rosterAName}'s total {weaponTypeLabel} attack output grouped by weapon Damage
            (dice-notation values like D6 are averaged and rounded), against {rosterBName}'s models
            grouped by Wounds. Click a bar to see which units/weapons it's made of.
            {dwResult.skippedUnitsA > 0 &&
              ` ${dwResult.skippedUnitsA} unit${dwResult.skippedUnitsA === 1 ? "" : "s"} in ${rosterAName} with no confirmed loadout not included.`}
          </p>
          {dwResult.buckets.length > 0 ? (
            <OverlayChart
              buckets={dwResult.buckets}
              armyALabel={`${rosterAName} — Damage`}
              armyBLabel={`${rosterBName} — Wounds`}
              valuePrefix=""
              onSelectA={(value) => showContributions(dwResult, value, `Damage ${value}`)}
              onSelectB={showWoundsMatches}
            />
          ) : (
            <p className="muted">No data to chart yet.</p>
          )}
        </details>
      )}

      {contributionsModal && (
        <CharacteristicContributionsModal
          title={contributionsModal.title}
          contributions={contributionsModal.contributions}
          onClose={() => setContributionsModal(null)}
        />
      )}
      {unitListModal && (
        <UnitListModal title={unitListModal.title} units={unitListModal.units} onClose={() => setUnitListModal(null)} />
      )}
    </div>
  );
}
