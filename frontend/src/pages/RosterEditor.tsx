import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import { UnitAutocomplete } from "../components/UnitAutocomplete";
import { UnitDetailsModal } from "../components/UnitDetailsModal";
import { PHASES, POOL_SCOPES, STAT_ORDER } from "../types";
import type { BattleOut, DeclaredStatePool, Roster, UnitAttachment, UnitBuff, UnitOut, UnitSynergy } from "../types";
import { groupUnitsByRole } from "../units";
import { unitsByMovement, unitsBySave, weaponAttacksByStrength } from "../weapons";

// Validated with the dataviz skill's palette checker against this app's dark panel surface
// (#1e212b): single-series charts share one hue; the two-series save chart uses a pair that
// passes CVD/contrast checks (`node validate_palette.js "#e0574a,#4a90c9" --mode dark
// --surface "#1e212b"` -- all checks pass). The app's original --accent (#c0392b) failed the
// contrast-vs-surface check, hence the lighter red here.
const CHART_COLOR = "#e0574a";
const CHART_COLOR_SECONDARY = "#4a90c9";

// Shared bar-chart mark spec (dataviz skill: <=24px thick, 4px rounded data-end square at the
// baseline, solid recessive gridlines -- never dashed).
const BAR_SIZE = 24;
const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];

