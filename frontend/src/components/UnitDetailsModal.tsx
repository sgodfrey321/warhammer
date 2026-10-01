import { useState } from "react";
import { KeywordList } from "./Keyword";
import { renderAbilityText } from "../markup";
import { STAT_ORDER, WEAPON_STAT_ORDER } from "../types";
import type { ModelGroup, ModelProfile, UnitOut, Weapon } from "../types";
import { api } from "../api";
import { weaponBaseName } from "../weapons";

interface CombinedUnit {
  unit: UnitOut;
  label: string;
}

interface ModelRow {
  profile: ModelProfile;
  count: number;
  label: string;
}

interface WeaponRow {
  weapon: Weapon;
  count: number;
  label: string;
}

// Only model-types/weapons this specific roster instance actually has (matched against
// unit.model_groups/loadout by name) are shown -- a catalogue option the player didn't take
// (e.g. an unequipped heavy-weapon choice) isn't listed, matching "what's really in this
// roster" over "everything this datasheet could carry".
function modelRows(combined: CombinedUnit[]): ModelRow[] {
  const rows: ModelRow[] = [];
  for (const { unit, label } of combined) {
    for (const profile of unit.unit_definition.model_profiles) {
      const group = unit.model_groups.find((g) => g.name === profile.name);
      if (group) rows.push({ profile, count: group.count, label });
    }
  }
  return rows;
}

function weaponRows(combined: CombinedUnit[], kind: "ranged" | "melee"): WeaponRow[] {
  const rows: WeaponRow[] = [];
  for (const { unit, label } of combined) {
    // Two model-types within the same unit can share an identical weapon (e.g. every
    // Guardian Defenders model-type carries its own "Close Combat Weapon") -- the roster's
    // loadout is already a unit-level total (not split per model-type), so seeing it in a
    // second profile would just repeat the exact same row. Dedupe by name per unit, not
    // globally -- a different combined unit (e.g. a nested leader) legitimately gets its own
    // row even for a same-named weapon, since it's labeled separately.
    const seen = new Set<string>();
    for (const profile of unit.unit_definition.model_profiles) {
      const weapons = kind === "ranged" ? profile.ranged_weapons : profile.melee_weapons;
      for (const weapon of weapons) {
        if (seen.has(weapon.name)) continue;
        const item = unit.loadout.find((i) => i.name === weaponBaseName(weapon.name));
        if (item) {
          rows.push({ weapon, count: item.count, label });
          seen.add(weapon.name);
        }
      }
    }
  }
  return rows;
}

