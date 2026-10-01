import type { UnitOut } from "../types";

// Drill-down for a clicked Movement/Save bar on the Army Analysis charts -- simpler than
// WeaponContributionsModal since there's no weapon/to-hit breakdown here, just which units
// land in that bucket.
export function UnitListModal({ title, units, onClose }: { title: string; units: UnitOut[]; onClose: () => void }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{title}</h2>
          <button type="button" className="link-button" onClick={onClose}>
            close ✕
          </button>
        </div>
        <ul className="ability-list">
          {units.map((u) => (
            <li key={u.id}>
              <strong>{u.unit_definition.name}</strong> <span className="muted">({u.unit_definition.points_cost}pts)</span>
            </li>
          ))}
          {units.length === 0 && <li className="muted">No units.</li>}
        </ul>
      </div>
    </div>
  );
}
