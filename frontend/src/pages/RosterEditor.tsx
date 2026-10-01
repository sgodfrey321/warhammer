import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { groupDefsByRole, isCrucible, matchFaction } from "../catalog";
import { BAR_RADIUS, BAR_SIZE, CHART_COLOR, CHART_COLOR_SECONDARY, OTHER_COLOR, SKILL_COLORS } from "../charts";
import { Keyword } from "../components/Keyword";
import { StatBoxes } from "../components/StatBoxes";
import { UnitDetailsModal } from "../components/UnitDetailsModal";
import { UnitListModal } from "../components/UnitListModal";
import { WeaponContributionsModal } from "../components/WeaponContributionsModal";
import { renderAbilityText } from "../markup";
import { statPairs, weaponPairs } from "../statPairs";
import { DISPOSITIONS, DISPOSITION_LABELS, PHASES, POOL_SCOPES, STAT_ORDER } from "../types";
import type {
  BattleOut,
  DeclaredStatePool,
  Disposition,
  FactionArmyRules,
  FactionDetachments,
  Roster,
  UnitAttachment,
  UnitBuff,
  UnitDefinition,
  UnitOut,
  UnitSynergy,
} from "../types";
import { auraAbilityReferences, groupUnitsByRole, leaderAbilityReferences, psychicAbilityReferences } from "../units";
import {
  groupLoadoutByRangeType,
  groupWeaponsByRangeType,
  parseLeadingInt,
  parseSaveValue,
  unitsByMovement,
  unitsBySave,
  unitsByToughness,
  unitsByWounds,
  matchLoadoutWeapons,
  weaponAttacksByStrengthAndSkill,
} from "../weapons";
import type {
  MovementBucket,
  SaveBucket,
  SkillStrengthBucket,
  StrengthSkillBucket,
  StrengthSkillResult,
  ToughnessBucket,
  WeaponContribution,
  WoundsBucket,
} from "../weapons";

