import type { WeaponContribution } from "../weapons";

// Drill-down for a clicked Strength/to-hit bar segment on the Army Analysis charts -- lists
// exactly which units/weapons make up that segment's total.
export function WeaponContributionsModal({
  title,
  skillLabel,
  contributions,
  onClose,
}: {
  title: string;
  skillLabel: "BS" | "WS";
  contributions: WeaponContribution[];
  onClose: () => void;
}) {
  const total = Math.round(contributions.reduce((sum, c) => sum + c.totalAttacks, 0) * 10) / 10;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{title}</h2>
          <button type="button" className="link-button" onClick={onClose}>
            close ✕
          </button>
        </div>
        <div className="table-scroll">
          <table className="details-table">
            <thead>
              <tr>
                <th>Unit</th>
                <th>Weapon</th>
                <th>{skillLabel}</th>
                <th>Count</th>
                <th>Attacks/model</th>
                <th>Total attacks</th>
              </tr>
            </thead>
            <tbody>
              {contributions.map((c, i) => (
                <tr key={i}>
                  <td>{c.unitLabel}</td>
                  <td>{c.weaponName}</td>
                  <td>{c.skill}</td>
                  <td>{c.count}</td>
                  <td>{c.attacksPerModel}</td>
                  <td>{c.totalAttacks}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted">Total: {total} attacks</p>
      </div>
    </div>
  );
}
