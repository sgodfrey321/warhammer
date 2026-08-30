import { KeywordList } from "./Keyword";
import { renderAbilityText } from "../markup";
import { STAT_ORDER, WEAPON_STAT_ORDER } from "../types";
import type { ModelProfile, UnitOut, Weapon } from "../types";
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
}: {
  primary: UnitOut;
  leaders: UnitOut[];
  onClose: () => void;
}) {
  // Leaders first, primary (led) unit last -- mirrors the card ordering in RosterEditor's
  // Units section (leader rows stacked above the unit they lead).
  const combined: CombinedUnit[] = [
    ...leaders.map((unit) => ({ unit, label: unit.unit_definition.name })),
    { unit: primary, label: primary.unit_definition.name },
  ];

  const models = modelRows(combined);
  const ranged = weaponRows(combined, "ranged");
  const melee = weaponRows(combined, "melee");
  const abilities = combined.flatMap(({ unit, label }) =>
    unit.unit_definition.abilities.map((a) => ({ ...a, label })),
  );

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{primary.unit_definition.name}</h2>
          <button type="button" className="link-button" onClick={onClose}>
            close ✕
          </button>
        </div>

        {models.length > 0 ? (
          <section>
            <h3>Models ({models.reduce((sum, m) => sum + m.count, 0)})</h3>
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
          </section>
        ) : (
          <p className="muted">
            No per-model-type data indexed yet for this unit — re-run the bsdata-indexer to pick it up.
          </p>
        )}

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