// Ranged Firepower / Melee Onslaught: total attacks by weapon Strength, stacked by to-hit value
// (BS/WS) so both "what do we wound with" and "what do we hit on" read in one chart. Clicking any
// segment of a Strength bar drills down to every unit/weapon at that Strength -- not just the
// segment's own to-hit value -- since the split exists to visualize to-hit, not to filter by it.
function StrengthSkillChart({
  result,
  skillLabel,
  onSelectBucket,
}: {
  result: StrengthSkillResult;
  skillLabel: "BS" | "WS";
  onSelectBucket: (strength: number) => void;
}) {
  if (result.buckets.length === 0) return null;
  return (
    <div className="chart-container chart-clickable">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={result.buckets}>
          <CartesianGrid strokeDasharray="" stroke="#333747" vertical={false} />
          <XAxis dataKey="strength" tickFormatter={(s) => `S${s}`} stroke="#8b8f9e" />
          <YAxis allowDecimals={false} stroke="#8b8f9e" />
          <Tooltip
            contentStyle={{ background: "#1e212b", border: "1px solid #333747" }}
            labelFormatter={(s) => `Strength ${s}`}
            formatter={(value, name) => [value, `${skillLabel}${name}`]}
          />
          <Legend formatter={(value) => `${skillLabel}${value}`} />
          {result.skillKeys.map((skill, i) => (
            <Bar
              key={skill}
              dataKey={skill}
              stackId="a"
              fill={SKILL_COLORS[i % SKILL_COLORS.length]}
              stroke="#1e212b"
              strokeWidth={2}
              radius={i === result.skillKeys.length - 1 ? BAR_RADIUS : undefined}
              maxBarSize={BAR_SIZE}
              onClick={(data) => onSelectBucket((data.payload as StrengthSkillBucket).strength)}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// The same data cut the other way round: to-hit value (BS/WS) as the primary axis, stacked by
// Strength -- "what do we hit on" read first, "what do we wound with" as the breakdown. Clicking
// a segment drills down to every unit/weapon at that to-hit value, across all Strengths.
function SkillStrengthChart({
  result,
  skillLabel,
  onSelectBucket,
}: {
  result: StrengthSkillResult;
  skillLabel: "BS" | "WS";
  onSelectBucket: (skill: string) => void;
}) {
  if (result.bySkillBuckets.length === 0) return null;
  return (
    <div className="chart-container chart-clickable">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={result.bySkillBuckets}>
          <CartesianGrid strokeDasharray="" stroke="#333747" vertical={false} />
          <XAxis dataKey="skill" tickFormatter={(s) => `${skillLabel}${s}`} stroke="#8b8f9e" />
          <YAxis allowDecimals={false} stroke="#8b8f9e" />
          <Tooltip
            contentStyle={{ background: "#1e212b", border: "1px solid #333747" }}
            labelFormatter={(s) => `${skillLabel}${s}`}
            formatter={(value, name) => [value, name === "Other" ? "Other" : `S${name}`]}
          />
          <Legend formatter={(value) => (value === "Other" ? "Other" : `S${value}`)} />
          {result.displayStrengths.map((strength, i) => (
            <Bar
              key={strength}
              dataKey={String(strength)}
              stackId="a"
              fill={strength === "Other" ? OTHER_COLOR : SKILL_COLORS[i % SKILL_COLORS.length]}
              stroke="#1e212b"
              strokeWidth={2}
              radius={i === result.displayStrengths.length - 1 ? BAR_RADIUS : undefined}
              maxBarSize={BAR_SIZE}
              onClick={(data) => onSelectBucket((data.payload as SkillStrengthBucket).skill)}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// One row renderer shared by a plain unit and a leader nested into the unit it leads (see
// RosterEditor's Units section) -- avoids duplicating this JSX for both cases.
// Header line for one unit in a (possibly combined) card: name, points, its rules and buffs, and
// its own remove. The weapons/abilities live in UnitDetailsBody so a leader + its bodyguard share
// one details view for the whole block.
function UnitRow({
  unit,
  isLeader,
  onRemove,
  onRemoveBuff,
}: {
  unit: UnitOut;
  isLeader?: boolean;
  onRemove: (unitId: number) => void;
  onRemoveBuff: (unit: UnitOut, index: number) => void;
}) {
  const stats = statPairs(unit.unit_definition.stats);
  return (
    <div className={`unit-row${isLeader ? " leader" : ""}`}>
      <div className="unit-row-head">
        <span className="unit-row-identity">
          <span className="unit-name">{unit.unit_definition.name}</span>
          <span className="muted"> ({unit.points}pts)</span>
          <button type="button" className="link-button" onClick={() => onRemove(unit.id)}>
            remove
          </button>
        </span>
        {stats.length > 0 && (
          <div className="unit-row-stats stat-line">
            <StatBoxes pairs={stats} />
          </div>
        )}
      </div>
      {unit.unit_definition.rules.length > 0 && (
        <div className="rule-tags">
          {unit.unit_definition.rules.map((r) => (
            <span key={r} className="tag">
              <Keyword name={r} />
            </span>
          ))}
        </div>
      )}
      {unit.buffs.length > 0 && (
        <div className="muted loadout-summary">
          {unit.buffs.map((b, i) => (
            <span key={i} className="tag">
              {b.stat} {b.modifier} ({b.label})
              <button type="button" className="link-button" onClick={() => onRemoveBuff(unit, i)}>
                remove
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// One unit's weapons + abilities, rendered inside a block's shared details view. When a block has a
// leader attached, several of these stack under one "details" toggle so the whole block reads as
// one item.
function UnitDetailsBody({ unit }: { unit: UnitOut }) {
  const abilities = unit.unit_definition.abilities;
  const hasLoadout = unit.loadout.length > 0;
  return (
    <div className="unit-details-body">
      <h4 className="weapon-section-heading">{unit.unit_definition.name}</h4>
      {/* Weapons and abilities each only fill ~half the width on their own, so run them as two
          columns side by side (collapsing to one on narrow screens via CSS). */}
      <div className="unit-details-cols">
        {hasLoadout && (
          <div className="unit-details-weapons">
            {groupLoadoutByRangeType(unit.loadout, unit.unit_definition.weapons).map(([rangeType, items]) => (
              <div key={rangeType}>
                <h5 className="weapon-section-heading">{rangeType}</h5>
                <ul className="ability-list">
                  {items.map((item) => {
                    const matches = matchLoadoutWeapons(item.name, unit.unit_definition.weapons);
                    return (
                      <li key={item.name}>
                        <strong>
                          {item.count}x {item.name}
                        </strong>
                        {matches.length === 0 && <span className="muted"> profile not indexed</span>}
                        {matches.map((w) => (
                          <div key={w.name} className="stat-line">
                            {matches.length > 1 && `${w.name.replace(/^➤\s*/, "")}: `}
                            <StatBoxes pairs={weaponPairs(w)} />
                          </div>
                        ))}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        )}
        {abilities.length > 0 && (
          <ul className="ability-list unit-details-abilities">
            {abilities.map((a) => (
              <li key={a.name}>
                <strong>{a.name}:</strong> {renderAbilityText(a.text, `${unit.id}-${a.name}`)}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export function RosterEditor() {
  const { id } = useParams();
  const rosterId = Number(id);
  const navigate = useNavigate();

  const [roster, setRoster] = useState<Roster | null>(null);
  const [units, setUnits] = useState<UnitOut[]>([]);
  const [availableUnits, setAvailableUnits] = useState<UnitDefinition[]>([]);
  const [allDetachments, setAllDetachments] = useState<FactionDetachments[]>([]);
  const [allArmyRules, setAllArmyRules] = useState<FactionArmyRules[]>([]);
  const [showLegends, setShowLegends] = useState(false);
  const [showCrucible, setShowCrucible] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [synergies, setSynergies] = useState<UnitSynergy[]>([]);
  const [pools, setPools] = useState<DeclaredStatePool[]>([]);
  const [attachments, setAttachments] = useState<UnitAttachment[]>([]);
  const [battles, setBattles] = useState<BattleOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [detailsGroup, setDetailsGroup] = useState<{ primary: UnitOut; leaders: UnitOut[] } | null>(null);
  const [weaponDrilldown, setWeaponDrilldown] = useState<{
    title: string;
    skillLabel: "BS" | "WS";
    contributions: WeaponContribution[];
  } | null>(null);
  const [unitListModal, setUnitListModal] = useState<{ title: string; units: UnitOut[] } | null>(null);
  const [expandedDetails, setExpandedDetails] = useState<Set<number>>(new Set());

  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const [sourceUnitId, setSourceUnitId] = useState<number | "">("");
  const [targetUnitId, setTargetUnitId] = useState<number | "">("");
  const [triggerPhase, setTriggerPhase] = useState<string>(PHASES[0]);
  const [note, setNote] = useState("");

  const [leaderUnitId, setLeaderUnitId] = useState<number | "">("");
  const [ledUnitId, setLedUnitId] = useState<number | "">("");

  const [buffUnitId, setBuffUnitId] = useState<number | "">("");
  const [buffStat, setBuffStat] = useState<string>(STAT_ORDER[0]);
  const [buffModifier, setBuffModifier] = useState("");
  const [buffLabel, setBuffLabel] = useState("");

  const [poolName, setPoolName] = useState("");
  const [poolMax, setPoolMax] = useState(1);
  const [poolScope, setPoolScope] = useState<string>(POOL_SCOPES[0]);
  const [poolStacking, setPoolStacking] = useState(false);

  function refresh() {
    api.getRoster(rosterId).then(setRoster).catch((e) => setError(String(e)));
    api.listUnits(rosterId).then(setUnits).catch((e) => setError(String(e)));
    api.listSynergies(rosterId).then(setSynergies).catch((e) => setError(String(e)));
    api.listPools(rosterId).then(setPools).catch((e) => setError(String(e)));
    api.listAttachments(rosterId).then(setAttachments).catch((e) => setError(String(e)));
    api.listBattlesForRoster(rosterId).then(setBattles).catch((e) => setError(String(e)));
  }

  useEffect(refresh, [rosterId]);

  const faction = roster?.faction;
  useEffect(() => {
    if (!faction) return;
    api.listUnitDefinitionsByFaction(faction).then(setAvailableUnits).catch((e) => setError(String(e)));
  }, [faction]);

  useEffect(() => {
    api.listDetachments().then(setAllDetachments).catch((e) => setError(String(e)));
    api.listArmyRules().then(setAllArmyRules).catch((e) => setError(String(e)));
  }, []);

  async function handleSelectDetachment(name: string) {
    try {
      const [first, ...rest] = roster?.detachments ?? [];
      const detachments = name ? [{ ...first, name, dp: first?.dp ?? 0 }, ...rest] : rest;
      const updated = await api.updateRoster(rosterId, { detachments });
      setRoster(updated);
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleSelectDisposition(value: string) {
    try {
      const updated = await api.updateRoster(rosterId, { disposition: (value || null) as Disposition | null });
      setRoster(updated);
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleAddUnit(unit: { id: string }) {
    try {
      await api.addUnit(rosterId, { unit_definition_id: unit.id, quantity: 1 });
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleRemoveUnit(unitId: number) {
    try {
      await api.deleteUnit(rosterId, unitId);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  function toggleDetails(unitId: number) {
    setExpandedDetails((prev) => {
      const next = new Set(prev);
      if (next.has(unitId)) next.delete(unitId);
      else next.add(unitId);
      return next;
    });
  }

  async function handleAddBuff(e: React.FormEvent) {
    e.preventDefault();
    if (buffUnitId === "" || !buffModifier.trim() || !buffLabel.trim()) return;
    const unit = units.find((u) => u.id === buffUnitId);
    if (!unit) return;
    try {
      const buff: UnitBuff = { label: buffLabel.trim(), stat: buffStat, modifier: buffModifier.trim() };
      await api.updateUnit(rosterId, unit.id, { buffs: [...unit.buffs, buff] });
      setBuffModifier("");
      setBuffLabel("");
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleRemoveBuff(unit: UnitOut, index: number) {
    try {
      await api.updateUnit(rosterId, unit.id, { buffs: unit.buffs.filter((_, i) => i !== index) });
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleAddSynergy(e: React.FormEvent) {
    e.preventDefault();
    if (sourceUnitId === "" || targetUnitId === "") return;
    try {
      await api.addSynergy(rosterId, {
        source_unit_id: Number(sourceUnitId),
        target_unit_id: Number(targetUnitId),
        trigger_phase: triggerPhase,
        note: note || undefined,
      });
      setNote("");
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleDeleteSynergy(synergyId: number) {
    try {
      await api.deleteSynergy(rosterId, synergyId);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleAddPool(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.addPool(rosterId, { name: poolName, max_value: poolMax, scope: poolScope, stacking: poolStacking });
      setPoolName("");
      setPoolMax(1);
      setPoolStacking(false);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleDeletePool(poolId: number) {
    try {
      await api.deletePool(rosterId, poolId);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleAddAttachment(e: React.FormEvent) {
    e.preventDefault();
    if (leaderUnitId === "" || ledUnitId === "") return;
    try {
      await api.addAttachment(rosterId, Number(leaderUnitId), Number(ledUnitId));
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleDeleteAttachment(attachmentId: number) {
    try {
      await api.deleteAttachment(rosterId, attachmentId);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  function handleStartBattle() {
    navigate(`/battles/setup?rosterId=${rosterId}`);
  }

  function startRename() {
    if (!roster) return;
    setNameDraft(roster.name);
    setRenaming(true);
  }

  async function handleRename(e: React.FormEvent) {
    e.preventDefault();
    if (!nameDraft.trim()) return;
    try {
      await api.updateRoster(rosterId, { name: nameDraft.trim() });
      setRenaming(false);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  }

  async function handleDeleteRoster() {
    try {
      await api.deleteRoster(rosterId);
      navigate("/");
    } catch (e) {
      setError(String(e));
    }
  }

  function unitLabel(unitId: number): string {
    const u = units.find((x) => x.id === unitId);
    return u ? u.unit_definition.name : `#${unitId}`;
  }

  if (!roster) return <div className="page roster-editor-page">Loading...</div>;

  const rangedResult = weaponAttacksByStrengthAndSkill(units, "Ranged Weapons");
  const meleeResult = weaponAttacksByStrengthAndSkill(units, "Melee Weapons");
  const movementBuckets = unitsByMovement(units);
  const toughnessBuckets = unitsByToughness(units);
  const saveBuckets = unitsBySave(units);
  const woundsBuckets = unitsByWounds(units);

  function showWeaponDrilldown(result: StrengthSkillResult, skillLabel: "BS" | "WS", strength: number) {
    const contributions = result.skillKeys.flatMap((skill) => result.contributions.get(`${strength}|${skill}`) ?? []);
    setWeaponDrilldown({ title: `Strength ${strength}`, skillLabel, contributions });
  }

  function showSkillDrilldown(result: StrengthSkillResult, skillLabel: "BS" | "WS", skill: string) {
    const contributions = result.strengthKeys.flatMap((s) => result.contributions.get(`${s}|${skill}`) ?? []);
    setWeaponDrilldown({ title: `${skillLabel}${skill}`, skillLabel, contributions });
  }

  function showMovementDrilldown(movement: number) {
    const matches = units.filter((u) => parseLeadingInt(u.unit_definition.stats.M ?? "") === movement);
    setUnitListModal({ title: `Movement ${movement}"`, units: matches });
  }

  function showSaveDrilldown(stat: "Sv" | "InSv", save: string) {
    const label = stat === "Sv" ? "Armor Save" : "Invulnerable Save";
    const matches = units.filter((u) => parseSaveValue(u.unit_definition.stats[stat]) === save);
    setUnitListModal({ title: `${label} ${save}`, units: matches });
  }

  function showToughnessDrilldown(toughness: number) {
    const matches = units.filter((u) => parseLeadingInt(u.unit_definition.stats.T ?? "") === toughness);
    setUnitListModal({ title: `Toughness ${toughness}`, units: matches });
  }

  function showWoundsDrilldown(wounds: number) {
    const matches = units.filter((u) => parseLeadingInt(u.unit_definition.stats.W ?? "") === wounds);
    setUnitListModal({ title: `Wounds ${wounds}`, units: matches });
  }
  const roleGroups = groupUnitsByRole(units, attachments);
  const nestedLeaderIds = new Set(attachments.map((a) => a.leader_unit_id));
  const filteredAvailableUnits = availableUnits.filter((u) => {
    if (!showLegends && u.is_legends) return false;
    if (!showCrucible && isCrucible(u)) return false;
    return true;
  });
  const leaderReferences = leaderAbilityReferences(units);
  const auraReferences = auraAbilityReferences(units);
  const psychicReferences = psychicAbilityReferences(units);
  const factionDetachments = matchFaction(allDetachments, roster.faction);
  const selectedDetachmentName = roster.detachments[0]?.name ?? "";
  const selectedDetachment = factionDetachments?.detachments.find((d) => d.name === selectedDetachmentName);
  const factionArmyRules = matchFaction(allArmyRules, roster.faction);

  return (
    <div className="page roster-editor-page">
      <div className="roster-editor-layout">
      <div className="roster-editor-main">
      {renaming ? (
        <form className="inline-form" onSubmit={handleRename}>
          <input
            type="text"
            value={nameDraft}
            onChange={(e) => setNameDraft(e.target.value)}
            autoFocus
            required
          />
          <button type="submit">Save</button>
          <button type="button" onClick={() => setRenaming(false)}>
            Cancel
          </button>
        </form>
      ) : (
        <h1>
          {roster.name}{" "}
          <button type="button" className="link-button" onClick={startRename}>
            rename
          </button>
        </h1>
      )}
      <p className="muted">
        {roster.faction} {roster.points_limit ? `— ${roster.points_limit}pts limit` : ""}
      </p>
      {error && <p className="error">{error}</p>}

      <div className="inline-form">
        <label className="checkbox-label">
          Detachment
          <select value={selectedDetachmentName} onChange={(e) => handleSelectDetachment(e.target.value)}>
            <option value="">None chosen</option>
            {factionDetachments?.detachments.map((d) => (
              <option key={d.name} value={d.name}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        {!factionDetachments && <span className="muted">No detachments indexed for this faction yet.</span>}
        <label className="checkbox-label">
          Force Disposition
          <select value={roster.disposition ?? ""} onChange={(e) => handleSelectDisposition(e.target.value)}>
            <option value="">None chosen</option>
            {DISPOSITIONS.map((d) => (
              <option key={d} value={d}>
                {DISPOSITION_LABELS[d]}
              </option>
            ))}
          </select>
        </label>
      </div>
      {selectedDetachment && (
        <p className="muted">
          <Link to={`/battles/setup?rosterId=${rosterId}`}>Next: choose your battle disposition →</Link>
        </p>
      )}

      <button type="button" onClick={handleStartBattle} className="primary">
        Start Battle
      </button>

      {confirmingDelete ? (
        <div className="delete-confirm">
          <p>
            Delete <strong>{roster.name}</strong> and everything in it — {units.length} unit
            {units.length === 1 ? "" : "s"}
            {battles.length > 0 && `, ${battles.length} battle${battles.length === 1 ? "" : "s"}`}? This can't be
            undone.
          </p>
          <button type="button" className="primary" onClick={handleDeleteRoster}>
            Delete Roster
          </button>
          <button type="button" onClick={() => setConfirmingDelete(false)}>
            Cancel
          </button>
        </div>
      ) : (
        <button type="button" className="link-button" onClick={() => setConfirmingDelete(true)}>
          Delete Roster
        </button>
      )}

      {battles.length > 0 && (
        <div className="battle-history">
          <span className="muted">Previous battles: </span>
          {battles.map((b, i) => (
            <span key={b.id}>
              {i > 0 && ", "}
              <Link to={`/battles/${b.id}`}>
                #{b.id} (Round {b.battle_round}, {b.current_phase})
              </Link>
            </span>
          ))}
        </div>
      )}

      <details className="accordion" open>
        <summary>Units</summary>
        <div className="inline-form">
          <button type="button" className="primary" onClick={() => setAddOpen(true)}>
            + Add units
          </button>
        </div>
        {roleGroups.map((group) => (
          <details key={group.role} className="role-group" open>
            <summary className="role-group-header">
              <span>{group.role}</span>
              <span className="role-group-points">{group.points}pts</span>
            </summary>
            {group.units
              .filter((u) => !nestedLeaderIds.has(u.id))
              .map((u) => {
                const leaders = attachments
                  .filter((a) => a.led_unit_id === u.id)
                  .map((a) => units.find((x) => x.id === a.leader_unit_id))
                  .filter((x): x is UnitOut => !!x);
                // Leader + bodyguard read as one block: one details toggle for all its units.
                const blockUnits = [...leaders, u];
                const blockExpanded = expandedDetails.has(u.id);
                const hasDetails = blockUnits.some(
                  (bu) => bu.unit_definition.abilities.length > 0 || bu.loadout.length > 0,
                );
                return (
                  <div key={u.id} className="unit-card">
                    {leaders.map((leader) => (
                      <UnitRow key={leader.id} unit={leader} isLeader onRemove={handleRemoveUnit} onRemoveBuff={handleRemoveBuff} />
                    ))}
                    <UnitRow unit={u} onRemove={handleRemoveUnit} onRemoveBuff={handleRemoveBuff} />
                    <div className="unit-row unit-block-actions">
                      {hasDetails && (
                        <button type="button" className="link-button" onClick={() => toggleDetails(u.id)}>
                          {blockExpanded ? "hide details" : "details"}
                        </button>
                      )}
                      <button type="button" className="link-button" onClick={() => setDetailsGroup({ primary: u, leaders })}>
                        full details
                      </button>
                    </div>
                    {blockExpanded && blockUnits.map((bu) => <UnitDetailsBody key={bu.id} unit={bu} />)}
                  </div>
                );
              })}
          </details>
        ))}
        {units.length === 0 && <p className="muted">No units yet — click “+ Add units”.</p>}
      </details>

      <details className="accordion">
        <summary>Army Analysis</summary>

        <details className="role-group" open>
          <summary className="role-group-header">
            <span>Ranged Firepower</span>
          </summary>
          <p className="muted">
            Total ranged shots this roster can put out, grouped by weapon Strength and stacked by
            Ballistic Skill (dice-notation Attacks like D6 are averaged; range-dependent bonuses
            like Rapid Fire aren't modeled). Click a segment to see which units it's made of.
            {rangedResult.skippedUnits > 0 &&
              ` ${rangedResult.skippedUnits} unit${rangedResult.skippedUnits === 1 ? "" : "s"} with no confirmed loadout not included.`}
          </p>
          {rangedResult.buckets.length > 0 ? (
            <>
              <StrengthSkillChart
                result={rangedResult}
                skillLabel="BS"
                onSelectBucket={(strength) => showWeaponDrilldown(rangedResult, "BS", strength)}
              />
              <p className="muted">Same data, cut the other way — Ballistic Skill first, stacked by Strength.</p>
              <SkillStrengthChart
                result={rangedResult}
                skillLabel="BS"
                onSelectBucket={(skill) => showSkillDrilldown(rangedResult, "BS", skill)}
              />
            </>
          ) : (
            <p className="muted">No ranged weapon data to chart yet.</p>
          )}
        </details>

        <details className="role-group" open>
          <summary className="role-group-header">
            <span>Melee Onslaught</span>
          </summary>
          <p className="muted">
            Total melee attacks this roster can put out, grouped by weapon Strength and stacked by
            Weapon Skill (same dice-averaging and loadout-only scope as Ranged Firepower above).
            Click a segment to see which units it's made of.
            {meleeResult.skippedUnits > 0 &&
              ` ${meleeResult.skippedUnits} unit${meleeResult.skippedUnits === 1 ? "" : "s"} with no confirmed loadout not included.`}
          </p>
          {meleeResult.buckets.length > 0 ? (
            <>
              <StrengthSkillChart
                result={meleeResult}
                skillLabel="WS"
                onSelectBucket={(strength) => showWeaponDrilldown(meleeResult, "WS", strength)}
              />
              <p className="muted">Same data, cut the other way — Weapon Skill first, stacked by Strength.</p>
              <SkillStrengthChart
                result={meleeResult}
                skillLabel="WS"
                onSelectBucket={(skill) => showSkillDrilldown(meleeResult, "WS", skill)}
              />
            </>
          ) : (
            <p className="muted">No melee weapon data to chart yet.</p>
          )}
        </details>

        <details className="role-group" open>
          <summary className="role-group-header">
            <span>Movement</span>
          </summary>
          <p className="muted">
            Units in this roster grouped by Movement — one bar contribution per unit entry, not
            weighted by squad size (there's no reliable per-model count to work from). Click a bar
            to see which units it's made of.
          </p>
          {movementBuckets.length > 0 ? (
            <div className="chart-container chart-clickable">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={movementBuckets}>
                  <CartesianGrid strokeDasharray="" stroke="#333747" vertical={false} />
                  <XAxis dataKey="movement" tickFormatter={(m) => `${m}"`} stroke="#8b8f9e" />
                  <YAxis allowDecimals={false} stroke="#8b8f9e" />
                  <Tooltip
                    contentStyle={{ background: "#1e212b", border: "1px solid #333747" }}
                    labelFormatter={(m) => `Movement ${m}"`}
                    formatter={(value) => [value, "units"]}
                  />
                  <Bar
                    dataKey="units"
                    fill={CHART_COLOR}
                    radius={BAR_RADIUS}
                    maxBarSize={BAR_SIZE}
                    onClick={(data) => showMovementDrilldown((data.payload as MovementBucket).movement)}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="muted">No movement data to chart yet.</p>
          )}
        </details>

        <details className="role-group" open>
          <summary className="role-group-header">
            <span>Toughness</span>
          </summary>
          <p className="muted">
            Units in this roster grouped by Toughness — one bar contribution per unit entry, not
            weighted by squad size. Click a bar to see which units it's made of.
          </p>
          {toughnessBuckets.length > 0 ? (
            <div className="chart-container chart-clickable">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={toughnessBuckets}>
                  <CartesianGrid strokeDasharray="" stroke="#333747" vertical={false} />
                  <XAxis dataKey="toughness" stroke="#8b8f9e" />
                  <YAxis allowDecimals={false} stroke="#8b8f9e" />
                  <Tooltip
                    contentStyle={{ background: "#1e212b", border: "1px solid #333747" }}
                    labelFormatter={(t) => `Toughness ${t}`}
                    formatter={(value) => [value, "units"]}
                  />
                  <Bar
                    dataKey="units"
                    fill={CHART_COLOR}
                    radius={BAR_RADIUS}
                    maxBarSize={BAR_SIZE}
                    onClick={(data) => showToughnessDrilldown((data.payload as ToughnessBucket).toughness)}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="muted">No toughness data to chart yet.</p>
          )}
        </details>

        <details className="role-group" open>
          <summary className="role-group-header">
            <span>Save / Invulnerable Save</span>
          </summary>
          <p className="muted">
            Units grouped by armor Save and Invulnerable Save (best 2+ to worst 7+/none), so both
            distributions read on the same scale. Click a bar to see which units it's made of.
          </p>
          {saveBuckets.length > 0 ? (
            <div className="chart-container chart-clickable">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={saveBuckets}>
                  <CartesianGrid strokeDasharray="" stroke="#333747" vertical={false} />
                  <XAxis dataKey="save" stroke="#8b8f9e" />
                  <YAxis allowDecimals={false} stroke="#8b8f9e" />
                  <Tooltip contentStyle={{ background: "#1e212b", border: "1px solid #333747" }} />
                  <Legend />
                  <Bar
                    dataKey="sv"
                    name="Armor Save"
                    fill={CHART_COLOR}
                    radius={BAR_RADIUS}
                    maxBarSize={BAR_SIZE}
                    onClick={(data) => showSaveDrilldown("Sv", (data.payload as SaveBucket).save)}
                  />
                  <Bar
                    dataKey="insv"
                    name="Invulnerable Save"
                    fill={CHART_COLOR_SECONDARY}
                    radius={BAR_RADIUS}
                    maxBarSize={BAR_SIZE}
                    onClick={(data) => showSaveDrilldown("InSv", (data.payload as SaveBucket).save)}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="muted">No save data to chart yet.</p>
          )}
        </details>

        <details className="role-group" open>
          <summary className="role-group-header">
            <span>Wounds</span>
          </summary>
          <p className="muted">
            Units in this roster grouped by Wounds — one bar contribution per unit entry, not
            weighted by squad size. Click a bar to see which units it's made of.
          </p>
          {woundsBuckets.length > 0 ? (
            <div className="chart-container chart-clickable">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={woundsBuckets}>
                  <CartesianGrid strokeDasharray="" stroke="#333747" vertical={false} />
                  <XAxis dataKey="wounds" stroke="#8b8f9e" />
                  <YAxis allowDecimals={false} stroke="#8b8f9e" />
                  <Tooltip
                    contentStyle={{ background: "#1e212b", border: "1px solid #333747" }}
                    labelFormatter={(w) => `Wounds ${w}`}
                    formatter={(value) => [value, "units"]}
                  />
                  <Bar
                    dataKey="units"
                    fill={CHART_COLOR}
                    radius={BAR_RADIUS}
                    maxBarSize={BAR_SIZE}
                    onClick={(data) => showWoundsDrilldown((data.payload as WoundsBucket).wounds)}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="muted">No wounds data to chart yet.</p>
          )}
        </details>
      </details>

      <details className="accordion">
        <summary>Unit Buffs</summary>
        <p className="muted">
          A standing reference for what a token spend (Battle Focus, etc.) could buy this unit —
          shown next to the relevant stat in the Battle Tracker before you spend anything.
        </p>
        <form className="inline-form" onSubmit={handleAddBuff}>
          <select value={buffUnitId} onChange={(e) => setBuffUnitId(Number(e.target.value))} required>
            <option value="">Unit...</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.unit_definition.name}
              </option>
            ))}
          </select>
          <select value={buffStat} onChange={(e) => setBuffStat(e.target.value)}>
            {STAT_ORDER.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder='Modifier (e.g. +2")'
            value={buffModifier}
            onChange={(e) => setBuffModifier(e.target.value)}
            required
          />
          <input
            type="text"
            placeholder="Label (e.g. Battle Focus: Fade Back)"
            value={buffLabel}
            onChange={(e) => setBuffLabel(e.target.value)}
            required
          />
          <button type="submit">Add Buff</button>
        </form>
      </details>

      <details className="accordion">
        <summary>Unit Attachments</summary>
        <p className="muted">
          A Character leading a bodyguard unit — they act (and move) as one combined unit in the Battle Tracker.
        </p>

        {leaderReferences.length > 0 && (
          <details className="role-group" open>
            <summary className="role-group-header">
              <span>Leader Ability Reference</span>
            </summary>
            <p className="muted">
              Abilities that buff whatever unit these Leaders are attached to — a reference for
              deciding attachments below, not something that's auto-applied anywhere.
            </p>
            <ul className="ability-list">
              {leaderReferences.map(({ unit, abilities }) => {
                const leading = attachments.find((a) => a.leader_unit_id === unit.id);
                return abilities.map((a, i) => (
                  <li key={`${unit.id}-${i}`}>
                    <strong>{unit.unit_definition.name}</strong>
                    <span className="muted"> ({leading ? `leading ${unitLabel(leading.led_unit_id)}` : "not attached"})</span>
                    {" — "}
                    <strong>{a.name}</strong>: {renderAbilityText(a.text, `${unit.id}-${i}`)}
                  </li>
                ));
              })}
            </ul>
          </details>
        )}

        <form className="inline-form" onSubmit={handleAddAttachment}>
          <select value={leaderUnitId} onChange={(e) => setLeaderUnitId(Number(e.target.value))} required>
            <option value="">Leader unit...</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.unit_definition.name}
              </option>
            ))}
          </select>
          <select value={ledUnitId} onChange={(e) => setLedUnitId(Number(e.target.value))} required>
            <option value="">Led unit...</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.unit_definition.name}
              </option>
            ))}
          </select>
          <button type="submit" disabled={units.length < 2}>
            Attach
          </button>
        </form>
        <ul className="synergy-list">
          {attachments.map((a) => (
            <li key={a.id}>
              <strong>{unitLabel(a.leader_unit_id)}</strong> leads <strong>{unitLabel(a.led_unit_id)}</strong>
              <button type="button" className="link-button" onClick={() => handleDeleteAttachment(a.id)}>
                remove
              </button>
            </li>
          ))}
          {attachments.length === 0 && <li className="muted">No attachments yet.</li>}
        </ul>
      </details>

      <details className="accordion">
        <summary>Unit Synergies</summary>

        {auraReferences.length > 0 && (
          <details className="role-group" open>
            <summary className="role-group-header">
              <span>Aura Reference</span>
            </summary>
            <p className="muted">
              Passive effects that apply to whatever's in range on the table — who that actually
              is depends on live model positions, so this is a reminder these exist, not
              something logged as a Synergy below.
            </p>
            <ul className="ability-list">
              {auraReferences.map(({ unit, abilities }) =>
                abilities.map((a, i) => (
                  <li key={`${unit.id}-${i}`}>
                    <strong>{unit.unit_definition.name}</strong> — <strong>{a.name}</strong>:{" "}
                    {renderAbilityText(a.text, `aura-${unit.id}-${i}`)}
                  </li>
                )),
              )}
            </ul>
          </details>
        )}

        {psychicReferences.length > 0 && (
          <details className="role-group" open>
            <summary className="role-group-header">
              <span>Psychic Power Reference</span>
            </summary>
            <p className="muted">
              Powers that pick a target live each turn — usually an enemy unit, so there's nothing
              here to attach to one of your own units either. Reminder only.
            </p>
            <ul className="ability-list">
              {psychicReferences.map(({ unit, abilities }) =>
                abilities.map((a, i) => (
                  <li key={`${unit.id}-${i}`}>
                    <strong>{unit.unit_definition.name}</strong> — <strong>{a.name}</strong>:{" "}
                    {renderAbilityText(a.text, `psychic-${unit.id}-${i}`)}
                  </li>
                )),
              )}
            </ul>
          </details>
        )}

        <form className="inline-form" onSubmit={handleAddSynergy}>
          <select value={sourceUnitId} onChange={(e) => setSourceUnitId(Number(e.target.value))} required>
            <option value="">Source unit...</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.unit_definition.name}
              </option>
            ))}
          </select>
          <select value={targetUnitId} onChange={(e) => setTargetUnitId(Number(e.target.value))} required>
            <option value="">Target unit...</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.unit_definition.name}
              </option>
            ))}
          </select>
          <select value={triggerPhase} onChange={(e) => setTriggerPhase(e.target.value)}>
            {PHASES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Note (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <button type="submit" disabled={units.length < 2}>
            Add Synergy
          </button>
        </form>
        <ul className="synergy-list">
          {synergies.map((s) => (
            <li key={s.id}>
              <strong>{unitLabel(s.source_unit_id)}</strong> → <strong>{unitLabel(s.target_unit_id)}</strong>{" "}
              <span className="tag">{s.trigger_phase}</span>
              {s.note && <span className="muted"> — {s.note}</span>}
              <button type="button" className="link-button" onClick={() => handleDeleteSynergy(s.id)}>
                remove
              </button>
            </li>
          ))}
          {synergies.length === 0 && <li className="muted">No synergies yet.</li>}
        </ul>
      </details>

      <details className="accordion">
        <summary>Declared State Pools</summary>
        <p className="muted">
          Round/turn/phase-scoped resource pools (Battle Focus tokens, Blessings of Khorne, etc.).
        </p>
        <form className="inline-form" onSubmit={handleAddPool}>
          <input
            type="text"
            placeholder="Pool name (e.g. Battle Focus)"
            value={poolName}
            onChange={(e) => setPoolName(e.target.value)}
            required
          />
          <input
            type="number"
            min={0}
            placeholder="Max value"
            value={poolMax}
            onChange={(e) => setPoolMax(Number(e.target.value))}
            required
          />
          <select value={poolScope} onChange={(e) => setPoolScope(e.target.value)}>
            {POOL_SCOPES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <label className="checkbox-label">
            <input type="checkbox" checked={poolStacking} onChange={(e) => setPoolStacking(e.target.checked)} />
            stacking
          </label>
          <button type="submit">Add Pool</button>
        </form>
        <ul className="pool-list">
          {pools.map((p) => (
            <li key={p.id}>
              <strong>{p.name}</strong> <span className="tag">{p.scope}</span>
              <span className="muted">
                {" "}
                — max {p.max_value}
                {p.stacking ? ", stacking" : ""}
              </span>
              <button type="button" className="link-button" onClick={() => handleDeletePool(p.id)}>
                remove
              </button>
            </li>
          ))}
          {pools.length === 0 && <li className="muted">No pools yet.</li>}
        </ul>
      </details>
      </div>

      <aside className="roster-rail">
        <h2 className="rail-heading">Army Context</h2>

        <section className="rail-section">
          <h3 className="rail-section-head">Army Rule</h3>
          {factionArmyRules ? (
            <>
              <p className="muted rail-note">
                Library-level — some rules apply only to specific sub-factions.
              </p>
              {factionArmyRules.rules.map((r) => (
                <details key={r.name} className="rail-rule">
                  <summary>{r.name}</summary>
                  <div className="rail-rule-body">{renderAbilityText(r.text, `army-${r.name}`)}</div>
                </details>
              ))}
            </>
          ) : (
            <p className="muted">No army rule indexed for this faction yet.</p>
          )}
        </section>

        <section className="rail-section">
          <h3 className="rail-section-head">
            Detachment{selectedDetachment ? `: ${selectedDetachment.name}` : ""}
          </h3>
          {selectedDetachment ? (
            selectedDetachment.rules.length > 0 ? (
              <ul className="ability-list rail-detachment-rules">
                {selectedDetachment.rules.map((r) => (
                  <li key={r.name}>
                    <strong>{r.name}:</strong> {renderAbilityText(r.text, `detachment-${r.name}`)}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No rule text indexed for this detachment.</p>
            )
          ) : (
            <p className="muted">Choose a detachment above to see its rule here.</p>
          )}
          <p className="muted rail-note">Stratagems and enhancements aren't indexed yet.</p>
        </section>
      </aside>
      </div>

      {addOpen && (
        <div className="modal-overlay" onClick={() => setAddOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Add units</h2>
              <button type="button" className="link-button" onClick={() => setAddOpen(false)}>
                close
              </button>
            </div>
            <div className="inline-form">
              <label className="checkbox-label">
                <input type="checkbox" checked={showLegends} onChange={(e) => setShowLegends(e.target.checked)} />
                Legends
              </label>
              <label className="checkbox-label">
                <input type="checkbox" checked={showCrucible} onChange={(e) => setShowCrucible(e.target.checked)} />
                Crucible
              </label>
            </div>
            {groupDefsByRole(filteredAvailableUnits).map(([role, defs]) => (
              <details key={role} className="unit-role-group" open>
                <summary className="unit-role-heading">
                  {role} <span className="muted">({defs.length})</span>
                </summary>
                <ul className="available-unit-list">
                  {defs.map((u) => (
                    <li key={u.id} className="available-unit-row">
                      <details className="unit-card">
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
                      <button type="button" className="link-button" onClick={() => handleAddUnit(u)}>
                        add
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            ))}
            {availableUnits.length === 0 && <p className="muted">No units indexed for this faction yet.</p>}
            {availableUnits.length > 0 && filteredAvailableUnits.length === 0 && (
              <p className="muted">No units match — try enabling Legends or Crucible above.</p>
            )}
          </div>
        </div>
      )}

      {detailsGroup && (
        <UnitDetailsModal
          primary={detailsGroup.primary}
          leaders={detailsGroup.leaders}
          onClose={() => setDetailsGroup(null)}
          onSaved={refresh}
        />
      )}

      {weaponDrilldown && (
        <WeaponContributionsModal
          title={weaponDrilldown.title}
          skillLabel={weaponDrilldown.skillLabel}
          contributions={weaponDrilldown.contributions}
          onClose={() => setWeaponDrilldown(null)}
        />
      )}

      {unitListModal && (
        <UnitListModal
          title={unitListModal.title}
          units={unitListModal.units}
          onClose={() => setUnitListModal(null)}
        />
      )}
    </div>
  );
}