// One row renderer shared by a plain unit and a leader nested into the unit it leads (see
// RosterEditor's Units section) -- avoids duplicating this JSX for both cases.
function UnitRow({
  unit,
  isLeader,
  onRemove,
  onRemoveBuff,
  onShowDetails,
}: {
  unit: UnitOut;
  isLeader?: boolean;
  onRemove: (unitId: number) => void;
  onRemoveBuff: (unit: UnitOut, index: number) => void;
  onShowDetails?: () => void;
}) {
  return (
    <div className={`unit-row${isLeader ? " leader" : ""}`}>
      <span className="unit-name">{unit.unit_definition.name}</span>
      <span className="muted"> ({unit.unit_definition.points_cost}pts)</span>
      {onShowDetails && (
        <button type="button" className="link-button" onClick={onShowDetails}>
          details
        </button>
      )}
      <button type="button" className="link-button" onClick={() => onRemove(unit.id)}>
        remove
      </button>
      {unit.loadout.length > 0 && (
        <ul className="ability-list loadout-list">
          {unit.loadout.map((item) => (
            <li key={item.name}>
              {item.count}x {item.name}
            </li>
          ))}
        </ul>
      )}
      {unit.unit_definition.rules.length > 0 && (
        <div className="rule-tags">
          {unit.unit_definition.rules.map((r) => (
            <span key={r} className="tag">
              {r}
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

export function RosterEditor() {
  const { id } = useParams();
  const rosterId = Number(id);
  const navigate = useNavigate();

  const [roster, setRoster] = useState<Roster | null>(null);
  const [units, setUnits] = useState<UnitOut[]>([]);
  const [synergies, setSynergies] = useState<UnitSynergy[]>([]);
  const [pools, setPools] = useState<DeclaredStatePool[]>([]);
  const [attachments, setAttachments] = useState<UnitAttachment[]>([]);
  const [battles, setBattles] = useState<BattleOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [detailsGroup, setDetailsGroup] = useState<{ primary: UnitOut; leaders: UnitOut[] } | null>(null);

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

  if (!roster) return <div className="page">Loading...</div>;

  const { buckets: shotsByStrength, skippedUnits: skippedRanged } = weaponAttacksByStrength(units, "Ranged Weapons");
  const { buckets: meleeByStrength, skippedUnits: skippedMelee } = weaponAttacksByStrength(units, "Melee Weapons");
  const movementBuckets = unitsByMovement(units);
  const saveBuckets = unitsBySave(units);
  const roleGroups = groupUnitsByRole(units, attachments);
  const nestedLeaderIds = new Set(attachments.map((a) => a.leader_unit_id));

  return (
    <div className="page">
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
        <UnitAutocomplete onSelect={handleAddUnit} />
        {roleGroups.map((group) => (
          <div key={group.role} className="role-group">
            <div className="role-group-header">
              <span>{group.role}</span>
              <span className="role-group-points">{group.points}pts</span>
            </div>
            {group.units
              .filter((u) => !nestedLeaderIds.has(u.id))
              .map((u) => {
                const leaders = attachments
                  .filter((a) => a.led_unit_id === u.id)
                  .map((a) => units.find((x) => x.id === a.leader_unit_id))
                  .filter((x): x is UnitOut => !!x);
                return (
                  <div key={u.id} className="unit-card">
                    {leaders.map((leader) => (
                      <UnitRow
                        key={leader.id}
                        unit={leader}
                        isLeader
                        onRemove={handleRemoveUnit}
                        onRemoveBuff={handleRemoveBuff}
                      />
                    ))}
                    <UnitRow
                      unit={u}
                      onRemove={handleRemoveUnit}
                      onRemoveBuff={handleRemoveBuff}
                      onShowDetails={() => setDetailsGroup({ primary: u, leaders })}
                    />
                  </div>
                );
              })}
          </div>
        ))}
        {units.length === 0 && <p className="muted">No units yet — search above to add one.</p>}
      </details>

      <details className="accordion">
        <summary>Army Analysis</summary>

        <h3>Ranged Firepower</h3>
        <p className="muted">
          Total ranged shots this roster can put out, grouped by weapon Strength (dice-notation
          Attacks like D6 are averaged; range-dependent bonuses like Rapid Fire aren't modeled).
          {skippedRanged > 0 &&
            ` ${skippedRanged} unit${skippedRanged === 1 ? "" : "s"} with no confirmed loadout not included.`}
        </p>
        {shotsByStrength.length > 0 ? (
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={shotsByStrength}>
                <CartesianGrid strokeDasharray="" stroke="#333747" vertical={false} />
                <XAxis dataKey="strength" tickFormatter={(s) => `S${s}`} stroke="#8b8f9e" />
                <YAxis allowDecimals={false} stroke="#8b8f9e" />
                <Tooltip
                  contentStyle={{ background: "#1e212b", border: "1px solid #333747" }}
                  labelFormatter={(s) => `Strength ${s}`}
                  formatter={(value) => [value, "shots"]}
                />
                <Bar dataKey="shots" fill={CHART_COLOR} radius={BAR_RADIUS} maxBarSize={BAR_SIZE} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="muted">No ranged weapon data to chart yet.</p>
        )}

        <h3>Melee Onslaught</h3>
        <p className="muted">
          Total melee attacks this roster can put out, grouped by weapon Strength (same dice-
          averaging and loadout-only scope as Ranged Firepower above).
          {skippedMelee > 0 &&
            ` ${skippedMelee} unit${skippedMelee === 1 ? "" : "s"} with no confirmed loadout not included.`}
        </p>
        {meleeByStrength.length > 0 ? (
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={meleeByStrength}>
                <CartesianGrid strokeDasharray="" stroke="#333747" vertical={false} />
                <XAxis dataKey="strength" tickFormatter={(s) => `S${s}`} stroke="#8b8f9e" />
                <YAxis allowDecimals={false} stroke="#8b8f9e" />
                <Tooltip
                  contentStyle={{ background: "#1e212b", border: "1px solid #333747" }}
                  labelFormatter={(s) => `Strength ${s}`}
                  formatter={(value) => [value, "attacks"]}
                />
                <Bar dataKey="shots" fill={CHART_COLOR} radius={BAR_RADIUS} maxBarSize={BAR_SIZE} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="muted">No melee weapon data to chart yet.</p>
        )}

        <h3>Movement</h3>
        <p className="muted">
          Units in this roster grouped by Movement — one bar contribution per unit entry, not
          weighted by squad size (there's no reliable per-model count to work from).
        </p>
        {movementBuckets.length > 0 ? (
          <div className="chart-container">
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
                <Bar dataKey="units" fill={CHART_COLOR} radius={BAR_RADIUS} maxBarSize={BAR_SIZE} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="muted">No movement data to chart yet.</p>
        )}

        <h3>Save / Invulnerable Save</h3>
        <p className="muted">
          Units grouped by armor Save and Invulnerable Save (best 2+ to worst 7+/none), so both
          distributions read on the same scale.
        </p>
        {saveBuckets.length > 0 ? (
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={saveBuckets}>
                <CartesianGrid strokeDasharray="" stroke="#333747" vertical={false} />
                <XAxis dataKey="save" stroke="#8b8f9e" />
                <YAxis allowDecimals={false} stroke="#8b8f9e" />
                <Tooltip contentStyle={{ background: "#1e212b", border: "1px solid #333747" }} />
                <Legend />
                <Bar dataKey="sv" name="Armor Save" fill={CHART_COLOR} radius={BAR_RADIUS} maxBarSize={BAR_SIZE} />
                <Bar
                  dataKey="insv"
                  name="Invulnerable Save"
                  fill={CHART_COLOR_SECONDARY}
                  radius={BAR_RADIUS}
                  maxBarSize={BAR_SIZE}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="muted">No save data to chart yet.</p>
        )}
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

      {detailsGroup && (
        <UnitDetailsModal
          primary={detailsGroup.primary}
          leaders={detailsGroup.leaders}
          onClose={() => setDetailsGroup(null)}
        />
      )}
    </div>
  );
}
