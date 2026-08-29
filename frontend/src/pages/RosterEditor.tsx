import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { UnitAutocomplete } from "../components/UnitAutocomplete";
import { PHASES, POOL_SCOPES } from "../types";
import type { DeclaredStatePool, Roster, UnitAttachment, UnitOut, UnitSynergy } from "../types";

export function RosterEditor() {
  const { id } = useParams();
  const rosterId = Number(id);
  const navigate = useNavigate();

  const [roster, setRoster] = useState<Roster | null>(null);
  const [units, setUnits] = useState<UnitOut[]>([]);
  const [synergies, setSynergies] = useState<UnitSynergy[]>([]);
  const [pools, setPools] = useState<DeclaredStatePool[]>([]);
  const [attachments, setAttachments] = useState<UnitAttachment[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [sourceUnitId, setSourceUnitId] = useState<number | "">("");
  const [targetUnitId, setTargetUnitId] = useState<number | "">("");
  const [triggerPhase, setTriggerPhase] = useState<string>(PHASES[0]);
  const [note, setNote] = useState("");

  const [leaderUnitId, setLeaderUnitId] = useState<number | "">("");
  const [ledUnitId, setLedUnitId] = useState<number | "">("");

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

  async function handleStartBattle() {
    try {
      const battle = await api.createBattle(rosterId);
      navigate(`/battles/${battle.id}`);
    } catch (e) {
      setError(String(e));
    }
  }

  function unitLabel(unitId: number): string {
    const u = units.find((x) => x.id === unitId);
    return u ? u.unit_definition.name : `#${unitId}`;
  }

  if (!roster) return <div className="page">Loading...</div>;

  return (
    <div className="page">
      <h1>{roster.name}</h1>
      <p className="muted">
        {roster.faction} {roster.points_limit ? `— ${roster.points_limit}pts limit` : ""}
      </p>
      {error && <p className="error">{error}</p>}

      <button type="button" onClick={handleStartBattle} className="primary">
        Start Battle
      </button>

      <section>
        <h2>Units</h2>
        <UnitAutocomplete onSelect={handleAddUnit} />
        <ul className="unit-list">
          {units.map((u) => {
            const leads = attachments.filter((a) => a.leader_unit_id === u.id).map((a) => unitLabel(a.led_unit_id));
            const ledBy = attachments.filter((a) => a.led_unit_id === u.id).map((a) => unitLabel(a.leader_unit_id));
            return (
              <li key={u.id}>
                <span className="unit-name">{u.unit_definition.name}</span>
                <span className="muted"> ({u.unit_definition.points_cost}pts)</span>
                {leads.length > 0 && <span className="tag">→ leads {leads.join(", ")}</span>}
                {ledBy.length > 0 && <span className="tag">← led by {ledBy.join(", ")}</span>}
                <button type="button" className="link-button" onClick={() => handleRemoveUnit(u.id)}>
                  remove
                </button>
                {u.loadout.length > 0 && (
                  <div className="muted loadout-summary">
                    {u.loadout.map((item) => `${item.count}x ${item.name}`).join(", ")}
                  </div>
                )}
              </li>
            );
          })}
          {units.length === 0 && <li className="muted">No units yet — search above to add one.</li>}
        </ul>
      </section>

      <section>
        <h2>Unit Attachments</h2>
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
      </section>

      <section>
        <h2>Unit Synergies</h2>
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
      </section>

      <section>
        <h2>Declared State Pools</h2>
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
      </section>
    </div>
  );
}