function WeaponTable({ title, rows, omit }: { title: string; rows: WeaponRow[]; omit: "BS" | "WS" }) {
  if (rows.length === 0) return null;
  const columns = WEAPON_STAT_ORDER.filter((c) => c !== omit);
  return (
    <section>
      <h3>{title}</h3>
      <div className="table-scroll">
        <table className="details-table">
          <thead>
            <tr>
              <th>Weapon</th>
              {columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td>
                  {r.weapon.name} (x{r.count}) - {r.label}
                </td>
                {columns.map((c) => (
                  <td key={c}>
                    {c === "Keywords" ? (
                      <KeywordList value={r.weapon.characteristics[c] ?? ""} />
                    ) : (
                      r.weapon.characteristics[c] ?? "-"
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function UnitDetailsModal({
  primary,
  leaders,
  onClose,
  onSaved,
}: {
  primary: UnitOut;
  leaders: UnitOut[];
  onClose: () => void;
  // Called after model counts are saved, so the parent can refresh its own unit list.
  onSaved?: () => void;
}) {
  // Local copies (leaders first, primary/led unit last -- mirrors the card ordering in
  // RosterEditor's Units section) so declaring model counts re-renders the tables here
  // immediately, without depending on the parent re-passing fresh props.
  const [units, setUnits] = useState<UnitOut[]>([...leaders, primary]);
  const [editing, setEditing] = useState(false);
  // draft[unitId][profileName] = count while editing.
  const [draft, setDraft] = useState<Record<number, Record<string, number>>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const combined: CombinedUnit[] = units.map((unit) => ({ unit, label: unit.unit_definition.name }));

  const models = modelRows(combined);
  const ranged = weaponRows(combined, "ranged");
  const melee = weaponRows(combined, "melee");
  const abilities = combined.flatMap(({ unit, label }) =>
    unit.unit_definition.abilities.map((a) => ({ ...a, label })),
  );

  // Only units with per-model-type profiles can have counts declared (a purely manual unit
  // with no reference profiles has nothing to enumerate).
  const editableUnits = units.filter((u) => u.unit_definition.model_profiles.length > 0);

  function startEditing() {
    const seed: Record<number, Record<string, number>> = {};
    for (const u of editableUnits) {
      const counts: Record<string, number> = {};
      const profiles = u.unit_definition.model_profiles;
      for (const p of profiles) {
        const existing = u.model_groups.find((g) => g.name === p.name);
        // Default a single-profile unit to its minimum legal size; a multi-type squad starts
        // blank, since the reference data doesn't record how the models split across types.
        const fallback = profiles.length === 1 ? u.unit_definition.min_models : 0;
        counts[p.name] = existing ? existing.count : fallback;
      }
      seed[u.id] = counts;
    }
    setDraft(seed);
    setError(null);
    setEditing(true);
  }

  function setCount(unitId: number, name: string, value: number) {
    setDraft((d) => ({ ...d, [unitId]: { ...d[unitId], [name]: Math.max(0, value) } }));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const saved: UnitOut[] = [];
      for (const u of editableUnits) {
        const counts = draft[u.id] ?? {};
        const model_groups: ModelGroup[] = Object.entries(counts)
          .filter(([, count]) => count > 0)
          .map(([name, count]) => ({ name, count }));
        saved.push(await api.updateUnit(u.roster_id, u.id, { model_groups }));
      }
      setUnits((prev) => prev.map((u) => saved.find((n) => n.id === u.id) ?? u));
      setEditing(false);
      onSaved?.();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{primary.unit_definition.name}</h2>
          <button type="button" className="link-button" onClick={onClose}>
            close ✕
          </button>
        </div>

        <section>
          <div className="modal-section-head">
            <h3>Models{models.length > 0 ? ` (${models.reduce((sum, m) => sum + m.count, 0)})` : ""}</h3>
            {!editing && editableUnits.length > 0 && (
              <button type="button" className="link-button" onClick={startEditing}>
                {models.length > 0 ? "Edit models" : "Declare models"}
              </button>
            )}
          </div>

          {editing ? (
            <div className="model-edit">
              {editableUnits.map((u) => (
                <div key={u.id} className="model-edit-group">
                  {editableUnits.length > 1 && <p className="muted">{u.unit_definition.name}</p>}
                  {u.unit_definition.model_profiles.map((p) => (
                    <label key={p.name} className="model-edit-row">
                      <span>{p.name}</span>
                      <input
                        type="number"
                        min={0}
                        value={draft[u.id]?.[p.name] ?? 0}
                        onChange={(e) => setCount(u.id, p.name, Math.floor(Number(e.target.value) || 0))}
                      />
                    </label>
                  ))}
                </div>
              ))}
              {error && <p className="error">{error}</p>}
              <div className="model-edit-actions">
                <button type="button" onClick={handleSave} disabled={saving}>
                  {saving ? "Saving…" : "Save"}
                </button>
                <button type="button" className="link-button" onClick={() => setEditing(false)} disabled={saving}>
                  Cancel
                </button>
              </div>
            </div>
          ) : models.length > 0 ? (
            <div className="table-scroll">
              <table className="details-table">
                <thead>
                  <tr>
                    <th>Unit</th>
                    {STAT_ORDER.map((s) => (
                      <th key={s}>{s}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {models.map((m, i) => (
                    <tr key={i}>
                      <td>
                        {m.profile.name} (x{m.count}) - {m.label}
                      </td>
                      {STAT_ORDER.map((s) => (
                        <td key={s}>{m.profile.stats[s] || "-"}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">
              No model breakdown yet — per-model counts come from a BattleScribe/NewRecruit import.
              {editableUnits.length > 0
                ? " For this hand-added unit, use Declare models above to set per-type counts."
                : ""}
            </p>
          )}
        </section>

        <WeaponTable title="Ranged Weapons" rows={ranged} omit="WS" />
        <WeaponTable title="Melee Weapons" rows={melee} omit="BS" />

        {abilities.length > 0 && (
          <section>
            <h3>Abilities</h3>
            <ul className="ability-list">
              {abilities.map((a, i) => (
                <li key={i}>
                  <strong>{a.name}</strong> - {a.label}: {renderAbilityText(a.text, `${a.label}-${i}`)}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
