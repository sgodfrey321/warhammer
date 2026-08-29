import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { UnitAutocomplete } from "../components/UnitAutocomplete";
import { PHASES } from "../types";
import type { Roster, UnitOut, UnitSynergy } from "../types";

export function RosterEditor() {
  const { id } = useParams();
  const rosterId = Number(id);
  const navigate = useNavigate();

  const [roster, setRoster] = useState<Roster | null>(null);
  const [units, setUnits] = useState<UnitOut[]>([]);
  const [synergies, setSynergies] = useState<UnitSynergy[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [sourceUnitId, setSourceUnitId] = useState<number | "">("");
  const [targetUnitId, setTargetUnitId] = useState<number | "">("");
  const [triggerPhase, setTriggerPhase] = useState<string>(PHASES[0]);
  const [note, setNote] = useState("");

  function refresh() {
    api.getRoster(rosterId).then(setRoster).catch((e) => setError(String(e)));
    api.listUnits(rosterId).then(setUnits).catch((e) => setError(String(e)));
    api.listSynergies(rosterId).then(setSynergies).catch((e) => setError(String(e)));
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
          {units.map((u) => (
            <li key={u.id}>
              <span className="unit-name">{u.unit_definition.name}</span>
              <span className="muted"> ({u.unit_definition.points_cost}pts)</span>
              <button type="button" className="link-button" onClick={() => handleRemoveUnit(u.id)}>
                remove
              </button>
            </li>
          ))}
          {units.length === 0 && <li className="muted">No units yet — search above to add one.</li>}
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
    </div>
  );
}
