import { useEffect, useState } from "react";
import { api } from "../api";
import { Keyword } from "../components/Keyword";
import { StatBoxes, statPairs, weaponPairs } from "../components/StatBoxes";
import { renderAbilityText } from "../markup";
import type { UnitDefinition } from "../types";
import { groupWeaponsByRangeType } from "../weapons";

// No dedicated backend flag for this (unlike is_legends) -- BSData only marks a Crucible of War
// datasheet by suffixing the name itself, confirmed against real indexed data (e.g. "Bloodcult
// Champion [Crucible]").
function isCrucible(u: UnitDefinition): boolean {
  return u.name.includes("[Crucible]");
}

// GW's own datasheet ordering for Battlefield Role, roughly "who leads, who holds the line,
// who else" -- anything not in this fixed list (or role === null) sorts after it as "Other".
const ROLE_ORDER = [
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

function roleRank(role: string): number {
  const idx = ROLE_ORDER.indexOf(role);
  return idx === -1 ? ROLE_ORDER.length : idx;
}

function groupByRole(defs: UnitDefinition[]): [string, UnitDefinition[]][] {
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

export function UnitsBrowser() {
  const [unitDefs, setUnitDefs] = useState<UnitDefinition[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [unitSearch, setUnitSearch] = useState("");
  const [showLegends, setShowLegends] = useState(false);
  const [showCrucible, setShowCrucible] = useState(false);
  const [expandedUnitFactions, setExpandedUnitFactions] = useState<Set<string>>(new Set());

  useEffect(() => {
    api.listAllUnitDefinitions().then(setUnitDefs).catch((e) => setError(String(e)));
  }, []);

  function toggleUnitFaction(f: string) {
    setExpandedUnitFactions((prev) => {
      const next = new Set(prev);
      if (next.has(f)) next.delete(f);
      else next.add(f);
      return next;
    });
  }

  const search = unitSearch.trim().toLowerCase();
  const filteredUnitDefs = unitDefs.filter((u) => {
    if (search && !u.name.toLowerCase().includes(search)) return false;
    if (!showLegends && u.is_legends) return false;
    if (!showCrucible && isCrucible(u)) return false;
    return true;
  });
  const unitsByFaction = new Map<string, UnitDefinition[]>();
  for (const u of filteredUnitDefs) {
    const arr = unitsByFaction.get(u.faction) ?? [];
    arr.push(u);
    unitsByFaction.set(u.faction, arr);
  }
  const unitFactionGroups = Array.from(unitsByFaction.entries()).sort((a, b) => a[0].localeCompare(b[0]));

  return (
    <div className="page">
      <h1>Units</h1>
      <p className="muted">
        Every unit indexed from BSData across all imported factions — a reference catalogue, not
        tied to any roster.
      </p>
      {error && <p className="error">{error}</p>}
      <div className="inline-form">
        <input
          type="text"
          placeholder="Search units..."
          value={unitSearch}
          onChange={(e) => setUnitSearch(e.target.value)}
        />
        <label className="checkbox-label">
          <input type="checkbox" checked={showLegends} onChange={(e) => setShowLegends(e.target.checked)} />
          Legends
        </label>
        <label className="checkbox-label">
          <input type="checkbox" checked={showCrucible} onChange={(e) => setShowCrucible(e.target.checked)} />
          Crucible
        </label>
      </div>
      <ul className="army-rules-list">
        {unitFactionGroups.map(([factionName, defs]) => (
          <li key={factionName}>
            <button
              type="button"
              className="link-button faction-toggle"
              onClick={() => toggleUnitFaction(factionName)}
            >
              {expandedUnitFactions.has(factionName) ? "▾" : "▸"} <strong>{factionName}</strong>{" "}
              <span className="muted">
                ({defs.length} unit{defs.length === 1 ? "" : "s"})
              </span>
            </button>
            {expandedUnitFactions.has(factionName) && (
              <div className="unit-def-list">
                {groupByRole(defs).map(([role, roleDefs]) => (
                  <details key={role} className="unit-role-group" open>
                    <summary className="unit-role-heading">
                      {role} <span className="muted">({roleDefs.length})</span>
                    </summary>
                    {roleDefs.map((u) => (
                      <details key={u.id} className="unit-card">
                        <summary className="unit-def-summary">
                          <span className="unit-def-name">{u.name}</span>
                          <span className="muted"> ({u.points_cost}pts)</span>
                          {u.is_legends && <span className="tag">Legends</span>}
                          {isCrucible(u) && <span className="tag">Crucible</span>}
                          {statPairs(u.stats).length > 0 && (
                            <div className="stat-line">
                              <StatBoxes pairs={statPairs(u.stats)} />
                            </div>
                          )}
                          {u.rules.length > 0 && (
                            <div className="rule-tags">
                              {u.rules.map((r) => (
                                <span key={r} className="tag">
                                  <Keyword name={r} />
                                </span>
                              ))}
                            </div>
                          )}
                        </summary>
                        <div className="unit-def-details">
                          {groupWeaponsByRangeType(u.weapons).map(([rangeType, ws]) => (
                            <div key={rangeType}>
                              <h4 className="weapon-section-heading">{rangeType}</h4>
                              <ul className="ability-list">
                                {ws.map((w) => (
                                  <li key={w.name}>
                                    <strong>{w.name}</strong>
                                    <div className="stat-line">
                                      <StatBoxes pairs={weaponPairs(w)} />
                                    </div>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          ))}
                          {u.abilities.length > 0 && (
                            <ul className="ability-list">
                              {u.abilities.map((a) => (
                                <li key={a.name}>
                                  <strong>{a.name}:</strong> {renderAbilityText(a.text, `${u.id}-${a.name}`)}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </details>
                    ))}
                  </details>
                ))}
              </div>
            )}
          </li>
        ))}
        {unitFactionGroups.length === 0 && <li className="muted">No units match.</li>}
      </ul>
    </div>
  );
}
